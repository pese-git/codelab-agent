"""Стадия обработки prompt директив (/tool, /tool-pending, _meta.promptDirectives и т.д.)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import structlog

from codelab.server.domain.session import Session
from codelab.server.messages import ACPMessage
from codelab.server.protocol.handlers.prompt import (
    build_executor_tool_execution_updates,
    build_fs_client_request,
    build_plan_entries,
    build_policy_tool_execution_updates,
    build_terminal_client_request,
    can_use_fs_client_rpc,
    can_use_terminal_client_rpc,
    create_tool_call,
    resolve_prompt_directives,
    resolve_tool_title,
)
from codelab.server.protocol.handlers.prompt.client_requests import PreparedFsClientRequest
from codelab.server.protocol.handlers.tool_policy import decide_tool_policy
from codelab.server.protocol.state import PromptDirectives

from ..base import PromptStage
from ..context import PromptContext

if TYPE_CHECKING:
    from codelab.server.protocol.handlers.permission_manager import PermissionManager
    from codelab.server.tools.base import ToolRegistry

logger = structlog.get_logger()


async def _prepare_client_rpc(
    context: PromptContext,
    build: Callable[[Session], PreparedFsClientRequest | None],
    *,
    name: str,
) -> PreparedFsClientRequest | None:
    """Подготовить agent→client запрос и перевести turn в waiting_client_rpc.

    Одна команда, и построение запроса внутри неё: сборка заводит tool call в
    сессии, а снимок `pending_external_request` — то, по чему приходящий ответ
    клиента соотносится с turn'ом. Порознь они дали бы вызов без ожидания или
    ожидание без вызова.
    """

    def _prepare(session: Session) -> PreparedFsClientRequest | None:
        prepared = build(session)
        if prepared is None:
            return None
        if session.active_turn is not None:
            session.active_turn.pending_external_request = prepared.pending_request
            session.active_turn.phase = "waiting_client_rpc"
        return prepared

    return await context.commands.apply(_prepare, name=name)


def _can_run_tool_runtime(session: Session) -> bool:
    """Проверяет, можно ли запускать tool-runtime в текущей сессии."""
    caps = session.config.runtime_capabilities
    if caps is None:
        return False
    return caps.terminal or caps.fs_read or caps.fs_write


class DirectivesStage(PromptStage):
    """Обрабатывает prompt директивы для принудительного вызова инструментов.

    Читает как text-based директивы (/tool, /tool-pending, /plan, /fs-read и пр.),
    так и structured overrides из _meta.promptDirectives.

    Порядок обработки:
    1. forced_stop_reason — устанавливает stop_reason, не прерывает pipeline
    2. publish_plan — эмитирует plan notification, не прерывает pipeline
    3. terminal_command — строит terminal/create RPC request, прерывает pipeline
    4. fs_read_path / fs_write_path — строит fs/* RPC request, прерывает pipeline
    5. requestTool — в зависимости от policy:
       - "ask": запрашивает permission, прерывает pipeline
       - "allow": выполняет tool, продолжает pipeline
       - "reject": отменяет tool, продолжает pipeline
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        permission_manager: PermissionManager,
    ) -> None:
        self._tool_registry = tool_registry
        self._permission_manager = permission_manager

    async def process(self, context: PromptContext) -> PromptContext:
        if context.should_stop:
            return context

        directives = resolve_prompt_directives(
            params=context.params,
            text_preview=context.raw_text,
        )
        context.meta["directives"] = directives

        # 1. Forced stop reason — изменяем stop_reason, но не останавливаем pipeline
        if directives.forced_stop_reason is not None:
            context.stop_reason = directives.forced_stop_reason

        # 2. Publish plan — эмитируем plan notification, не останавливаем pipeline
        await self._apply_publish_plan(context, directives)

        # 3. Terminal RPC — turn deferred, если запрос сформирован
        if await self._apply_terminal_rpc(context, directives):
            return context

        # 4. FS RPC — turn deferred, если запрос сформирован
        if await self._apply_fs_rpc(context, directives):
            return context

        # 5. Request tool — permission flow
        return await self._apply_request_tool(context, directives)

    async def _apply_publish_plan(
        self, context: PromptContext, directives: PromptDirectives
    ) -> None:
        """Директива publish_plan: эмитировать plan notification и сохранить в сессии."""
        if not directives.publish_plan:
            return
        plan_entries = build_plan_entries(directives=directives, text_preview=context.raw_text)
        if not plan_entries:
            return
        context.notifications.append(
            ACPMessage.notification(
                "session/update",
                {
                    "sessionId": context.session_id,
                    "update": {
                        "sessionUpdate": "plan",
                        "entries": plan_entries,
                    },
                },
            )
        )
        # План сохраняется в сессии для replay. Носитель — доменный агрегат; ACP-форма
        # {content, priority, status}, ушедшая в wire выше, воспроизводится маппером на
        # границе сохранения (P2-26: прежняя форма {title, description} невалидна по ACP
        # и теряла статусы при replay).
        from codelab.server.domain.session import AgentPlan
        from codelab.server.mapping.plan_mapper import PlanMapper

        acp_entries = PlanMapper.entries_to_acp(list(plan_entries))
        await context.commands.apply(
            lambda session: setattr(
                session, "plan", AgentPlan(steps=PlanMapper.from_acp(acp_entries))
            ),
            name="plan_published",
        )

    async def _apply_terminal_rpc(
        self, context: PromptContext, directives: PromptDirectives
    ) -> bool:
        """Директива terminal_command: сформировать client RPC. True — turn deferred."""
        if directives.terminal_command is None or not can_use_terminal_client_rpc(context.session):
            return False
        prepared = await _prepare_client_rpc(
            context,
            lambda session: build_terminal_client_request(
                session=session,
                session_id=context.session_id,
                directives=directives,
            ),
            name="terminal_rpc_awaited",
        )
        if prepared is None:
            return False
        context.notifications.extend(prepared.messages)
        context.pending_permission = True  # turn deferred — не отправлять response
        context.should_stop = True
        return True

    async def _apply_fs_rpc(self, context: PromptContext, directives: PromptDirectives) -> bool:
        """Директива fsReadPath/fsWritePath: сформировать fs/* RPC. True — turn deferred."""
        if directives.fs_read_path is None and directives.fs_write_path is None:
            return False
        fs_kind = "fs_read" if directives.fs_read_path is not None else "fs_write"
        if not can_use_fs_client_rpc(context.session, fs_kind):
            return False
        prepared = await _prepare_client_rpc(
            context,
            lambda session: build_fs_client_request(
                session=session,
                session_id=context.session_id,
                directives=directives,
            ),
            name="fs_rpc_awaited",
        )
        if prepared is None:
            return False
        context.notifications.extend(prepared.messages)
        context.pending_permission = True  # turn deferred — не отправлять response
        context.should_stop = True
        return True

    async def _apply_request_tool(
        self, context: PromptContext, directives: PromptDirectives
    ) -> PromptContext:
        """Директива request_tool: создать tool call и провести permission-flow."""
        if not directives.request_tool:
            return context

        if not _can_run_tool_runtime(context.session):
            # Сообщаем о недоступности tool runtime
            context.notifications.append(
                ACPMessage.notification(
                    "session/update",
                    {
                        "sessionId": context.session_id,
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {
                                "type": "text",
                                "text": (
                                    "Tool runtime unavailable: capability not "
                                    "negotiated via initialize"
                                ),
                            },
                        },
                    },
                )
            )
            return context

        tool_title = resolve_tool_title(directives.tool_kind)
        tool_call_id = await context.commands.apply(
            lambda session: create_tool_call(
                session,
                title=tool_title,
                kind=directives.tool_kind,
            ),
            name="directive_tool_call_created",
        )
        if tool_call_id is None:
            return context

        context.notifications.append(
            ACPMessage.notification(
                "session/update",
                {
                    "sessionId": context.session_id,
                    "update": {
                        "sessionUpdate": "tool_call",
                        "toolCallId": tool_call_id,
                        "title": tool_title,
                        "kind": directives.tool_kind,
                        "status": "pending",
                    },
                },
            )
        )

        # Проверяем политику разрешений (включает mode check)
        policy = decide_tool_policy(context.session, directives.tool_kind)

        if policy == "allow":
            # Политика разрешает — выполняем tool без запроса permission.
            execution_updates = build_executor_tool_execution_updates(
                session=context.session,
                session_id=context.session_id,
                tool_call_id=tool_call_id,
                leave_running=False,
            )
            context.notifications.extend(execution_updates)
            return context

        if policy == "reject":
            # Политика отклоняет — отменяем tool call, завершаем turn с cancelled.
            execution_updates = build_policy_tool_execution_updates(
                session=context.session,
                session_id=context.session_id,
                tool_call_id=tool_call_id,
                allowed=False,
            )
            context.notifications.extend(execution_updates)
            context.stop_reason = "cancelled"
            return context

        # policy == "ask" — запрашиваем permission у пользователя
        await self._request_permission(context, directives, tool_call_id, tool_title)
        return context

    async def _request_permission(
        self,
        context: PromptContext,
        directives: PromptDirectives,
        tool_call_id: str,
        tool_title: str,
    ) -> None:
        """policy == "ask": сформировать permission request и приостановить turn."""
        options = self._permission_manager.build_permission_options()
        permission_request = ACPMessage.request(
            "session/request_permission",
            {
                "sessionId": context.session_id,
                "toolCall": {
                    "toolCallId": tool_call_id,
                    "title": tool_title,
                    "kind": directives.tool_kind,
                    "status": "pending",
                },
                "options": options,
            },
        )
        # Идентификатор запроса и фаза turn'а — одна команда: ответ на разрешение
        # придёт отдельным запросом и ищет сессию именно по `permission_request_id`.
        phase = "waiting_tool_completion" if directives.keep_tool_pending else "waiting_permission"

        def _await_permission(session: Session) -> None:
            if session.active_turn is None:
                return
            session.active_turn.permission_request_id = permission_request.id
            session.active_turn.permission_tool_call_id = tool_call_id
            session.active_turn.phase = phase

        await context.commands.require_active_turn(
            _await_permission, name="directive_permission_requested"
        )
        context.notifications.append(permission_request)
        context.pending_permission = True
        context.should_stop = True

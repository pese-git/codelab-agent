"""Главный оркестратор обработки prompt-turn через Pipeline Pattern."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import structlog

from ...client_rpc.service import ClientRPCService
from ...mapping.session_mapper import SessionMapper
from ...messages import ACPMessage, JsonRpcId
from ...rpc_holder import ClientRPCServiceHolder
from ...storage import SessionStorage
from ...tools.base import ToolRegistry
from ..content.acp_codec import ACPContentCodec
from ..session_merge import save_session_merging
from ..state import LLMLoopResult, ProtocolOutcome, SessionState
from ..turn_cancellation import TurnCancellationRegistry
from .event_history_writer import EventHistoryWriter
from .permission_manager import PermissionManager
from .pipeline import (
    LLMLoopStage,
    PromptContext,
    PromptPipeline,
)
from .plan_builder import PlanBuilder
from .slash_commands import CommandRegistry
from .state_manager import StateManager
from .tool_call_handler import ToolCallHandler
from .turn_lifecycle_manager import TurnLifecycleManager

if TYPE_CHECKING:
    from codelab.server.agent.context.file_cache import SessionFileCacheRegistry
    from codelab.server.domain.session import Session as DomainSession
    from codelab.server.mcp.manager import MCPManager

    from .global_policy_manager import GlobalPolicyManager

logger = structlog.get_logger()


class PromptOrchestrator:
    """Фабрика и точка входа для обработки prompt-turn через Pipeline.

    Собирает все стадии в PromptPipeline и предоставляет методы:
    - handle_prompt: основная обработка prompt-turn
    - handle_cancel: отмена активного turn
    - execute_pending_tool: выполнение tool после permission approval
    """

    def __init__(
        self,
        state_manager: StateManager,
        plan_builder: PlanBuilder,
        turn_lifecycle_manager: TurnLifecycleManager,
        tool_call_handler: ToolCallHandler,
        permission_manager: PermissionManager,
        tool_registry: ToolRegistry,
        llm_loop_stage: LLMLoopStage,
        command_registry: CommandRegistry,
        pipeline: PromptPipeline,
        client_rpc_service_holder: ClientRPCServiceHolder | None = None,
        client_rpc_service: ClientRPCService | None = None,  # backward compatibility
        global_policy_manager: GlobalPolicyManager | None = None,
        session_file_cache_registry: SessionFileCacheRegistry | None = None,
        turn_cancellation: TurnCancellationRegistry | None = None,
    ):
        self.state_manager = state_manager
        self.turn_cancellation = turn_cancellation
        # Единственный писатель формата события истории (фаза C ADR-006); stateless.
        self._history_writer = EventHistoryWriter()
        self.plan_builder = plan_builder
        self.turn_lifecycle_manager = turn_lifecycle_manager
        self.tool_call_handler = tool_call_handler
        self.permission_manager = permission_manager
        self.tool_registry = tool_registry
        self.global_policy_manager = global_policy_manager
        self._session_file_cache_registry = session_file_cache_registry
        self._tools_registered = False

        # Поддерживаем оба способа передачи сервиса
        if client_rpc_service_holder is not None:
            self.client_rpc_service_holder = client_rpc_service_holder
        elif client_rpc_service is not None:
            # backward compatibility: создаём holder с уже установленным сервисом
            self.client_rpc_service_holder = ClientRPCServiceHolder()
            self.client_rpc_service_holder.service = client_rpc_service
        else:
            self.client_rpc_service_holder = None

        # Регистрация plan tool сразу
        from ...tools.definitions import PlanToolDefinitions
        from ...tools.executors.plan_executor import PlanToolExecutor

        PlanToolDefinitions.register_all(tool_registry, PlanToolExecutor())

        self._llm_loop_stage = llm_loop_stage
        self._command_registry = command_registry
        self._pipeline = pipeline

    @property
    def client_rpc_service(self) -> ClientRPCService | None:
        """Возвращает ClientRPCService из holder."""
        if self.client_rpc_service_holder is not None:
            return self.client_rpc_service_holder.service
        return None

    def _ensure_tools_registered(self) -> None:
        """Лениво регистрирует tool executors при первом использовании."""
        if self._tools_registered:
            return

        if self.client_rpc_service is not None:
            from ...tools.definitions import (
                FileSystemToolDefinitions,
                TerminalToolDefinitions,
            )
            from ...tools.executors.decorators.project_structure import (
                ProjectStructureDecorator,
            )
            from ...tools.executors.filesystem_executor import FileSystemToolExecutor
            from ...tools.executors.terminal_executor import TerminalToolExecutor
            from ...tools.integrations.client_rpc_bridge import ClientRPCBridge
            from ...tools.integrations.permission_checker import PermissionChecker

            bridge = ClientRPCBridge(self.client_rpc_service)
            checker = PermissionChecker(self.permission_manager)

            fs_executor = FileSystemToolExecutor(bridge, checker)

            if self._session_file_cache_registry is not None:
                from ...agent.context.file_cache_decorator import FileCacheDecorator

                fs_executor = FileCacheDecorator(
                    wrapped=fs_executor,
                    session_registry=self._session_file_cache_registry,
                )

            FileSystemToolDefinitions.register_all(self.tool_registry, fs_executor)
            terminal_executor = TerminalToolExecutor(bridge, checker)
            TerminalToolDefinitions.register_all(
                self.tool_registry, ProjectStructureDecorator(terminal_executor)
            )
            logger.debug(
                "PromptOrchestrator_registered tool executors",
                tools_registered=len(self.tool_registry.get_available_tools("")),
                file_cache_enabled=self._session_file_cache_registry is not None,
            )

        self._tools_registered = True

    @property
    def command_registry(self) -> CommandRegistry:
        return self._command_registry

    async def handle_prompt(
        self,
        request_id: JsonRpcId | None,
        params: dict[str, Any],
        session: SessionState,
        storage: SessionStorage,
        mcp_manager: MCPManager | None = None,
        mcp_prompt_handlers: dict[str, Any] | None = None,
        notification_callback: Callable[[ACPMessage], Awaitable[None]] | None = None,
    ) -> ProtocolOutcome:
        """Обрабатывает session/prompt request.

        Оркестрирует весь цикл обработки промпта:
        1. Инициализация active turn
        2. Извлечение текста из prompt blocks
        3. Обработка через LLM-агента
        4. Построение и отправка notifications
        5. Управление tool calls, permissions, client RPC
        6. Финализация turn

        Args:
            request_id: ID входящего request
            params: Параметры (должны содержать prompt array)
            session: Состояние сессии
            storage: Хранилище сессий
            mcp_manager: MCP manager для сессии (из runtime registry)
            mcp_prompt_handlers: Обработчики MCP prompts (из runtime registry)
            notification_callback: Опциональный callback для немедленной отправки notifications.

        Returns:
            ProtocolOutcome с notifications и response
        """
        # Лениво регистрируем tool executors если service стал доступен
        self._ensure_tools_registered()

        session_id = session.session_id
        prompt = params.get("prompt", [])

        # Подготовка состояния сессии до запуска pipeline
        text_preview = _extract_text_preview(prompt)
        prompt_text = _extract_full_text(prompt)
        self.state_manager.update_session_title(session, text_preview)
        self.state_manager.add_user_message(session, prompt)
        for block in prompt:
            self._history_writer.save_user_message_chunk(session, block)
        self.state_manager.update_session_timestamp(session)

        context = PromptContext(
            session_id=session_id,
            session=session,
            request_id=request_id,
            params=params,
            raw_text=prompt_text,
            content_parts=ACPContentCodec().decode(prompt) if isinstance(prompt, list) else [],
            # Write-фаза (ADR-006, D4-a): доменный снимок рабочей модели. Аддитивно,
            # source-of-truth пока `session` (SessionState); потребителей нет.
            domain_session=SessionMapper.to_domain(session),
            # Промежуточные записи turn'а (ADR-007): без них копия turn'а
            # расходилась с диском на десятки секунд. Слияние внутри — развязка на
            # случай, если отмена или ответ на разрешение успели записать своё.
            persist=lambda: save_session_merging(storage, session),
        )
        context.meta["mcp_manager"] = mcp_manager
        context.meta["mcp_prompt_handlers"] = mcp_prompt_handlers or {}
        if notification_callback is not None:
            context.meta["notification_callback"] = notification_callback

        result = await self._pipeline.run(context)

        # Pipeline-ошибка: закрыть turn если он был открыт
        if result.error_response is not None:
            if session.active_turn is not None:
                self.turn_lifecycle_manager.finalize_turn(session, "end_turn")
                self.turn_lifecycle_manager.clear_active_turn(session)
            # Не отправляем notifications при ошибке валидации
            return ProtocolOutcome(response=result.error_response, notifications=[])

        # Добавить session info независимо от того, завершён turn или отложен
        summary = self.state_manager.get_session_summary(session)
        result.notifications.append(_build_session_info_notification(session_id, summary))

        from .session import _serialize_available_commands

        result.notifications.append(
            ACPMessage.notification(
                "session/update",
                {
                    "sessionId": session_id,
                    "update": {
                        "sessionUpdate": "available_commands_update",
                        "availableCommands": _serialize_available_commands(
                            session.available_commands
                        ),
                    },
                },
            )
        )
        self._history_writer.save_session_info_update(
            session,
            title=summary.get("title"),
            updated_at=summary.get("updated_at"),
        )

        # Turn отложен — ожидает разрешения пользователя
        if result.pending_permission:
            logger.debug(
                "turn deferred, awaiting permission response",
                session_id=session_id,
                permission_request_id=(
                    session.active_turn.permission_request_id if session.active_turn else None
                ),
            )
            return ProtocolOutcome(notifications=result.notifications)

        logger.debug(
            "prompt handling completed via pipeline",
            session_id=session_id,
            stop_reason=result.stop_reason,
            notifications_count=len(result.notifications),
        )

        response = (
            ACPMessage.response(request_id, {"stopReason": result.stop_reason})
            if request_id is not None
            else None
        )
        return ProtocolOutcome(response=response, notifications=result.notifications)

    def handle_cancel(
        self,
        request_id: JsonRpcId | None,
        params: dict[str, Any],
        session: DomainSession,
    ) -> ProtocolOutcome:
        """Обрабатывает session/cancel request.

        Логика:
        1. Найти сессию если нужна по ID
        2. Если есть active turn, установить cancel_requested флаг
        3. Отменить все активные tool calls
        4. Отметить cancelled permission requests
        5. Отметить cancelled client RPC requests
        6. Завершить turn с stop_reason='cancel'

        Транзакция работает доменным агрегатом (фаза D ADR-006): состояние меняют
        доменные сеймы, wire остаётся только в построении нотификаций.

        Args:
            request_id: ID cancel request
            params: Параметры (sessionId)
            session: Доменный агрегат сессии (будет обновлён)

        Returns:
            ProtocolOutcome с notifications об отмене
        """
        session_id = params.get("sessionId", str(session.id))
        notifications: list[ACPMessage] = []

        if session.active_turn is None:
            logger.debug("cancel request with no active turn", session_id=session_id)
            return ProtocolOutcome(response=None, notifications=[])

        # Сигнал отмены — в процессном реестре, а не в состоянии сессии: у каждого
        # запроса своя копия сессии с диска, поэтому запись в неё идущий turn не
        # увидит (P0-39, правило «сигнал против состояния» ADR-007).
        if self.turn_cancellation is not None:
            self.turn_cancellation.cancel(session_id)
        session.mark_turn_cancel_requested()

        cancel_messages = self.tool_call_handler.cancel_active_tools(session, session_id)
        notifications.extend(cancel_messages)
        # Отмена обязана попасть и в events_history: иначе реплей на session/load
        # отдаст вызов как pending, хотя клиент уже получил cancelled. Источник
        # записи — сами отправленные нотификации, чтобы «какие вызовы отменены»
        # не дублировалось предикатом активности.
        _save_tool_updates_to_history(session, cancel_messages)

        if session.active_turn.permission_request_id is not None:
            session.cancel_permission_request(session.active_turn.permission_request_id)

        if session.active_turn.pending_external_request is not None:
            session.cancel_client_rpc_request(
                session.active_turn.pending_external_request.request_id
            )

        if self.client_rpc_service is not None:
            cancelled_rpc_count = self.client_rpc_service.cancel_all_pending_requests(
                reason="session/cancel requested"
            )
            if cancelled_rpc_count > 0:
                logger.debug(
                    "cancelled pending RPC requests",
                    session_id=session_id,
                    cancelled_count=cancelled_rpc_count,
                )

        # Отложенный хвост батча (P2-40) не выполнится — отвечаем модели, иначе
        # вызовы останутся без `role: tool` (найдено на `sess_a98dab30f7c3`).
        session.answer_deferred_batch(reason="turn отменён пользователем")

        # Сохраняем prompt response до очистки active_turn. `stop_reason` —
        # ACP-значение `cancelled`, нормализация не нужна (литерал уже валиден).
        if session.active_turn.prompt_request_id is not None:
            session.runtime.pending_prompt_response = {
                "request_id": session.active_turn.prompt_request_id,
                "stop_reason": "cancelled",
            }

        session.clear_active_turn()

        logger.debug(
            "cancel request handled", session_id=session_id, notifications_count=len(notifications)
        )
        return ProtocolOutcome(response=None, notifications=notifications)

    async def execute_pending_tool(
        self,
        session: SessionState,
        session_id: str,
        tool_call_id: str,
        mcp_manager: MCPManager | None = None,
        notification_callback: Callable[[ACPMessage], Awaitable[None]] | None = None,
        domain_session: DomainSession | None = None,
        persist: Callable[[], Awaitable[None]] | None = None,
    ) -> LLMLoopResult:
        """Выполняет pending tool после permission approval и продолжает LLM loop."""
        return await self._llm_loop_stage.execute_pending_tool(
            session=session,
            session_id=session_id,
            tool_call_id=tool_call_id,
            mcp_manager=mcp_manager,
            notification_callback=notification_callback,
            domain_session=domain_session,
            persist=persist,
        )


# ── module-level helpers ──────────────────────────────────────────────────────


def _save_tool_updates_to_history(session: DomainSession, messages: list[ACPMessage]) -> None:
    """Сохранить отправленные tool_call_update в историю реплея.

    Форму события истории владеет `EventHistoryWriter`; создаётся здесь, так как
    он stateless (тот же приём в `handlers.session.session_load`).
    """
    history_writer = EventHistoryWriter()
    for message in messages:
        update = (message.params or {}).get("update", {})
        if not isinstance(update, dict) or update.get("sessionUpdate") != "tool_call_update":
            continue
        tool_call_id = update.get("toolCallId")
        status = update.get("status")
        if not isinstance(tool_call_id, str) or not isinstance(status, str):
            continue
        history_writer.save_tool_call_update(
            session,
            tool_call_id=tool_call_id,
            status=status,
            content=update.get("content"),
        )


def _extract_text_preview(prompt: list[dict[str, Any]]) -> str:
    if not isinstance(prompt, list):
        return "Prompt received"
    for block in prompt:
        if (
            isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        ):
            text = block["text"]
            return text if text else "Prompt received"
    return "Prompt received"


def _extract_full_text(prompt: list[dict[str, Any]]) -> str:
    if not isinstance(prompt, list):
        return ""
    return "\n".join(
        block["text"]
        for block in prompt
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    )


def _build_session_info_notification(session_id: str, summary: dict[str, Any]) -> ACPMessage:
    return ACPMessage.notification(
        "session/update",
        {
            "sessionId": session_id,
            "update": {
                "sessionUpdate": "session_info_update",
                "title": summary.get("title"),
                "updatedAt": summary.get("updated_at"),
            },
        },
    )

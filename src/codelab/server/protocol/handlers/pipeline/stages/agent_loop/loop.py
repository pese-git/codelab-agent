"""AgentLoop — унифицированный цикл итераций LLM tool-calling.

Соответствует ACP 05-Prompt Turn.md:
- loop Until completion (строка 30)
- max_turn_requests stop reason (строка 277-279)
- Tool results back to LLM (строки 261-263)

Архитектурное решение:
- AgentLoop отвечает за цикл итераций, tool-calling, permission
- LLMCallStrategy отвечает за вызов LLM
- Разделение ответственности (SRP)
- Strategy Pattern для разных способов вызова LLM (OCP)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, cast

import structlog

from codelab.server.messages import ACPMessage
from codelab.server.protocol.content.extractor import ContentExtractor
from codelab.server.protocol.content.formatter import ContentFormatter
from codelab.server.protocol.content.validator import ContentValidator
from codelab.server.protocol.handlers.permission_manager import PermissionManager
from codelab.server.protocol.handlers.pipeline.stages.agent_loop.llm_caller import (
    LlmCaller,
    LlmCallResult,
)
from codelab.server.protocol.handlers.pipeline.stages.agent_loop.updates import SessionUpdateSink
from codelab.server.protocol.handlers.plan_builder import PlanBuilder
from codelab.server.protocol.handlers.replay_manager import ReplayManager
from codelab.server.protocol.handlers.state_manager import StateManager
from codelab.server.protocol.handlers.tool_call_handler import ToolCallHandler
from codelab.server.protocol.handlers.tool_policy import decide_tool_policy_async
from codelab.server.protocol.state import SessionState, ToolResult
from codelab.server.protocol.stop_reasons import StopReason
from codelab.server.tools.base import ToolRegistry
from codelab.server.tools.executors.mcp_executor import MCPToolExecutor
from codelab.server.tools.mapping import llm_name_to_acp_name

if TYPE_CHECKING:
    from codelab.server.agent.strategies.base import LLMCallStrategy
    from codelab.server.agent.system_prompt_builder import SystemPromptBuilder
    from codelab.server.mcp.manager import MCPManager
    from codelab.server.protocol.handlers.global_policy_manager import GlobalPolicyManager

logger = structlog.get_logger()


@dataclass
class AgentLoopResult:
    """Результат выполнения AgentLoop.

    Attributes:
        text: Текст ответа агента.
        stop_reason: Причина остановки (ACP stop reason).
        notifications: Список notifications для клиента.
        pending_permission: True если требуется permission.
        pending_tool_calls: Список tool_call_id ожидающих permission.
        tool_results: Список результатов выполнения tools.
    """

    text: str | None = None
    stop_reason: StopReason = StopReason.END_TURN
    notifications: list[ACPMessage] = field(default_factory=list)
    pending_permission: bool = False
    pending_tool_calls: list[str] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)


@dataclass
class ToolProcessingResult:
    """Результат обработки tool calls.

    Внутренний результат для передачи между методами AgentLoop.

    Attributes:
        tool_results: Список результатов выполнения tools.
        pending_permission: True если требуется permission.
        pending_tool_calls: Список tool_call_id ожидающих permission.
    """

    tool_results: list[ToolResult] = field(default_factory=list)
    pending_permission: bool = False
    pending_tool_calls: list[str] = field(default_factory=list)


@dataclass
class _ToolCallStep:
    """Результат обработки одного tool call внутри цикла AgentLoop.

    Attributes:
        tool_result: Результат исполнения (добавляется в общий список); None,
            если tool_call пропущен (без имени).
        pause_tool_call_id: Если задан — цикл ставится на паузу для permission
            по этому tool_call_id.
    """

    tool_result: ToolResult | None = None
    pause_tool_call_id: str | None = None


class AgentLoop:
    """Универсальный цикл итераций LLM tool-calling.

    Соответствует ACP 05-Prompt Turn.md:
    - loop Until completion (строка 30)
    - max_turn_requests stop reason (строка 277-279)
    - Tool results back to LLM (строки 261-263)

    Responsibilities:
    - Цикл итераций (max_turn_requests)
    - Вызов LLM через LLMCallStrategy
    - Обработка tool_calls
    - Permission pause/resume
    - Cancellation handling

    НЕ отвечает за:
    - Вызов LLM (делает LLMCallStrategy)
    - Выполнение tools (делает ToolRegistry)
    - Pipeline integration (делает LLMLoopStage)

    Example:
        loop = AgentLoop(
            strategy=strategy_dispatcher,
            tool_registry=tool_registry,
            ...
        )
        result = await loop.run(session, session_id, "Hello")
        if result.pending_permission:
            # ...等待 permission ...
            result = await loop.resume_after_permission(session, tool_call_id)
    """

    def __init__(
        self,
        strategy: LLMCallStrategy,
        tool_registry: ToolRegistry,
        tool_call_handler: ToolCallHandler,
        permission_manager: PermissionManager,
        state_manager: StateManager,
        content_extractor: ContentExtractor,
        content_validator: ContentValidator,
        content_formatter: ContentFormatter,
        replay_manager: ReplayManager,
        plan_builder: PlanBuilder,
        system_prompt_builder: SystemPromptBuilder,
        global_policy_manager: GlobalPolicyManager | None = None,
        max_turn_requests: int = 10,
        notification_callback: Callable[[ACPMessage], Awaitable[None]] | None = None,
        streaming_enabled: bool = False,
    ) -> None:
        """Инициализация AgentLoop.

        Args:
            strategy: Стратегия вызова LLM (StrategyDispatcher).
            tool_registry: Реестр инструментов для выполнения.
            tool_call_handler: Обработчик tool calls для управления состоянием.
            permission_manager: Менеджер разрешений для permission requests.
            state_manager: Менеджер состояния сессии.
            content_extractor: Извлекатель контента из результатов tools.
            content_validator: Валидатор контента.
            content_formatter: Форматировщик контента для LLM.
            replay_manager: Менеджер replay для сохранения событий.
            plan_builder: Построитель планов выполнения.
            system_prompt_builder: Билдер system prompt (config + MCP info).
            global_policy_manager: Менеджер глобальных политик (опционально).
            max_turn_requests: Максимальное количество запросов к LLM в turn.
            notification_callback: Опциональный callback для немедленной отправки notifications.
                Если задан, notifications отправляются сразу при создании. Если None,
                notifications только накапливаются в списке для backward compatibility.
        """
        self._tool_registry = tool_registry
        self._tool_call_handler = tool_call_handler
        self._permission_manager = permission_manager
        self._state_manager = state_manager
        self._content_extractor = content_extractor
        self._content_validator = content_validator
        self._content_formatter = content_formatter
        self._replay_manager = replay_manager
        self._plan_builder = plan_builder
        self._global_policy_manager = global_policy_manager
        self._max_turn_requests = max_turn_requests
        self._notification_callback = notification_callback
        self._llm_caller = LlmCaller(strategy, system_prompt_builder, streaming_enabled)

    # ── Immediate Notification Delivery ─────────────────────────────────────────
    #
    # Согласно ACP спецификации (05-Prompt Turn.md:169, 08-Tool Calls.md:11),
    # tool calls и их статусы должны репортиться "immediately" для "real-time
    # progress". Особенно критично для terminal embedding (10-Terminal.md:140),
    # где клиент должен отображать "live output as it's generated".
    #
    # Доставка + буферизация + replay инкапсулированы в SessionUpdateSink,
    # который создаётся пер-turn в run()/resume_after_permission().
    # ──────────────────────────────────────────────────────────────────────────────

    def set_notification_callback(
        self, callback: Callable[[ACPMessage], Awaitable[None]] | None
    ) -> None:
        """Обновить callback для немедленной отправки notifications.

        Используется когда AgentLoop переиспользуется между вызовами
        (например, в execute_pending_tool после permission approval).

        Args:
            callback: Новый callback или None для отключения immediate delivery.
        """
        self._notification_callback = callback

    async def run(
        self,
        session: SessionState,
        session_id: str,
        initial_prompt: str | None = None,
        mcp_manager: MCPManager | None = None,
    ) -> AgentLoopResult:
        """Запустить цикл итераций.

        Flow:
        1. Вызов LLM (execute или continue_execution)
        2. Обработка ответа (text, tool_calls, plan)
        3. Если нет tool_calls → завершить
        4. Обработка tool_calls
        5. Если permission required → приостановить
        6. Продолжить цикл

        Args:
            session: Состояние сессии.
            session_id: ID сессии для логирования.
            initial_prompt: Текст начального промпта (None для продолжения).
            mcp_manager: MCP manager для tool execution.

        Returns:
            AgentLoopResult с результатом выполнения.
        """
        notifications: list[ACPMessage] = []
        sink = SessionUpdateSink(self._replay_manager, self._notification_callback, notifications)
        iteration = 0
        final_text: str | None = None

        while iteration < self._max_turn_requests:
            iteration += 1
            result, final_text = await self._run_iteration(
                session,
                session_id,
                initial_prompt,
                mcp_manager,
                iteration,
                sink,
                final_text,
            )
            if result is not None:
                return result
            # Продолжить цикл — prompt=None для continue_execution
            initial_prompt = None

        # Max iterations reached
        logger.warning(
            "agent_loop max_turn_requests reached",
            session_id=session_id,
            max_turn_requests=self._max_turn_requests,
        )
        return AgentLoopResult(
            text=final_text,
            stop_reason=StopReason.MAX_TURN_REQUESTS,
            notifications=notifications,
        )

    async def _run_iteration(
        self,
        session: SessionState,
        session_id: str,
        prompt: str | None,
        mcp_manager: MCPManager | None,
        iteration: int,
        sink: SessionUpdateSink,
        final_text: str | None,
    ) -> tuple[AgentLoopResult | None, str | None]:
        """Одна итерация цикла: LLM-вызов + обработка ответа/tool_calls.

        Returns:
            (terminal_result | None, final_text). None-результат означает
            «продолжать цикл»; final_text прокидывается между итерациями.
        """
        call_result, terminal = await self._obtain_llm_response(
            session, session_id, prompt, mcp_manager, iteration, sink
        )
        if terminal is not None:
            return terminal, final_text

        # Обработка ответа
        response = call_result.response if call_result else None
        streamed = call_result.streamed if call_result else False
        agent_text = response.text if response else ""
        has_tool_calls = bool(response and response.tool_calls)

        logger.debug(
            "llm_response_received",
            session_id=session_id,
            iteration=iteration,
            has_text=bool(agent_text),
            has_tool_calls=has_tool_calls,
            tool_call_count=len(response.tool_calls) if response else 0,
            stop_reason=getattr(response, "stop_reason", None),
        )

        if agent_text:
            final_text = agent_text
            await self._emit_agent_text(session, session_id, agent_text, sink, streamed)

        await self._emit_response_plan(session, session_id, response, sink)

        # Нет tool_calls → завершить
        if not has_tool_calls:
            logger.debug(
                "agent_loop completed - no tool calls",
                session_id=session_id,
                iteration=iteration,
            )
            return (
                AgentLoopResult(
                    text=final_text,
                    stop_reason=StopReason.END_TURN,
                    notifications=sink.notifications,
                ),
                final_text,
            )

        # Обработка tool_calls
        logger.info(
            "agent_loop processing tool calls",
            session_id=session_id,
            iteration=iteration,
            num_tool_calls=len(response.tool_calls),
        )

        # Добавляем tool_calls в историю
        tool_calls_for_history = [
            {"id": tc.id, "name": tc.name, "arguments": tc.arguments} for tc in response.tool_calls
        ]
        session.history.append(
            {
                "role": "assistant",
                "text": agent_text or "",
                "tool_calls": tool_calls_for_history,
            }
        )

        # Обрабатываем tool_calls
        tool_result = await self._process_tool_calls(
            session, session_id, response.tool_calls, sink, mcp_manager
        )

        # Permission pause
        if tool_result.pending_permission:
            logger.debug(
                "agent_loop deferred for permission",
                session_id=session_id,
                iteration=iteration,
            )
            return (
                AgentLoopResult(
                    notifications=sink.notifications,
                    pending_permission=True,
                    pending_tool_calls=tool_result.pending_tool_calls,
                    tool_results=tool_result.tool_results,
                ),
                final_text,
            )

        # Проверка отмены во время tool processing
        if self._is_cancel_requested(session):
            logger.debug(
                "agent_loop cancelled during tool processing",
                session_id=session_id,
                iteration=iteration,
            )
            return (
                AgentLoopResult(
                    notifications=sink.notifications, stop_reason=StopReason.CANCELLED
                ),
                final_text,
            )

        return None, final_text

    async def _obtain_llm_response(
        self,
        session: SessionState,
        session_id: str,
        prompt: str | None,
        mcp_manager: MCPManager | None,
        iteration: int,
        sink: SessionUpdateSink,
    ) -> tuple[LlmCallResult | None, AgentLoopResult | None]:
        """Вызвать LLM с проверками отмены и обработкой ошибки.

        Returns:
            (call_result, None) при успехе; (None, terminal_result) если turn
            отменён или LLM-вызов упал.
        """
        if self._is_cancel_requested(session):
            logger.debug(
                "agent_loop cancelled before LLM call",
                session_id=session_id,
                iteration=iteration,
            )
            return None, AgentLoopResult(
                notifications=sink.notifications, stop_reason=StopReason.CANCELLED
            )

        try:
            call_result = await self._llm_caller.call(
                session, prompt, mcp_manager, iteration, sink
            )
        except Exception as e:
            logger.error(
                "LLM call failed",
                session_id=session_id,
                iteration=iteration,
                error=str(e),
            )
            await sink.emit_agent_message(session_id, str(e))
            return None, AgentLoopResult(
                notifications=sink.notifications, stop_reason=StopReason.END_TURN
            )

        if self._is_cancel_requested(session):
            logger.debug(
                "agent_loop cancelled after LLM call",
                session_id=session_id,
                iteration=iteration,
            )
            return None, AgentLoopResult(
                notifications=sink.notifications, stop_reason=StopReason.CANCELLED
            )

        return call_result, None

    async def _emit_agent_text(
        self,
        session: SessionState,
        session_id: str,
        agent_text: str,
        sink: SessionUpdateSink,
        streamed: bool,
    ) -> None:
        """Добавить текст ассистента в историю, эмитировать (если не стримился), в replay."""
        self._state_manager.add_assistant_message(session, agent_text)
        # При стриминге текст уже доставлен дельтами через on_delta —
        # не эмитим полный текст повторно (иначе дубль). Но если дельт
        # не было (провайдер без стрима) — эмитим полный текст.
        if not streamed:
            await sink.emit_agent_message(session_id, agent_text)
        # Сохранить в events_history для replay при session/load
        # (полный текст одним chunk'ом — авторитетно для реплея).
        sink.save_agent_message_chunk(session, {"type": "text", "text": agent_text})

    async def _emit_response_plan(
        self,
        session: SessionState,
        session_id: str,
        response: Any,
        sink: SessionUpdateSink,
    ) -> None:
        """Эмитировать plan из ответа LLM (response.plan), если он валиден."""
        plan = getattr(response, "plan", None)
        if not plan:
            return
        validated_plan = self._plan_builder.validate_plan_entries(plan)
        if not validated_plan:
            return
        session.latest_plan = list(validated_plan)
        plan_notification = self._plan_builder.build_plan_notification(session_id, validated_plan)
        await sink.emit_and_save_plan(
            plan_notification, session=session, entries=validated_plan
        )

    async def resume_after_permission(
        self,
        session: SessionState,
        session_id: str,
        tool_call_id: str,
        mcp_manager: MCPManager | None = None,
    ) -> AgentLoopResult:
        """Продолжить цикл после permission approval.

        Flow:
        1. Выполнить pending tool
        2. Отправить notification клиенту с content
        3. Продолжить цикл через run()

        Args:
            session: Состояние сессии.
            session_id: ID сессии для логирования.
            tool_call_id: ID tool call для выполнения.
            mcp_manager: MCP manager для tool execution.

        Returns:
            AgentLoopResult с результатом выполнения.
        """
        notifications: list[ACPMessage] = []
        sink = SessionUpdateSink(self._replay_manager, self._notification_callback, notifications)

        # Убедиться что стратегия инициализирована для continue_execution.
        self._llm_caller.ensure_strategy_selected(session, session_id)

        # Выполнить pending tool
        tool_result = await self._execute_pending_tool(
            session, session_id, tool_call_id, mcp_manager
        )

        if tool_result is None:
            return AgentLoopResult(
                notifications=notifications,
                stop_reason=StopReason.END_TURN,
            )

        # Отправить notification клиенту с content (terminal embedding и т.д.)
        status = "completed" if tool_result.success else "failed"
        notification = self._tool_call_handler.build_tool_update_notification(
            session_id=session_id,
            tool_call_id=tool_call_id,
            status=status,
            content=tool_result.content,
        )
        await sink.emit_and_save_tool_update(
            notification,
            session=session,
            tool_call_id=tool_call_id,
            status=status,
            content=tool_result.content,
        )

        logger.info(
            "resume_after_permission: notification built with content",
            session_id=session_id,
            tool_call_id=tool_call_id,
            status=status,
            has_content=tool_result.content is not None,
            content_types=(
                [item.get("type") for item in tool_result.content] if tool_result.content else []
            ),
        )

        # Продолжить цикл (tool_results уже в session.history)
        loop_result = await self.run(
            session=session,
            session_id=session_id,
            initial_prompt=None,
            mcp_manager=mcp_manager,
        )

        # Объединяем notifications
        return AgentLoopResult(
            text=loop_result.text,
            stop_reason=loop_result.stop_reason,
            notifications=notifications + loop_result.notifications,
            pending_permission=loop_result.pending_permission,
            pending_tool_calls=loop_result.pending_tool_calls,
            tool_results=loop_result.tool_results,
        )

    async def _process_tool_calls(
        self,
        session: SessionState,
        session_id: str,
        tool_calls: list,
        sink: SessionUpdateSink,
        mcp_manager: MCPManager | None,
    ) -> ToolProcessingResult:
        """Обработать tool calls из ответа LLM.

        Итерирует по tool calls, делегируя обработку каждого в
        `_process_single_tool_call`. Прерывается на отмене или при запросе
        permission (agent loop ставится на паузу до ответа клиента).

        Args:
            session: Состояние сессии.
            session_id: ID сессии.
            tool_calls: Список tool calls из ответа LLM.
            sink: Канал доставки notifications (+ replay).
            mcp_manager: MCP manager.

        Returns:
            ToolProcessingResult с результатами обработки.
        """
        tool_results: list[ToolResult] = []

        for tool_call in tool_calls:
            if self._is_cancel_requested(session):
                logger.debug("tool processing cancelled", session_id=session_id)
                return ToolProcessingResult(
                    tool_results=tool_results,
                    pending_permission=False,
                )

            step = await self._process_single_tool_call(
                session, session_id, tool_call, sink, mcp_manager
            )
            if step.pause_tool_call_id is not None:
                return ToolProcessingResult(
                    tool_results=tool_results,
                    pending_permission=True,
                    pending_tool_calls=[step.pause_tool_call_id],
                )
            if step.tool_result is not None:
                tool_results.append(step.tool_result)

        return ToolProcessingResult(tool_results=tool_results)

    async def _process_single_tool_call(
        self,
        session: SessionState,
        session_id: str,
        tool_call: object,
        sink: SessionUpdateSink,
        mcp_manager: MCPManager | None,
    ) -> _ToolCallStep:
        """Обработать один tool call: создать, принять решение, исполнить.

        Возвращает `_ToolCallStep`, сигнализирующий вызывающему циклу: либо
        готовый `ToolResult` (продолжить), либо паузу для permission.
        """
        tool_name = getattr(tool_call, "name", None)
        tool_arguments = getattr(tool_call, "arguments", {})
        tool_call_id_from_llm = getattr(tool_call, "id", None)

        if not tool_name:
            logger.warning("tool_call has no name", session_id=session_id)
            return _ToolCallStep()

        # Конвертируем LLM имя обратно в ACP формат
        acp_tool_name = llm_name_to_acp_name(tool_name)

        tool_kind = "other"
        is_mcp = MCPToolExecutor.is_mcp_tool(acp_tool_name)
        tool_definition = self._tool_registry.get(acp_tool_name)
        if tool_definition is not None:
            tool_kind = tool_definition.kind

        tool_call_id = self._tool_call_handler.create_tool_call(
            session=session,
            title=acp_tool_name,
            kind=tool_kind,
            tool_name=acp_tool_name,
            tool_arguments=tool_arguments,
            tool_call_id_from_llm=tool_call_id_from_llm,
        )

        logger.info(
            "tool_call_created",
            session_id=session_id,
            tool_call_id=tool_call_id,
            tool_name=acp_tool_name,
            tool_kind=tool_kind,
            is_mcp=is_mcp,
        )

        tool_call_notification = self._tool_call_handler.build_tool_call_notification(
            session_id=session_id,
            tool_call_id=tool_call_id,
            title=acp_tool_name,
            kind=tool_kind,
        )
        await sink.emit_and_save_tool_call(
            tool_call_notification,
            session=session,
            tool_call_id=tool_call_id,
            title=acp_tool_name,
            kind=tool_kind,
            status="pending",
        )

        logger.info(
            "tool_call_deciding_execution",
            session_id=session_id,
            tool_call_id=tool_call_id,
            tool_name=acp_tool_name,
            tool_kind=tool_kind,
            is_mcp=is_mcp,
        )

        # MCP инструменты всегда требуют разрешения (по умолчанию)
        if is_mcp:
            decision = await self._decide_tool_execution(session, tool_kind)
        elif tool_definition is not None and not tool_definition.requires_permission:
            decision = "allow"
        else:
            decision = await self._decide_tool_execution(session, tool_kind)

        logger.info(
            "tool_execution_decision",
            session_id=session_id,
            tool_call_id=tool_call_id,
            tool_name=acp_tool_name,
            tool_kind=tool_kind,
            is_mcp=is_mcp,
            requires_permission=(tool_definition.requires_permission if tool_definition else None),
            mode=session.config_values.get("mode", "standard"),
            decision=decision,
        )

        if decision == "ask":
            self._pause_for_permission(
                session, session_id, tool_call_id, acp_tool_name, tool_kind, sink
            )
            return _ToolCallStep(pause_tool_call_id=tool_call_id)

        if decision == "reject":
            return _ToolCallStep(
                tool_result=await self._reject_tool_call(
                    session,
                    session_id,
                    tool_call_id,
                    acp_tool_name,
                    tool_kind,
                    tool_call_id_from_llm,
                    sink,
                )
            )

        # decision == "allow"
        return _ToolCallStep(
            tool_result=await self._execute_allowed_tool_call(
                session,
                session_id,
                tool_call_id,
                tool_name,
                acp_tool_name,
                tool_arguments,
                tool_call_id_from_llm,
                is_mcp,
                mcp_manager,
                sink,
            )
        )

    def _pause_for_permission(
        self,
        session: SessionState,
        session_id: str,
        tool_call_id: str,
        acp_tool_name: str,
        tool_kind: str,
        sink: SessionUpdateSink,
    ) -> None:
        """Сформировать permission request и перевести turn в awaiting_permission."""
        tool_call_state = session.tool_calls.get(tool_call_id)
        if tool_call_state is not None:
            permission_msg = self._permission_manager.build_permission_request(
                session,
                session_id,
                tool_call_state.tool_call_id,
                tool_call_state.title,
                tool_kind,
            )
            sink.buffer_only(permission_msg)
            # НЕ отправляем permission request через immediate callback.
            # Он будет отправлен через стандартный механизм outcome.notifications
            # чтобы избежать дублирования и корректной обработки ответа.

            if session.active_turn:
                session.active_turn.phase = "awaiting_permission"
                session.active_turn.permission_tool_call_id = tool_call_id

        logger.info(
            "permission_request_sent_pausing_agent_loop",
            session_id=session_id,
            tool_call_id=tool_call_id,
            tool_name=acp_tool_name,
        )

    async def _reject_tool_call(
        self,
        session: SessionState,
        session_id: str,
        tool_call_id: str,
        acp_tool_name: str,
        tool_kind: str,
        tool_call_id_from_llm: str | None,
        sink: SessionUpdateSink,
    ) -> ToolResult:
        """Отклонить tool call по policy: пометить failed и вернуть ToolResult."""
        logger.info(
            "tool_call_rejected",
            session_id=session_id,
            tool_call_id=tool_call_id,
            tool_name=acp_tool_name,
            tool_kind=tool_kind,
        )
        self._tool_call_handler.update_tool_call_status(session, tool_call_id, "failed")
        rejection_msg = f"Tool execution rejected by policy for {tool_kind}"
        rejection_content = [
            {"type": "content", "content": {"type": "text", "text": rejection_msg}}
        ]
        rejection_notification = self._tool_call_handler.build_tool_update_notification(
            session_id=session_id,
            tool_call_id=tool_call_id,
            status="failed",
            content=rejection_content,
        )
        await sink.emit_and_save_tool_update(
            rejection_notification,
            session=session,
            tool_call_id=tool_call_id,
            status="failed",
            content=rejection_content,
        )
        return ToolResult(
            tool_call_id=tool_call_id_from_llm or tool_call_id,
            tool_name=acp_tool_name,
            success=False,
            error=rejection_msg,
        )

    async def _execute_allowed_tool_call(
        self,
        session: SessionState,
        session_id: str,
        tool_call_id: str,
        tool_name: str,
        acp_tool_name: str,
        tool_arguments: dict,
        tool_call_id_from_llm: str | None,
        is_mcp: bool,
        mcp_manager: MCPManager | None,
        sink: SessionUpdateSink,
    ) -> ToolResult:
        """Исполнить разрешённый tool call и сформировать ToolResult."""
        logger.info(
            "tool_call_executing",
            session_id=session_id,
            tool_call_id=tool_call_id,
            tool_name=acp_tool_name,
            is_mcp=is_mcp,
        )
        try:
            self._tool_call_handler.update_tool_call_status(session, tool_call_id, "in_progress")
            in_progress_notification = self._tool_call_handler.build_tool_update_notification(
                session_id=session_id,
                tool_call_id=tool_call_id,
                status="in_progress",
            )
            await sink.emit_and_save_tool_update(
                in_progress_notification,
                session=session,
                tool_call_id=tool_call_id,
                status="in_progress",
            )

            result = await self._run_tool(
                session, session_id, acp_tool_name, tool_arguments, is_mcp, mcp_manager
            )

            extracted_content = await self._content_extractor.extract_from_result(
                tool_call_id, result
            )

            is_valid, errors = self._content_validator.validate_content_list(
                extracted_content.content_items
            )
            if not is_valid:
                logger.warning(
                    "tool_result_content_validation_failed",
                    tool_call_id=tool_call_id,
                    errors=errors,
                )

            tool_call_state = session.tool_calls.get(tool_call_id)
            if tool_call_state:
                tool_call_state.result_content = extracted_content.content_items

            provider_raw = session.config_values.get("llm_provider", "openai")
            provider = cast(Literal["openai", "anthropic"], provider_raw)
            self._content_formatter.format_for_llm(extracted_content, provider=provider)

            if result.success:
                success_text = result.output or "Success"
                success_content = [
                    {"type": "content", "content": {"type": "text", "text": success_text}}
                ]
                self._tool_call_handler.update_tool_call_status(
                    session, tool_call_id, "completed", content=success_content
                )
                status = "completed"
            else:
                self._tool_call_handler.update_tool_call_status(session, tool_call_id, "failed")
                status = "failed"

            notification_content = self._build_notification_content(extracted_content, result)

            tool_update_notification = self._tool_call_handler.build_tool_update_notification(
                session_id=session_id,
                tool_call_id=tool_call_id,
                status=status,
                content=notification_content,
            )
            await sink.emit_and_save_tool_update(
                tool_update_notification,
                session=session,
                tool_call_id=tool_call_id,
                status=status,
                content=notification_content,
            )

            # Добавляем tool result в историю для LLM
            self._add_tool_result_to_history(
                session,
                tool_call_id_from_llm or tool_call_id,
                result.success,
                result.output,
                result.error,
            )

            await self._emit_plan_notification_if_needed(
                session, session_id, acp_tool_name, result, sink
            )

            return ToolResult(
                tool_call_id=tool_call_id_from_llm or tool_call_id,
                tool_name=acp_tool_name,
                success=result.success,
                output=result.output,
                content=extracted_content.content_items,
                error=result.error,
            )

        except Exception as e:
            logger.error(
                "tool execution failed",
                session_id=session_id,
                tool_name=tool_name,
                error=str(e),
            )
            self._tool_call_handler.update_tool_call_status(session, tool_call_id, "failed")
            # Историческое поведение: notification буферизуется напрямую, минуя
            # immediate callback (в отличие от success-ветки выше).
            sink.buffer_and_save_tool_update(
                self._tool_call_handler.build_tool_update_notification(
                    session_id=session_id,
                    tool_call_id=tool_call_id,
                    status="failed",
                ),
                session=session,
                tool_call_id=tool_call_id,
                status="failed",
            )
            self._add_tool_result_to_history(
                session,
                tool_call_id_from_llm or tool_call_id,
                False,
                None,
                str(e),
            )
            return ToolResult(
                tool_call_id=tool_call_id_from_llm or tool_call_id,
                tool_name=acp_tool_name,
                success=False,
                error=str(e),
            )

    async def _run_tool(
        self,
        session: SessionState,
        session_id: str,
        acp_tool_name: str,
        tool_arguments: dict,
        is_mcp: bool,
        mcp_manager: MCPManager | None,
    ):
        """Исполнить tool через MCP executor или локальный registry."""
        if is_mcp:
            if mcp_manager is None:
                raise RuntimeError("MCP manager not available for session")
            mcp_executor = MCPToolExecutor(mcp_manager)
            return await mcp_executor.execute_tool(
                session_id, acp_tool_name, tool_arguments, session=session
            )
        return await self._tool_registry.execute_tool(
            session_id, acp_tool_name, tool_arguments, session=session
        )

    @staticmethod
    def _build_notification_content(extracted_content, result) -> list | None:
        """Контент для tool_call_update: extracted content с fallback на текст output."""
        if extracted_content.content_items:
            return extracted_content.content_items
        if result.success and result.output:
            return [{"type": "content", "content": {"type": "text", "text": result.output}}]
        return None

    async def _emit_plan_notification_if_needed(
        self,
        session: SessionState,
        session_id: str,
        acp_tool_name: str,
        result,
        sink: SessionUpdateSink,
    ) -> None:
        """Отправить plan notification, если tool update_plan успешно вернул план.

        Соответствует ACP spec (protocol/11-Agent Plan.md).
        """
        if acp_tool_name != "update_plan" or not result.success:
            return
        plan_entries = result.metadata.get("validated_entries") if result.metadata else None
        if not plan_entries:
            return
        session.latest_plan = list(plan_entries)
        plan_notification = self._plan_builder.build_plan_notification(session_id, plan_entries)
        await sink.emit_and_save_plan(plan_notification, session=session, entries=plan_entries)
        logger.debug(
            "plan notification sent from update_plan tool",
            session_id=session_id,
            entries_count=len(plan_entries),
        )

    async def _execute_pending_tool(
        self,
        session: SessionState,
        session_id: str,
        tool_call_id: str,
        mcp_manager: MCPManager | None,
    ) -> ToolResult | None:
        """Выполнить pending tool после permission approval.

        Перенесено из LLMLoopStage.execute_pending_tool.

        Args:
            session: Состояние сессии.
            session_id: ID сессии.
            tool_call_id: ID tool call для выполнения.
            mcp_manager: MCP manager.

        Returns:
            ToolResult или None если tool не найден.
        """
        tool_call_state = session.tool_calls.get(tool_call_id)
        if tool_call_state is None:
            logger.error(
                "tool_call_state not found for pending execution",
                session_id=session_id,
                tool_call_id=tool_call_id,
            )
            return None

        tool_name = tool_call_state.tool_name
        tool_arguments = tool_call_state.tool_arguments
        tool_call_id_from_llm = tool_call_state.tool_call_id_from_llm

        if tool_name is None:
            logger.error(
                "tool_name not found in tool_call_state",
                session_id=session_id,
                tool_call_id=tool_call_id,
            )
            return None

        logger.info(
            "executing pending tool after permission approval",
            session_id=session_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
        )

        try:
            result = await self._run_tool(
                session,
                session_id,
                tool_name,
                tool_arguments,
                MCPToolExecutor.is_mcp_tool(tool_name),
                mcp_manager,
            )

            extracted_content = await self._content_extractor.extract_from_result(
                tool_call_id, result
            )
            tool_call_state.result_content = extracted_content.content_items

            provider_raw = session.config_values.get("llm_provider", "openai")
            provider = cast(Literal["openai", "anthropic"], provider_raw)
            self._content_formatter.format_for_llm(extracted_content, provider=provider)

            notification_content = self._build_notification_content(extracted_content, result)

            if result.success:
                self._tool_call_handler.update_tool_call_status(
                    session, tool_call_id, "completed", content=notification_content
                )
                # Добавляем tool result в историю для LLM
                self._add_tool_result_to_history(
                    session, tool_call_id_from_llm or tool_call_id, True, result.output, None
                )
                return ToolResult(
                    tool_call_id=tool_call_id_from_llm or tool_call_id,
                    tool_name=tool_name,
                    success=True,
                    output=result.output,
                    content=extracted_content.content_items,
                )
            else:
                error_content = [
                    {
                        "type": "content",
                        "content": {
                            "type": "text",
                            "text": result.error or "Tool execution failed",
                        },
                    }
                ]
                self._tool_call_handler.update_tool_call_status(
                    session, tool_call_id, "failed", content=error_content
                )
                # Добавляем tool result в историю для LLM
                self._add_tool_result_to_history(
                    session, tool_call_id_from_llm or tool_call_id, False, None, result.error
                )
                return ToolResult(
                    tool_call_id=tool_call_id_from_llm or tool_call_id,
                    tool_name=tool_name,
                    success=False,
                    error=result.error,
                )

        except Exception as exc:
            logger.error(
                "tool execution failed with exception",
                session_id=session_id,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                error=str(exc),
                exc_info=True,
            )
            error_content = [
                {
                    "type": "content",
                    "content": {"type": "text", "text": f"Tool execution error: {exc}"},
                }
            ]
            self._tool_call_handler.update_tool_call_status(
                session, tool_call_id, "failed", content=error_content
            )
            # Добавляем tool result в историю для LLM
            self._add_tool_result_to_history(
                session, tool_call_id_from_llm or tool_call_id, False, None, str(exc)
            )
            return ToolResult(
                tool_call_id=tool_call_id_from_llm or tool_call_id,
                tool_name=tool_name,
                success=False,
                error=str(exc),
            )

    def _add_tool_result_to_history(
        self,
        session: SessionState,
        tool_call_id: str,
        success: bool,
        output: str | None,
        error: str | None,
    ) -> None:
        """Добавить результат выполнения tool в историю сессии.

        Формат соответствует OpenAI API для tool response messages:
          {"role": "tool", "tool_call_id": "...", "content": "..."}

        Args:
            session: Состояние сессии (мутируется).
            tool_call_id: ID tool call.
            success: Успешно ли выполнен tool.
            output: Выход tool (если успешен).
            error: Ошибка (если не успешен).
        """
        content = output if success else (error or "Tool execution failed")

        session.history.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": content or "",
            }
        )

        logger.debug(
            "tool_result_added_to_history",
            session_id=session.session_id,
            tool_call_id=tool_call_id,
            success=success,
        )

    async def _decide_tool_execution(self, session: SessionState, tool_kind: str) -> str:
        """Определить решение о выполнении tool.

        Делегирует единой логике в ToolPolicyDecider.

        Args:
            session: Состояние сессии.
            tool_kind: Тип инструмента.

        Returns:
            "allow", "reject" или "ask".
        """
        return await decide_tool_policy_async(session, tool_kind, self._global_policy_manager)

    def _is_cancel_requested(self, session: SessionState) -> bool:
        """Проверить флаг отмены."""
        return session.active_turn is not None and session.active_turn.cancel_requested

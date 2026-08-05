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
from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.domain.tool_call import ToolCall as DomainToolCall
from codelab.server.messages import ACPMessage
from codelab.server.protocol.content.extractor import ContentExtractor
from codelab.server.protocol.content.validator import ContentValidator
from codelab.server.protocol.handlers.event_history_writer import EventHistoryWriter
from codelab.server.protocol.handlers.permission_manager import PermissionManager
from codelab.server.protocol.handlers.pipeline.stages.agent_loop.llm_caller import (
    LlmCaller,
    LlmCallResult,
)
from codelab.server.protocol.handlers.pipeline.stages.agent_loop.tool_processor import (
    ToolCallProcessor,
    ToolProcessingResult,
)
from codelab.server.protocol.handlers.pipeline.stages.agent_loop.updates import SessionUpdateSink
from codelab.server.protocol.handlers.plan_builder import PlanBuilder
from codelab.server.protocol.handlers.state_manager import StateManager
from codelab.server.protocol.handlers.tool_call_handler import ToolCallHandler
from codelab.server.protocol.session_commands import SessionCommands
from codelab.server.protocol.state import ToolResult
from codelab.server.protocol.stop_reasons import StopReason
from codelab.server.protocol.turn_cancellation import TurnCancellationRegistry
from codelab.server.tools.base import ToolRegistry

if TYPE_CHECKING:
    from codelab.server.agent.core.strategies.base import LLMCallStrategy
    from codelab.server.agent.core.system_prompt_builder import SystemPromptBuilder
    from codelab.server.domain.session import Session
    from codelab.server.mcp.manager import MCPManager
    from codelab.server.protocol.handlers.global_policy_manager import GlobalPolicyManager

logger = structlog.get_logger()

__all__ = ["AgentLoop", "AgentLoopResult", "StopReason", "ToolProcessingResult", "ToolResult"]


class _DeferredToolCall:
    """Восстановленный из `pending_batch` tool call.

    `process_batch` читает вызовы как объекты с `.id/.name/.arguments`, а в
    состоянии turn'а хвост лежит словарями (он уезжает на диск), поэтому нужен
    тонкий адаптер, а не второй путь обработки (P2-40).
    """

    __slots__ = ("id", "name", "arguments")

    def __init__(self, call: dict[str, Any]) -> None:
        self.id = call.get("id")
        self.name = call.get("name")
        self.arguments = call.get("arguments") or {}


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
        history_writer: EventHistoryWriter,
        plan_builder: PlanBuilder,
        system_prompt_builder: SystemPromptBuilder,
        global_policy_manager: GlobalPolicyManager | None = None,
        max_turn_requests: int = 10,
        notification_callback: Callable[[ACPMessage], Awaitable[None]] | None = None,
        streaming_enabled: bool = False,
        loop_guard_limit: int = 3,
        turn_cancellation: TurnCancellationRegistry | None = None,
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
            history_writer: Писатель events_history.
            plan_builder: Построитель планов выполнения.
            system_prompt_builder: Билдер system prompt (config + MCP info).
            global_policy_manager: Менеджер глобальных политик (опционально).
            max_turn_requests: Максимальное количество запросов к LLM в turn.
            notification_callback: Опциональный callback для немедленной отправки notifications.
                Если задан, notifications отправляются сразу при создании. Если None,
                notifications только накапливаются в списке для backward compatibility.
        """
        self._tool_call_handler = tool_call_handler
        self._state_manager = state_manager
        self._history_writer = history_writer
        self._plan_builder = plan_builder
        self._max_turn_requests = max_turn_requests
        self._notification_callback = notification_callback
        self._llm_caller = LlmCaller(strategy, system_prompt_builder, streaming_enabled)
        self._turn_cancellation = turn_cancellation
        self._tool_processor = ToolCallProcessor(
            tool_registry=tool_registry,
            tool_call_handler=tool_call_handler,
            permission_manager=permission_manager,
            content_extractor=content_extractor,
            content_validator=content_validator,
            plan_builder=plan_builder,
            global_policy_manager=global_policy_manager,
            loop_guard_limit=loop_guard_limit,
            turn_cancellation=turn_cancellation,
        )

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
        commands: SessionCommands,
        session_id: str,
        initial_prompt: str | None = None,
        mcp_manager: MCPManager | None = None,
        started_epoch: int | None = None,
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
            commands: Шов команд над сессией — единственный путь записи состояния.
            session_id: ID сессии для логирования.
            initial_prompt: Текст начального промпта (None для продолжения).
            mcp_manager: MCP manager для tool execution.
            started_epoch: Поколение отмены для сверки. `None` — новый turn, берём
                текущее. Resume-путь передаёт своё: иначе он взял бы за базу уже
                изменённое отменой поколение и не заметил бы её (P0-39).

        Returns:
            AgentLoopResult с результатом выполнения.
        """
        notifications: list[ACPMessage] = []
        sink = SessionUpdateSink(
            self._history_writer, self._notification_callback, notifications, commands
        )
        iteration = 0
        final_text: str | None = None
        # Поколение отмены на входе в turn: сигнал живёт в процессном реестре, а не
        # в копии сессии, поэтому виден идущему turn'у (P0-39).
        if started_epoch is None:
            started_epoch = self._cancellation_generation(session_id)

        while iteration < self._max_turn_requests:
            iteration += 1
            result, final_text = await self._run_iteration(
                commands,
                session_id,
                initial_prompt,
                mcp_manager,
                iteration,
                sink,
                final_text,
                started_epoch,
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
        commands: SessionCommands,
        session_id: str,
        prompt: str | None,
        mcp_manager: MCPManager | None,
        iteration: int,
        sink: SessionUpdateSink,
        final_text: str | None,
        started_epoch: int,
    ) -> tuple[AgentLoopResult | None, str | None]:
        """Одна итерация цикла: LLM-вызов + обработка ответа/tool_calls.

        Returns:
            (terminal_result | None, final_text). None-результат означает
            «продолжать цикл»; final_text прокидывается между итерациями.
        """
        session = commands.session
        call_result, terminal = await self._obtain_llm_response(
            session, session_id, prompt, mcp_manager, iteration, sink, started_epoch
        )
        # terminal и call_result взаимоисключающи: успех даёт call_result,
        # отмена/ошибка — terminal.
        if terminal is not None or call_result is None:
            return terminal, final_text

        # Обработка ответа
        response = call_result.response
        streamed = call_result.streamed
        agent_text = response.text
        has_tool_calls = bool(response.tool_calls)

        logger.debug(
            "llm_response_received",
            session_id=session_id,
            iteration=iteration,
            has_text=bool(agent_text),
            has_tool_calls=has_tool_calls,
            tool_call_count=len(response.tool_calls),
            stop_reason=getattr(response, "stop_reason", None),
        )

        if agent_text:
            final_text = agent_text
            await self._emit_agent_text(commands, session_id, agent_text, sink, streamed)

        await self._emit_response_plan(session_id, response, sink)

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

        # Запись «ассистент + запрошенные им tool_calls» — доменный сейм. Раньше
        # писалась сырым dict'ом мимо носителя, из-за чего одна и та же запись
        # существовала в двух формах и сравнение по префиксу ломалось на первой же
        # записи turn'а (корень P1-45).
        requested_calls = [
            DomainToolCall(id=tc.id, tool_name=tc.name, arguments=tc.arguments)
            for tc in response.tool_calls
        ]
        await commands.apply(
            lambda target: target.add_assistant_tool_call_message(
                agent_text or "", requested_calls
            ),
            name="assistant_tool_call_message",
        )

        # Обрабатываем tool_calls
        tool_result = await self._tool_processor.process_batch(
            commands, session_id, response.tool_calls, sink, mcp_manager, started_epoch
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
        if self._is_cancel_requested(session, started_epoch, session_id):
            logger.debug(
                "agent_loop cancelled during tool processing",
                session_id=session_id,
                iteration=iteration,
            )
            return (
                AgentLoopResult(notifications=sink.notifications, stop_reason=StopReason.CANCELLED),
                final_text,
            )

        return None, final_text

    async def _obtain_llm_response(
        self,
        session: Session,
        session_id: str,
        prompt: str | None,
        mcp_manager: MCPManager | None,
        iteration: int,
        sink: SessionUpdateSink,
        started_epoch: int,
    ) -> tuple[LlmCallResult | None, AgentLoopResult | None]:
        """Вызвать LLM с проверками отмены и обработкой ошибки.

        Returns:
            (call_result, None) при успехе; (None, terminal_result) если turn
            отменён или LLM-вызов упал.
        """
        if self._is_cancel_requested(session, started_epoch, session_id):
            logger.debug(
                "agent_loop cancelled before LLM call",
                session_id=session_id,
                iteration=iteration,
            )
            return None, AgentLoopResult(
                notifications=sink.notifications, stop_reason=StopReason.CANCELLED
            )

        try:
            call_result = await self._llm_caller.call(session, prompt, mcp_manager, iteration, sink)
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

        if self._is_cancel_requested(session, started_epoch, session_id):
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
        commands: SessionCommands,
        session_id: str,
        agent_text: str,
        sink: SessionUpdateSink,
        streamed: bool,
    ) -> None:
        """Добавить текст ассистента в историю, эмитировать (если не стримился), в replay."""
        await commands.apply(
            lambda session: self._state_manager.add_assistant_message(session, agent_text),
            name="assistant_message",
        )
        # При стриминге текст уже доставлен дельтами через on_delta —
        # не эмитим полный текст повторно (иначе дубль). Но если дельт
        # не было (провайдер без стрима) — эмитим полный текст.
        if not streamed:
            await sink.emit_agent_message(session_id, agent_text)
        # Сохранить в events_history для replay при session/load
        # (полный текст одним chunk'ом — авторитетно для реплея).
        await sink.save_agent_message_chunk({"type": "text", "text": agent_text})

    async def _emit_response_plan(
        self,
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
        # План пишет sink.emit_and_save_plan — единый писатель плана в turn-пути.
        plan_notification = self._plan_builder.build_plan_notification(session_id, validated_plan)
        await sink.emit_and_save_plan(plan_notification, entries=validated_plan)

    async def resume_after_permission(
        self,
        commands: SessionCommands,
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
            commands: Шов команд над сессией — единственный путь записи состояния.
            session_id: ID сессии для логирования.
            tool_call_id: ID tool call для выполнения.
            mcp_manager: MCP manager для tool execution.

        Returns:
            AgentLoopResult с результатом выполнения.
        """
        session = commands.session
        notifications: list[ACPMessage] = []
        sink = SessionUpdateSink(
            self._history_writer, self._notification_callback, notifications, commands
        )

        # Поколение на входе в resume: отмена может прийти, пока pending tool
        # исполняется (например, во время клиентского RPC). Без своей базы отсчёта
        # `run()` ниже взял бы уже изменённое поколение и продолжил отменённый
        # turn — именно так дефект и выживал (P0-39).
        started_epoch = self._cancellation_generation(session_id)

        # Убедиться что стратегия инициализирована для continue_execution.
        self._llm_caller.ensure_strategy_selected(session, session_id)

        # Выполнить pending tool
        tool_result = await self._tool_processor.execute_pending(
            commands, session_id, tool_call_id, mcp_manager
        )

        if tool_result is None:
            return AgentLoopResult(
                notifications=notifications,
                stop_reason=StopReason.END_TURN,
            )

        # Отправить notification клиенту с content (terminal embedding и т.д.).
        # Статус берём из состояния, а не пересчитываем из `success`: его только что
        # проставил `execute_pending` по матрице переходов, и он различает отмену
        # пользователем (`cancelled`) от сбоя инструмента (P2-50). Пересчёт здесь
        # разошёлся бы с диском — тот самый инвариант «последний статус в
        # events_history = статус в tool_calls», который мы сверяем на прогонах.
        # Нетерминальный статус в состоянии означает, что писатель до него не дошёл;
        # отдать клиенту `pending` как итог исполнения нельзя — тогда лучше вывод из
        # `success`, чем заведомо неверная «незавершённость».
        stored_call = session.tool_calls.get(tool_call_id)
        stored_status = stored_call.status.value if stored_call is not None else None
        status = (
            stored_status
            if stored_status in {"completed", "failed", "cancelled"}
            else ("completed" if tool_result.success else "failed")
        )
        notification = self._tool_call_handler.build_tool_update_notification(
            session_id=session_id,
            tool_call_id=tool_call_id,
            status=status,
            content=tool_result.content,
        )
        await sink.emit_and_save_tool_update(
            notification,
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

        # Отмена во время выполнения pending tool: продолжать turn нельзя.
        if self._is_cancel_requested(session, started_epoch, session_id):
            logger.info(
                "resume_after_permission cancelled: turn was cancelled during tool execution",
                session_id=session_id,
                tool_call_id=tool_call_id,
            )
            return AgentLoopResult(
                notifications=notifications,
                stop_reason=StopReason.CANCELLED,
            )

        # Доработать остаток батча, отложенный паузой на permission (P2-40).
        # Только после него имеет смысл идти к модели: иначе она увидит ответы не на
        # все свои вызовы и запросит их снова.
        batch_result = await self._process_deferred_batch(
            commands, session_id, sink, mcp_manager, started_epoch
        )
        if batch_result is not None:
            return AgentLoopResult(
                notifications=notifications,
                pending_permission=batch_result.pending_permission,
                pending_tool_calls=batch_result.pending_tool_calls,
                tool_results=batch_result.tool_results,
            )

        # Продолжить цикл (tool_results уже в session.history)
        loop_result = await self.run(
            commands=commands,
            session_id=session_id,
            initial_prompt=None,
            mcp_manager=mcp_manager,
            started_epoch=started_epoch,
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

    async def _process_deferred_batch(
        self,
        commands: SessionCommands,
        session_id: str,
        sink: SessionUpdateSink,
        mcp_manager: MCPManager | None,
        started_epoch: int,
    ) -> ToolProcessingResult | None:
        """Обработать остаток батча, отложенный предыдущей паузой на permission.

        Возвращает результат, если обработка снова встала на разрешении (тогда цикл
        останавливается до следующего resume), и `None`, если хвост исчерпан и можно
        идти к модели.
        """
        session = commands.session
        if session.active_turn is None or not session.active_turn.pending_batch:
            return None

        deferred = [_DeferredToolCall(call) for call in session.active_turn.pending_batch]

        # Снимаем хвост командой, до обработки: очередная пауза положит сюда свой
        # остаток, а несохранённое снятие вернуло бы батч к повторному исполнению
        # на следующем resume.
        def _take_batch(target: Session) -> None:
            if target.active_turn is not None:
                target.active_turn.pending_batch = []

        await commands.require_active_turn(_take_batch, name="deferred_batch_taken")
        logger.info(
            "resuming_deferred_tool_calls",
            session_id=session_id,
            count=len(deferred),
        )

        result = await self._tool_processor.process_batch(
            commands, session_id, deferred, sink, mcp_manager, started_epoch
        )
        if result.pending_permission:
            return result
        return None

    def _cancellation_generation(self, session_id: str) -> int:
        """Текущее поколение отмены сессии (0, если реестр не подключён)."""
        if self._turn_cancellation is None:
            return 0
        return self._turn_cancellation.generation(session_id)

    def _is_cancel_requested(
        self, session: Session, started_epoch: int, session_id: str | None = None
    ) -> bool:
        """Проверить отмену: поколение в процессном реестре либо флаг в `active_turn`.

        Реестр — основной источник: у каждого запроса своя копия сессии, поэтому
        запись отмены в состояние идущий turn не видит (P0-39). Флаг оставлен
        вторым источником — он часть ACP-состояния turn'а.
        """
        if session_id is not None and self._cancellation_generation(session_id) != started_epoch:
            return True
        return session.active_turn is not None and session.active_turn.cancel_requested

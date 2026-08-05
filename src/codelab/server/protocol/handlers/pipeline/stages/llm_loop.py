"""LLMLoopStage — тонкий адаптер pipeline → AgentLoop.

Responsibilities:
- Создание AgentLoop с нужной стратегией (лениво)
- Интеграция с pipeline (PromptContext → AgentLoopResult → PromptContext)

НЕ отвечает за:
- Цикл итераций (делает AgentLoop)
- Вызов LLM (делает LLMCallStrategy)
- Обработку tool_calls (делает AgentLoop)

Архитектурное решение:
- Strategy Pattern — выбор стратегии через LLMCallStrategy
- Single Responsibility — LLMLoopStage только адаптер
- Open/Closed — добавление стратегии не требует изменения LLMLoopStage
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.mapping.session_view import DomainSessionView
from codelab.server.messages import ACPMessage
from codelab.server.protocol.content.extractor import ContentExtractor
from codelab.server.protocol.content.validator import ContentValidator
from codelab.server.protocol.handlers.event_history_writer import EventHistoryWriter
from codelab.server.protocol.handlers.pipeline.stages.agent_loop import AgentLoop
from codelab.server.protocol.handlers.pipeline.stages.agent_loop.updates import SessionUpdateSink
from codelab.server.protocol.session_commands import SessionCommands
from codelab.server.protocol.stop_reasons import StopReason
from codelab.server.protocol.turn_cancellation import TurnCancellationRegistry

from ..base import PromptStage
from ..context import PromptContext

if TYPE_CHECKING:
    from codelab.server.agent.core.strategies.base import LLMCallStrategy
    from codelab.server.agent.core.strategies.dispatcher import StrategyDispatcher
    from codelab.server.agent.core.system_prompt_builder import SystemPromptBuilder
    from codelab.server.domain.session import Session as DomainSession
    from codelab.server.observability.tracer import Tracer
    from codelab.server.protocol.handlers.global_policy_manager import GlobalPolicyManager
    from codelab.server.protocol.handlers.permission_manager import PermissionManager
    from codelab.server.protocol.handlers.plan_builder import PlanBuilder
    from codelab.server.protocol.handlers.state_manager import StateManager
    from codelab.server.protocol.handlers.tool_call_handler import ToolCallHandler
    from codelab.server.protocol.state import LLMLoopResult
    from codelab.server.tools.base import ToolRegistry

logger = structlog.get_logger()


class LLMLoopStage(PromptStage):
    """Тонкий адаптер pipeline → AgentLoop.

    Поддерживает один путь выполнения через LLMCallStrategy:
    - EventBus: через StrategyDispatcher → SingleStrategy → LLMAdapter

    Стратегия выбирается лениво при первом вызове process().

    Example:
        stage = LLMLoopStage(
            tool_registry=tool_registry,
            strategy_dispatcher=strategy_dispatcher,  # EventBus путь
            ...
        )
        result = await stage.process(context)
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        tool_call_handler: ToolCallHandler,
        permission_manager: PermissionManager,
        state_manager: StateManager,
        plan_builder: PlanBuilder,
        system_prompt_builder: SystemPromptBuilder,
        global_policy_manager: GlobalPolicyManager | None = None,
        strategy_dispatcher: StrategyDispatcher | None = None,
        tracer: Tracer | None = None,
        streaming_enabled: bool = False,
        loop_guard_limit: int = 3,
        turn_cancellation: TurnCancellationRegistry | None = None,
    ) -> None:
        """Инициализация LLMLoopStage.

        Args:
            tool_registry: Реестр инструментов для выполнения.
            tool_call_handler: Обработчик tool calls для управления состоянием.
            permission_manager: Менеджер разрешений для permission requests.
            state_manager: Менеджер состояния сессии.
            plan_builder: Построитель планов выполнения.
            system_prompt_builder: Билдер system prompt (config + MCP info).
            global_policy_manager: Менеджер глобальных политик (опционально).
            strategy_dispatcher: StrategyDispatcher для EventBus пути (обязательно).
            tracer: Tracer для observability (опционально).
        """
        self._tool_registry = tool_registry
        self._tool_call_handler = tool_call_handler
        self._permission_manager = permission_manager
        self._state_manager = state_manager
        self._plan_builder = plan_builder
        self._system_prompt_builder = system_prompt_builder
        self._global_policy_manager = global_policy_manager
        self._strategy_dispatcher = strategy_dispatcher
        self._tracer = tracer
        self._streaming_enabled = streaming_enabled
        self._loop_guard_limit = loop_guard_limit
        self._turn_cancellation = turn_cancellation

        # Компоненты для AgentLoop
        self._content_extractor = ContentExtractor()
        self._content_validator = ContentValidator()
        self._history_writer = EventHistoryWriter()

        # Лениво создаваемый AgentLoop
        self._agent_loop: AgentLoop | None = None
        self._strategy_selected: bool = False

        strategy_name = "event_bus" if strategy_dispatcher else "legacy"
        logger.info(
            "LLMLoopStage initialized",
            strategy=strategy_name,
            tracer_enabled=tracer is not None,
        )

    async def _get_or_create_agent_loop(
        self,
        context: PromptContext,
        notification_callback: Callable[[ACPMessage], Awaitable[None]] | None = None,
    ) -> AgentLoop:
        """Лениво создать AgentLoop с нужной стратегией.

        Стратегия выбирается один раз и фиксируется через set_current_strategy,
        чтобы continue_execution мог использовать ту же стратегию.

        Args:
            context: Контекст pipeline (session, meta).
            notification_callback: Опциональный callback для немедленной отправки notifications.

        Returns:
            AgentLoop с нужной стратегией.

        Raises:
            ValueError: Если стратегия не доступна.
        """
        if self._agent_loop is not None:
            logger.info(
                "reusing_existing_agentLoop",
                session_id=context.session_id,
                has_callback=notification_callback is not None,
            )
            return self._agent_loop

        if self._strategy_dispatcher is None:
            raise ValueError(
                "StrategyDispatcher not configured. "
                "LLMLoopStage requires strategy_dispatcher to be set."
            )

        # Выбрать и зафиксировать стратегию ДО создания AgentLoop.
        # Это гарантирует что _current_strategy_name установлен для continue_execution.
        if not self._strategy_selected:
            strategy_name, fallback_from = self._strategy_dispatcher.select_strategy(
                session=DomainSessionView(context.session),
                context_meta=context.meta,
            )

            if fallback_from is not None:
                fallback_text = self._strategy_dispatcher.build_fallback_text(
                    requested=fallback_from,
                    actual=strategy_name,
                    reason="strategy not available",
                )
                fallback_notification = SessionUpdateSink.build_agent_message_chunk(
                    context.session_id, fallback_text
                )
                # Уведомление доставляется НЕМЕДЛЕННО через callback; буфер —
                # только fallback при отсутствии callback (не батчить в конце turn'а).
                if notification_callback is not None:
                    await notification_callback(fallback_notification)
                else:
                    context.notifications.append(fallback_notification)
                logger.warning(
                    "strategy fallback",
                    requested=fallback_from,
                    actual=strategy_name,
                    session_id=context.session_id,
                )

            self._strategy_dispatcher.set_current_strategy(strategy_name)
            self._strategy_selected = True

        logger.info(
            "creating_new_AgentLoop",
            session_id=context.session_id,
            has_callback=notification_callback is not None,
        )
        self._agent_loop = self._build_agent_loop(self._strategy_dispatcher, notification_callback)
        return self._agent_loop

    def _build_agent_loop(
        self,
        strategy: LLMCallStrategy,
        notification_callback: Callable[[ACPMessage], Awaitable[None]] | None,
    ) -> AgentLoop:
        """Собрать AgentLoop с общими зависимостями stage.

        Единая точка сборки для process() и fallback в execute_pending_tool —
        устраняет дублирование списка зависимостей.
        """
        return AgentLoop(
            strategy=strategy,
            tool_registry=self._tool_registry,
            tool_call_handler=self._tool_call_handler,
            permission_manager=self._permission_manager,
            state_manager=self._state_manager,
            content_extractor=self._content_extractor,
            content_validator=self._content_validator,
            history_writer=self._history_writer,
            plan_builder=self._plan_builder,
            system_prompt_builder=self._system_prompt_builder,
            global_policy_manager=self._global_policy_manager,
            notification_callback=notification_callback,
            streaming_enabled=self._streaming_enabled,
            loop_guard_limit=self._loop_guard_limit,
            turn_cancellation=self._turn_cancellation,
        )

    async def process(self, context: PromptContext) -> PromptContext:
        """Обработать prompt через AgentLoop.

        Args:
            context: Контекст pipeline.

        Returns:
            Обновлённый контекст с результатами.
        """
        # Demo mode: нет LLM стратегии
        if self._strategy_dispatcher is None:
            if context.raw_text:
                ack_text = f"ACK: {context.raw_text[:80]}"
                ack_content = {"type": "text", "text": ack_text}
                from codelab.server.messages import ACPMessage

                context.notifications.append(
                    ACPMessage.notification(
                        "session/update",
                        {
                            "sessionId": context.session_id,
                            "update": {
                                "sessionUpdate": "agent_message_chunk",
                                "content": ack_content,
                            },
                        },
                    )
                )
                def _ack(target: DomainSession) -> None:
                    self._history_writer.save_agent_message_chunk(target, ack_content)
                    self._state_manager.add_assistant_message(target, ack_text)

                await context.commands.apply(_ack, name="demo_ack")
            return context

        agent_loop = await self._get_or_create_agent_loop(
            context,
            notification_callback=context.meta.get("notification_callback"),
        )
        mcp_manager = self._get_mcp_manager(context)

        result = await agent_loop.run(
            commands=context.commands,
            session_id=context.session_id,
            initial_prompt=context.raw_text,
            mcp_manager=mcp_manager,
        )

        context.notifications.extend(result.notifications)
        context.stop_reason = result.stop_reason or StopReason.END_TURN
        context.pending_permission = result.pending_permission

        if result.pending_permission:
            context.should_stop = True

        return context

    async def execute_pending_tool(
        self,
        commands: SessionCommands,
        session_id: str,
        tool_call_id: str,
        mcp_manager: Any | None = None,
        notification_callback: Callable[[ACPMessage], Awaitable[None]] | None = None,
    ) -> LLMLoopResult:
        """Выполнить pending tool после permission approval.

        Переиспользует существующий AgentLoop (с той же стратегией, что и при process()).
        Если AgentLoop ещё не создан, создаёт его с правильной стратегией.

        Args:
            commands: Шов команд над сессией — единственный путь записи состояния.
            session_id: ID сессии.
            tool_call_id: ID tool call для выполнения.
            mcp_manager: MCP manager для tool execution.
            notification_callback: Опциональный callback для немедленной отправки notifications.

        Returns:
            LLMLoopResult с результатами выполнения.
        """
        session = commands.session
        # Отменённый turn возобновлять нельзя. Отмена очищает `active_turn`, поэтому
        # его отсутствие здесь и означает «turn, к которому относился этот вызов,
        # больше не существует». Раньше проверки не было вовсе, и каждое разрешение
        # толкало отменённый turn дальше — на живом прогоне 8 запросов разрешения
        # уже после отмены (P0-39).
        if session.active_turn is None:
            from codelab.server.protocol.state import LLMLoopResult

            logger.info(
                "pending tool not executed: turn is gone",
                session_id=session_id,
                tool_call_id=tool_call_id,
            )
            return LLMLoopResult(notifications=[], stop_reason=StopReason.CANCELLED)

        # Переиспользовать существующий AgentLoop или создать новый с правильной стратегией
        if self._agent_loop is None:
            logger.info(
                "creating new AgentLoop with callback",
                session_id=session_id,
                has_callback=notification_callback is not None,
            )
            # Fallback: создать AgentLoop с правильной стратегией
            strategy: LLMCallStrategy
            if self._strategy_dispatcher is not None:
                # Выбрать стратегию через dispatcher (без context_meta для pending tool)
                strategy_name, _ = self._strategy_dispatcher.select_strategy(
                    session=DomainSessionView(session),
                    context_meta=None,
                )
                self._strategy_dispatcher.set_current_strategy(strategy_name)
                strategy = self._strategy_dispatcher
            else:
                logger.error(
                    "No LLM strategy available for execute_pending_tool",
                    session_id=session_id,
                )
                from codelab.server.protocol.state import LLMLoopResult

                return LLMLoopResult(notifications=[], stop_reason="end_turn")

            self._agent_loop = self._build_agent_loop(strategy, notification_callback)
        else:
            # Обновить callback в существующем AgentLoop для немедленной отправки notifications
            if notification_callback is not None:
                self._agent_loop.set_notification_callback(notification_callback)
                logger.info(
                    "updated notification_callback in existing AgentLoop",
                    session_id=session_id,
                )
            else:
                logger.warning(
                    "notification_callback is None in execute_pending_tool",
                    session_id=session_id,
                )

        # Использовать AgentLoop.resume_after_permission
        result = await self._agent_loop.resume_after_permission(
            commands=commands,
            session_id=session_id,
            tool_call_id=tool_call_id,
            mcp_manager=mcp_manager,
        )

        # Конвертировать AgentLoopResult → LLMLoopResult
        from codelab.server.protocol.state import LLMLoopResult

        stop_reason = (
            result.stop_reason.value
            if isinstance(result.stop_reason, StopReason)
            else result.stop_reason
        )
        return LLMLoopResult(
            notifications=result.notifications,
            stop_reason=stop_reason,
            pending_permission=result.pending_permission,
            pending_tool_calls=result.pending_tool_calls,
            tool_results=result.tool_results,
        )

    def _get_mcp_manager(self, context: PromptContext):
        """Получить MCP manager из PromptContext.meta."""
        return context.meta.get("mcp_manager")

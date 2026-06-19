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

from codelab.server.messages import ACPMessage
from codelab.server.protocol.content.extractor import ContentExtractor
from codelab.server.protocol.content.formatter import ContentFormatter
from codelab.server.protocol.content.validator import ContentValidator
from codelab.server.protocol.handlers.pipeline.stages.agent_loop import AgentLoop
from codelab.server.protocol.handlers.replay_manager import ReplayManager
from codelab.server.protocol.stop_reasons import StopReason

from ..base import PromptStage
from ..context import PromptContext

if TYPE_CHECKING:
    from codelab.server.agent.strategies.base import LLMCallStrategy
    from codelab.server.agent.strategies.dispatcher import StrategyDispatcher
    from codelab.server.agent.system_prompt_builder import SystemPromptBuilder
    from codelab.server.observability.tracer import Tracer
    from codelab.server.protocol.handlers.global_policy_manager import GlobalPolicyManager
    from codelab.server.protocol.handlers.permission_manager import PermissionManager
    from codelab.server.protocol.handlers.plan_builder import PlanBuilder
    from codelab.server.protocol.handlers.state_manager import StateManager
    from codelab.server.protocol.handlers.tool_call_handler import ToolCallHandler
    from codelab.server.protocol.state import LLMLoopResult, SessionState
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

        # Компоненты для AgentLoop
        self._content_extractor = ContentExtractor()
        self._content_validator = ContentValidator()
        self._content_formatter = ContentFormatter()
        self._replay_manager = ReplayManager()

        # Лениво создаваемый AgentLoop
        self._agent_loop: AgentLoop | None = None
        self._strategy_selected: bool = False

        strategy_name = "event_bus" if strategy_dispatcher else "legacy"
        logger.info(
            "LLMLoopStage initialized",
            strategy=strategy_name,
            tracer_enabled=tracer is not None,
        )

    def _get_or_create_agent_loop(
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
                session=context.session,
                context_meta=context.meta,
            )

            if fallback_from is not None:
                fallback_notification = self._strategy_dispatcher.build_fallback_notification(
                    session_id=context.session_id,
                    requested=fallback_from,
                    actual=strategy_name,
                    reason="strategy not available",
                )
                context.notifications.append(fallback_notification)
                logger.warning(
                    "strategy fallback",
                    requested=fallback_from,
                    actual=strategy_name,
                    session_id=context.session_id,
                )

            self._strategy_dispatcher.set_current_strategy(strategy_name)
            self._strategy_selected = True

        self._agent_loop = AgentLoop(
            strategy=self._strategy_dispatcher,
            tool_registry=self._tool_registry,
            tool_call_handler=self._tool_call_handler,
            permission_manager=self._permission_manager,
            state_manager=self._state_manager,
            content_extractor=self._content_extractor,
            content_validator=self._content_validator,
            content_formatter=self._content_formatter,
            replay_manager=self._replay_manager,
            plan_builder=self._plan_builder,
            system_prompt_builder=self._system_prompt_builder,
            global_policy_manager=self._global_policy_manager,
            notification_callback=notification_callback,
        )
        return self._agent_loop

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
                self._replay_manager.save_agent_message_chunk(context.session, ack_content)
                self._state_manager.add_assistant_message(context.session, ack_text)
            return context

        agent_loop = self._get_or_create_agent_loop(
            context,
            notification_callback=context.meta.get("notification_callback"),
        )
        mcp_manager = self._get_mcp_manager(context)

        result = await agent_loop.run(
            session=context.session,
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
        session: SessionState,
        session_id: str,
        tool_call_id: str,
        mcp_manager: Any | None = None,
        notification_callback: Callable[[ACPMessage], Awaitable[None]] | None = None,
    ) -> LLMLoopResult:
        """Выполнить pending tool после permission approval.

        Переиспользует существующий AgentLoop (с той же стратегией, что и при process()).
        Если AgentLoop ещё не создан, создаёт его с правильной стратегией.

        Args:
            session: Состояние сессии.
            session_id: ID сессии.
            tool_call_id: ID tool call для выполнения.
            mcp_manager: MCP manager для tool execution.
            notification_callback: Опциональный callback для немедленной отправки notifications.

        Returns:
            LLMLoopResult с результатами выполнения.
        """
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
                    session=session,
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

            self._agent_loop = AgentLoop(
                strategy=strategy,
                tool_registry=self._tool_registry,
                tool_call_handler=self._tool_call_handler,
                permission_manager=self._permission_manager,
                state_manager=self._state_manager,
                content_extractor=self._content_extractor,
                content_validator=self._content_validator,
                content_formatter=self._content_formatter,
                replay_manager=self._replay_manager,
                plan_builder=self._plan_builder,
                system_prompt_builder=self._system_prompt_builder,
                global_policy_manager=self._global_policy_manager,
                notification_callback=notification_callback,
            )
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
            session=session,
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

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

from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.agent.strategies.legacy_adapter import LegacyCallStrategy
from codelab.server.protocol.content.extractor import ContentExtractor
from codelab.server.protocol.content.formatter import ContentFormatter
from codelab.server.protocol.content.validator import ContentValidator
from codelab.server.protocol.handlers.pipeline.stages.agent_loop import AgentLoop
from codelab.server.protocol.handlers.replay_manager import ReplayManager
from codelab.server.protocol.stop_reasons import StopReason

from ..base import PromptStage
from ..context import PromptContext

if TYPE_CHECKING:
    from codelab.server.agent.orchestrator import AgentOrchestrator
    from codelab.server.agent.strategies.base import LLMCallStrategy
    from codelab.server.agent.strategies.dispatcher import StrategyDispatcher
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

    Поддерживает два пути выполнения через LLMCallStrategy:
    - Legacy: через LegacyCallStrategy → AgentOrchestrator → NaiveAgent
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
            global_policy_manager: Менеджер глобальных политик (опционально).
            strategy_dispatcher: StrategyDispatcher для EventBus пути (опционально).
                Если None, используется LegacyCallStrategy.
            tracer: Tracer для observability (опционально).
        """
        self._tool_registry = tool_registry
        self._tool_call_handler = tool_call_handler
        self._permission_manager = permission_manager
        self._state_manager = state_manager
        self._plan_builder = plan_builder
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

        strategy_name = "event_bus" if strategy_dispatcher else "legacy"
        logger.info(
            "LLMLoopStage initialized",
            strategy=strategy_name,
            tracer_enabled=tracer is not None,
        )

    def _get_or_create_agent_loop(self, context: PromptContext) -> AgentLoop:
        """Лениво создать AgentLoop с нужной стратегией.

        Args:
            context: Контекст pipeline для получения agent_orchestrator.

        Returns:
            AgentLoop с нужной стратегией.

        Raises:
            ValueError: Если стратегия не доступна.
        """
        if self._agent_loop is not None:
            return self._agent_loop

        # Определить стратегию
        strategy: LLMCallStrategy
        if self._strategy_dispatcher is not None:
            strategy = self._strategy_dispatcher
        else:
            agent_orchestrator = context.meta.get("agent_orchestrator")
            if agent_orchestrator is None:
                raise ValueError("No LLM strategy available: neither strategy_dispatcher nor agent_orchestrator")
            strategy = LegacyCallStrategy(agent_orchestrator)

        self._agent_loop = AgentLoop(
            strategy=strategy,
            tool_registry=self._tool_registry,
            tool_call_handler=self._tool_call_handler,
            permission_manager=self._permission_manager,
            state_manager=self._state_manager,
            content_extractor=self._content_extractor,
            content_formatter=self._content_formatter,
            replay_manager=self._replay_manager,
            plan_builder=self._plan_builder,
            global_policy_manager=self._global_policy_manager,
        )
        return self._agent_loop

    async def process(self, context: PromptContext) -> PromptContext:
        """Обработать prompt через AgentLoop.

        Args:
            context: Контекст pipeline.

        Returns:
            Обновлённый контекст с результатами.
        """
        # Demo mode: нет LLM
        agent_orchestrator: AgentOrchestrator | None = context.meta.get("agent_orchestrator")
        if agent_orchestrator is None and self._strategy_dispatcher is None:
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

        agent_loop = self._get_or_create_agent_loop(context)
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
        agent_orchestrator: AgentOrchestrator,
        mcp_manager: Any | None = None,
    ) -> LLMLoopResult:
        """Выполнить pending tool после permission approval.

        Делегирует AgentLoop.resume_after_permission().

        Args:
            session: Состояние сессии.
            session_id: ID сессии.
            tool_call_id: ID tool call для выполнения.
            agent_orchestrator: Legacy оркестратор (для создания стратегии).
            mcp_manager: MCP manager.

        Returns:
            LLMLoopResult с результатом выполнения.
        """
        # Создать временный контекст для получения стратегии
        from ..context import PromptContext
        context = PromptContext(
            session=session,
            session_id=session_id,
            raw_text=None,
            meta={"agent_orchestrator": agent_orchestrator},
        )

        agent_loop = self._get_or_create_agent_loop(context)

        result = await agent_loop.resume_after_permission(
            session=session,
            session_id=session_id,
            tool_call_id=tool_call_id,
            mcp_manager=mcp_manager,
        )

        # Конвертировать AgentLoopResult → LLMLoopResult
        from codelab.server.protocol.state import LLMLoopResult
        return LLMLoopResult(
            notifications=result.notifications,
            stop_reason=result.stop_reason.value if isinstance(result.stop_reason, StopReason) else result.stop_reason,
            pending_permission=result.pending_permission,
            pending_tool_calls=result.pending_tool_calls,
            tool_results=result.tool_results,
        )

    def _get_mcp_manager(self, context: PromptContext):
        """Получить MCP manager из PromptContext.meta."""
        return context.meta.get("mcp_manager")

    # =========================================================================
    # Legacy methods for backward compatibility with tests
    # Эти методы делегируют в AgentLoop для обратной совместимости с тестами
    # =========================================================================

    async def _process_tool_calls_for_llm_loop(
        self,
        session: SessionState,
        session_id: str,
        tool_calls: list,
        notifications: list,
        mcp_manager: Any | None = None,
    ) -> LLMLoopResult:
        """Обработать tool calls (legacy interface для тестов).

        Делегирует в AgentLoop._process_tool_calls().
        """
        agent_loop = self._get_agent_loop_for_legacy()
        result = await agent_loop._process_tool_calls(
            session, session_id, tool_calls, notifications, mcp_manager
        )
        from codelab.server.protocol.state import LLMLoopResult
        return LLMLoopResult(
            notifications=notifications,
            tool_results=result.tool_results,
            pending_permission=result.pending_permission,
        )

    async def run_loop(
        self,
        session: SessionState,
        session_id: str,
        agent_orchestrator: Any,
        initial_prompt_text: str | None = None,
        tool_results: list | None = None,
        mcp_manager: Any | None = None,
    ) -> LLMLoopResult:
        """Запустить LLM loop (legacy interface для тестов).

        Делегирует в AgentLoop.run().
        """
        from ..context import PromptContext
        context = PromptContext(
            session=session,
            session_id=session_id,
            raw_text=initial_prompt_text,
            meta={"agent_orchestrator": agent_orchestrator},
        )
        agent_loop = self._get_or_create_agent_loop(context)

        result = await agent_loop.run(
            session=session,
            session_id=session_id,
            initial_prompt=initial_prompt_text,
            mcp_manager=mcp_manager,
        )

        from codelab.server.protocol.state import LLMLoopResult
        return LLMLoopResult(
            notifications=result.notifications,
            stop_reason=result.stop_reason.value if isinstance(result.stop_reason, StopReason) else result.stop_reason,
            final_text=result.text,
            pending_permission=result.pending_permission,
            tool_results=result.tool_results,
        )

    async def _run_llm_loop(
        self,
        session: SessionState,
        session_id: str,
        agent_orchestrator: Any,
        initial_prompt_text: str | None = None,
        tool_results: list | None = None,
        mcp_manager: Any | None = None,
    ) -> LLMLoopResult:
        """Legacy LLM loop (legacy interface для тестов).

        Делегирует в run_loop().
        """
        return await self.run_loop(
            session=session,
            session_id=session_id,
            agent_orchestrator=agent_orchestrator,
            initial_prompt_text=initial_prompt_text,
            tool_results=tool_results,
            mcp_manager=mcp_manager,
        )

    def _get_agent_loop_for_legacy(self) -> AgentLoop:
        """Получить AgentLoop для legacy методов (без context).

        Создаёт AgentLoop с LegacyCallStrategy используя mock orchestrator.
        """
        if self._agent_loop is not None:
            return self._agent_loop

        # Для legacy методов создаём AgentLoop с mock стратегией
        # Это нужно только для тестов которые вызывают внутренние методы напрямую
        from unittest.mock import MagicMock
        mock_strategy = MagicMock()
        self._agent_loop = AgentLoop(
            strategy=mock_strategy,
            tool_registry=self._tool_registry,
            tool_call_handler=self._tool_call_handler,
            permission_manager=self._permission_manager,
            state_manager=self._state_manager,
            content_extractor=self._content_extractor,
            content_formatter=self._content_formatter,
            replay_manager=self._replay_manager,
            plan_builder=self._plan_builder,
            global_policy_manager=self._global_policy_manager,
        )
        return self._agent_loop

    def _is_cancel_requested(self, session: SessionState) -> bool:
        """Проверить флаг отмены (legacy interface для тестов)."""
        return session.active_turn is not None and session.active_turn.cancel_requested

    async def _decide_tool_execution(self, session: SessionState, tool_kind: str) -> str:
        """Определить решение о выполнении tool (legacy interface для тестов)."""
        agent_loop = self._get_agent_loop_for_legacy()
        return await agent_loop._decide_tool_execution(session, tool_kind)

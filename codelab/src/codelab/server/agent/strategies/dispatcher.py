"""StrategyDispatcher — маршрутизация запросов к стратегиям выполнения.

Выбирает стратегию на основе режима выполнения (mode) из конфигурации сессии:
- "single" → SingleStrategy (прямой вызов LLMAdapter через EventBus)
- "multi_orchestrated" → OrchestratedStrategy (будущая реализация)
- "multi_choreographed" → ChoreographyStrategy (будущая реализация)
- "hierarchical" → HierarchicalStrategy (будущая реализация)

Архитектурное решение:
- Все стратегии используют один паттерн вызова через EventBus (uniformity)
- StrategyDispatcher — единственный компонент, знающий о routing
- LLMLoopStage не знает о стратегиях — вызывает dispatcher.execute()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

import structlog

if TYPE_CHECKING:
    from codelab.server.agent.base import AgentResponse
    from codelab.server.agent.event_bus.bus import AgentEventBus
    from codelab.server.agent.execution_engine import ExecutionEngine
    from codelab.server.observability.tracer import SpanContext, Tracer
    from codelab.server.protocol.state import SessionState

logger = structlog.get_logger()

# Допустимые режимы выполнения
ExecutionMode = Literal[
    "single",
    "multi_orchestrated",
    "multi_choreographed",
    "hierarchical",
]

# Режим по умолчанию
_DEFAULT_MODE: ExecutionMode = "single"


class StrategyDispatcher:
    """Диспетчер стратегий выполнения.

    Выбирает и делегирует выполнение соответствующей стратегии
    на основе режима выполнения из конфигурации сессии.

    Attributes:
        _strategies: Мапа стратегий (mode → strategy instance)
        _default_mode: Режим по умолчанию
        _tracer: Tracer для observability
    """

    def __init__(
        self,
        event_bus: AgentEventBus,
        execution_engine: ExecutionEngine,
        tracer: Tracer | None = None,
        default_mode: ExecutionMode = _DEFAULT_MODE,
    ) -> None:
        self._event_bus = event_bus
        self._execution_engine = execution_engine
        self._tracer = tracer
        self._default_mode = default_mode
        self._strategies: dict[str, Any] = {}

        # Регистрируем SingleStrategy (единственная реализованная стратегия)
        from codelab.server.protocol.handlers.strategies.single_strategy import (
            SingleStrategy,
        )

        self._strategies["single"] = SingleStrategy(
            event_bus=event_bus,
            execution_engine=execution_engine,
            tracer=tracer,
            agent_name="primary",
        )

        logger.info(
            "StrategyDispatcher initialized with mode=%s",
            default_mode,
        )

    async def execute(
        self,
        session: SessionState,
        prompt: str,
        system_prompt: str | None = None,
        mcp_manager: Any | None = None,
        parent_span: SpanContext | None = None,
    ) -> AgentResponse:
        """Выполнить стратегию на основе режима сессии.

        Args:
            session: Состояние сессии (содержит config с mode)
            prompt: Текст промпта пользователя
            system_prompt: Системный промпт
            mcp_manager: MCP manager
            parent_span: Родительский span для tracing

        Returns:
            AgentResponse с результатом выполнения стратегии

        Raises:
            ValueError: Если режим выполнения не поддерживается
        """
        mode = self._resolve_mode(session)
        strategy = self._strategies.get(mode)

        if strategy is None:
            # Проверяем есть ли заглушка для будущих стратегий
            if mode in ("multi_orchestrated", "multi_choreographed", "hierarchical"):
                raise NotImplementedError(
                    f"Strategy '{mode}' is not yet implemented. "
                    f"Use 'single' mode or set fallback_mode in config."
                )
            raise ValueError(f"Unknown execution mode: {mode}")

        logger.debug(
            "dispatching to strategy",
            mode=mode,
            session_id=session.session_id,
        )

        return await strategy.execute(
            session=session,
            prompt=prompt,
            system_prompt=system_prompt,
            mcp_manager=mcp_manager,
            parent_span=parent_span,
        )

    async def continue_execution(
        self,
        session: SessionState,
        mcp_manager: Any | None = None,
        parent_span: SpanContext | None = None,
    ) -> AgentResponse:
        """Продолжить выполнение после tool_results.

        Args:
            session: Состояние сессии
            mcp_manager: MCP manager
            parent_span: Родительский span

        Returns:
            AgentResponse с результатом
        """
        mode = self._resolve_mode(session)
        strategy = self._strategies.get(mode)

        if strategy is None:
            raise ValueError(f"No strategy registered for mode: {mode}")

        return await strategy.continue_execution(
            session=session,
            mcp_manager=mcp_manager,
            parent_span=parent_span,
        )

    def _resolve_mode(self, session: SessionState) -> str:
        """Резолвить режим выполнения из конфигурации сессии.

        Порядок приоритета:
        1. session.config_values.get("mode")
        2. _default_mode

        Args:
            session: Состояние сессии

        Returns:
            Режим выполнения (str)
        """
        config_values = getattr(session, "config_values", {}) or {}
        mode = config_values.get("mode", self._default_mode)
        return mode

    def get_registered_modes(self) -> list[str]:
        """Получить список зарегистрированных режимов.

        Returns:
            Список mode строк
        """
        return list(self._strategies.keys())

    def is_mode_supported(self, mode: str) -> bool:
        """Проверить поддержку режима.

        Args:
            mode: Режим для проверки

        Returns:
            True если режим поддерживается
        """
        return mode in self._strategies

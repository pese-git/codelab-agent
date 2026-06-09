"""StrategyDispatcher — маршрутизация запросов к стратегиям выполнения.

Выбирает стратегию на основе server-side конфигурации (strategy):
- "single" → SingleStrategy (прямой вызов LLMAdapter через EventBus)
- "multi_orchestrated" → OrchestratedStrategy (будущая реализация)
- "hierarchical" → HierarchicalStrategy (будущая реализация)

Агент для выполнения определяется через session.config_values["_agent"],
который формируется из списка primary agents в AgentRegistry.

Архитектурное решение:
- Strategy определяется server-side (TOML/CLI/ENV), override через /strategy
- Agent определяется session-level (IDE dropdown из AgentRegistry)
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
    from codelab.server.agent.registry import AgentRegistry
    from codelab.server.observability.tracer import SpanContext, Tracer
    from codelab.server.protocol.state import SessionState

logger = structlog.get_logger()

# Допустимые стратегии выполнения
ExecutionStrategy = Literal[
    "single",
    "multi_orchestrated",
    "hierarchical",
]

# Стратегия по умолчанию
_DEFAULT_STRATEGY: ExecutionStrategy = "single"


class StrategyDispatcher:
    """Диспетчер стратегий выполнения.

    Выбирает и делегирует выполнение соответствующей стратегии
    на основе server-side конфигурации. Агент для выполнения
    определяется через session.config_values["_agent"].

    Attributes:
        _strategies: Мапа стратегий (strategy_name → strategy instance)
        _strategy_name: Текущая стратегия выполнения
        _agent_registry: Реестр агентов для определения target agent
        _tracer: Tracer для observability
    """

    def __init__(
        self,
        event_bus: AgentEventBus,
        execution_engine: ExecutionEngine,
        agent_registry: AgentRegistry,
        tracer: Tracer | None = None,
        strategy: str = _DEFAULT_STRATEGY,
    ) -> None:
        self._event_bus = event_bus
        self._execution_engine = execution_engine
        self._agent_registry = agent_registry
        self._tracer = tracer
        self._strategy_name = strategy
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
            "StrategyDispatcher initialized",
            strategy=strategy,
            agents_count=len(agent_registry.get_all()),
        )

    async def execute(
        self,
        session: SessionState,
        prompt: str,
        system_prompt: str | None = None,
        mcp_manager: Any | None = None,
        parent_span: SpanContext | None = None,
    ) -> AgentResponse:
        """Выполнить стратегию.

        Определяет стратегию из server config и агента из session config.

        Args:
            session: Состояние сессии (содержит config_values["_agent"])
            prompt: Текст промпта пользователя
            system_prompt: Системный промпт
            mcp_manager: MCP manager
            parent_span: Родительский span для tracing

        Returns:
            AgentResponse с результатом выполнения стратегии

        Raises:
            ValueError: Если стратегия или агент не найдены
        """
        # 1. Получаем стратегию из server config
        strategy = self._strategies.get(self._strategy_name)
        if strategy is None:
            if self._strategy_name in ("multi_orchestrated", "hierarchical"):
                raise NotImplementedError(
                    f"Strategy '{self._strategy_name}' is not yet implemented. "
                    f"Use 'single' strategy."
                )
            raise ValueError(f"Unknown strategy: {self._strategy_name}")

        # 2. Получаем agent_name из session config
        agent_name = self._resolve_agent_name(session)

        # 3. Проверяем наличие агента в Registry
        agent = self._agent_registry.get(agent_name)
        if agent is None:
            available = list(self._agent_registry.get_all().keys())
            raise ValueError(
                f"Agent '{agent_name}' not found in registry. "
                f"Available agents: {available}"
            )

        logger.debug(
            "dispatching to strategy",
            strategy=self._strategy_name,
            agent_name=agent_name,
            session_id=session.session_id,
        )

        # 4. Выполняем с правильным agent_name
        return await strategy.execute(
            session=session,
            prompt=prompt,
            system_prompt=system_prompt,
            mcp_manager=mcp_manager,
            parent_span=parent_span,
            agent_name=agent_name,
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
        strategy = self._strategies.get(self._strategy_name)
        if strategy is None:
            raise ValueError(f"No strategy registered: {self._strategy_name}")

        agent_name = self._resolve_agent_name(session)

        return await strategy.continue_execution(
            session=session,
            mcp_manager=mcp_manager,
            parent_span=parent_span,
            agent_name=agent_name,
        )

    def _resolve_agent_name(self, session: SessionState) -> str:
        """Определить имя агента для выполнения.

        Порядок приоритета:
        1. session.config_values.get("_agent")
        2. Default agent из Registry (по priority)

        Args:
            session: Состояние сессии

        Returns:
            Имя агента для вызова
        """
        config_values = getattr(session, "config_values", {}) or {}
        agent_name = config_values.get("_agent")

        if agent_name:
            return agent_name

        # Fallback: агент по умолчанию (по priority)
        return self._get_default_agent_name()

    def _get_default_agent_name(self) -> str:
        """Получить имя агента по умолчанию (по priority).

        Returns:
            Имя агента с наименьшим priority значением

        Raises:
            ValueError: Если нет зарегистрированных primary agents
        """
        primary_agents = self._agent_registry.get_primary_agents()
        if not primary_agents:
            # Fallback если Registry пуст
            return "primary"

        # Сортируем по priority (меньше = выше приоритет)
        sorted_agents = sorted(primary_agents.values(), key=lambda a: a.priority)
        return sorted_agents[0].name

    def set_strategy(self, strategy_name: str) -> None:
        """Runtime override стратегии (для /strategy slash command).

        Args:
            strategy_name: Имя стратегии для установки

        Raises:
            ValueError: Если стратегия не зарегистрирована
        """
        if strategy_name not in self._strategies:
            available = list(self._strategies.keys())
            raise ValueError(
                f"Unknown strategy: {strategy_name}. "
                f"Available strategies: {available}"
            )

        old_strategy = self._strategy_name
        self._strategy_name = strategy_name
        logger.info(
            "strategy changed",
            old_strategy=old_strategy,
            new_strategy=strategy_name,
        )

    def get_strategy(self) -> str:
        """Получить текущую стратегию.

        Returns:
            Имя текущей стратегии
        """
        return self._strategy_name

    def get_registered_strategies(self) -> list[str]:
        """Получить список зарегистрированных стратегий.

        Returns:
            Список имён стратегий
        """
        return list(self._strategies.keys())

    def is_strategy_supported(self, strategy_name: str) -> bool:
        """Проверить поддержку стратегии.

        Args:
            strategy_name: Имя стратегии для проверки

        Returns:
            True если стратегия поддерживается
        """
        return strategy_name in self._strategies

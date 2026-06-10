"""StrategyDispatcher — маршрутизация запросов к стратегиям выполнения.

ТОЛЬКО маршрутизация (priority chain + fallback).
Использует StrategyRegistry для получения списка доступных стратегий.

Архитектурное решение:
- StrategyDispatcher НЕ хранит стратегии (это делает StrategyRegistry)
- StrategyDispatcher НЕ создает metadata (это хранится в StrategyDescriptor)
- StrategyDispatcher ТОЛЬКО выбирает стратегию по приоритету и валидирует доступность

Priority chain:
1. context.meta["active_strategy"] — slash command override
2. config_values["_active_strategy"] — persistent config option
3. default_strategy — server config default
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.messages import ACPMessage

if TYPE_CHECKING:
    from codelab.server.agent.base import AgentResponse
    from codelab.server.agent.registry import AgentRegistry
    from codelab.server.agent.strategies.base import LLMCallStrategy
    from codelab.server.agent.strategies.descriptor import StrategyDependencies
    from codelab.server.agent.strategies.registry import StrategyRegistry
    from codelab.server.observability.tracer import SpanContext
    from codelab.server.protocol.state import SessionState

logger = structlog.get_logger()


class StrategyDispatcher:
    """Диспетчер стратегий — ТОЛЬКО маршрутизация.
    
    Responsibilities:
    - Priority chain (slash → config → default)
    - Validation через StrategyRegistry
    - Fallback на доступную стратегию
    
    НЕ отвечает за:
    - Хранение стратегий (это делает StrategyRegistry)
    - Создание экземпляров (это делает Registry)
    - Metadata (это хранится в StrategyDescriptor)
    
    Attributes:
        _strategy_registry: Реестр стратегий
        _agent_registry: Реестр агентов для валидации
        _deps: Зависимости для создания стратегий
        _default_strategy: Стратегия по умолчанию из server config
        _fallback_strategy: Стратегия для fallback
        _current_strategy_name: Текущая выбранная стратегия
    
    Example:
        >>> dispatcher = StrategyDispatcher(
        ...     strategy_registry=registry,
        ...     agent_registry=agent_registry,
        ...     strategy_dependencies=deps,
        ...     default_strategy="single",
        ...     fallback_strategy="single",
        ... )
        >>> strategy_name, fallback_from = dispatcher.select_strategy(session, meta)
        >>> strategy = dispatcher.get_current_strategy()
    """

    def __init__(
        self,
        strategy_registry: StrategyRegistry,
        agent_registry: AgentRegistry,
        strategy_dependencies: StrategyDependencies,
        default_strategy: str = "single",
        fallback_strategy: str = "single",
    ) -> None:
        """Инициализация StrategyDispatcher.
        
        Args:
            strategy_registry: Реестр стратегий
            agent_registry: Реестр агентов для валидации
            strategy_dependencies: Зависимости для создания стратегий
            default_strategy: Стратегия по умолчанию из server config
            fallback_strategy: Стратегия для fallback
        """
        self._strategy_registry = strategy_registry
        self._agent_registry = agent_registry
        self._deps = strategy_dependencies
        self._default_strategy = default_strategy
        self._fallback_strategy = fallback_strategy
        self._current_strategy_name = default_strategy

        logger.info(
            "StrategyDispatcher initialized",
            default_strategy=default_strategy,
            fallback_strategy=fallback_strategy,
            registered_strategies=len(strategy_registry.list_all()),
            agents_count=len(agent_registry.get_all()),
        )

    def select_strategy(
        self,
        session: SessionState,
        context_meta: dict[str, Any] | None = None,
    ) -> tuple[str, str | None]:
        """Выбрать стратегию по приоритету.
        
        Priority chain:
        1. context_meta["active_strategy"] — slash command override
        2. session.config_values["_active_strategy"] — persistent config
        3. self._default_strategy — server config default
        
        Args:
            session: Состояние сессии
            context_meta: Метаданные контекста (для slash command override)
        
        Returns:
            Кортеж (strategy_name, fallback_from):
            - strategy_name: имя выбранной стратегии
            - fallback_from: имя запрошенной но недоступной стратегии (None если не было fallback)
        """
        # 1. Slash command override (высший приоритет)
        if context_meta and context_meta.get("active_strategy"):
            requested = context_meta["active_strategy"]
            logger.debug(
                "strategy from slash command",
                strategy=requested,
                session_id=session.session_id,
            )
        # 2. Persistent config (session-level)
        elif session.config_values.get("_active_strategy"):
            requested = session.config_values["_active_strategy"]
            logger.debug(
                "strategy from config_values",
                strategy=requested,
                session_id=session.session_id,
            )
        # 3. Server default
        else:
            requested = self._default_strategy
            logger.debug(
                "strategy from default",
                strategy=requested,
                session_id=session.session_id,
            )

        # Валидация через Registry
        available = self._strategy_registry.get_available(self._agent_registry)
        available_names = [d.name for d in available]

        if requested in available_names:
            self._current_strategy_name = requested
            return requested, None

        # Fallback
        logger.warning(
            "strategy not available, falling back",
            requested=requested,
            available=available_names,
            session_id=session.session_id,
        )

        fallback = self._fallback_strategy
        if fallback not in available_names:
            # Если даже fallback недоступен, взять первую доступную
            if available:
                fallback = available[0].name
                logger.warning(
                    "fallback strategy also not available, using first available",
                    fallback=fallback,
                    session_id=session.session_id,
                )
            else:
                # Последний resort — "single" (должна быть всегда)
                fallback = "single"
                logger.error(
                    "no strategies available, using hardcoded fallback",
                    fallback=fallback,
                    session_id=session.session_id,
                )

        self._current_strategy_name = fallback
        return fallback, requested

    def get_current_strategy(self) -> LLMCallStrategy | None:
        """Получить текущий экземпляр стратегии.
        
        Returns:
            Экземпляр стратегии или None если не найдена
        """
        return self._strategy_registry.create_instance(
            self._current_strategy_name,
            self._deps,
        )

    def set_current_strategy(self, name: str) -> bool:
        """Установить текущую стратегию.
        
        Args:
            name: Имя стратегии
        
        Returns:
            True если стратегия установлена, False если не найдена
        """
        descriptor = self._strategy_registry.get(name)
        if descriptor is None:
            logger.warning("strategy not found", name=name)
            return False

        old_strategy = self._current_strategy_name
        self._current_strategy_name = name
        logger.info(
            "strategy changed",
            old_strategy=old_strategy,
            new_strategy=name,
        )
        return True

    def get_strategy(self) -> str:
        """Получить имя текущей стратегии.
        
        Returns:
            Имя текущей стратегии
        """
        return self._current_strategy_name

    def get_available_strategies(self) -> list[str]:
        """Получить список доступных стратегий.
        
        Returns:
            Список имён доступных стратегий
        """
        available = self._strategy_registry.get_available(self._agent_registry)
        return [d.name for d in available]

    def is_strategy_available(self, name: str) -> bool:
        """Проверить доступность стратегии.
        
        Args:
            name: Имя стратегии
        
        Returns:
            True если стратегия доступна
        """
        return name in self.get_available_strategies()

    # =========================================================================
    # LLMCallStrategy Protocol (для обратной совместимости с AgentLoop)
    # =========================================================================

    async def execute(
        self,
        session: SessionState,
        prompt: str | None,
        mcp_manager: Any | None = None,
        *,
        system_prompt: str | None = None,
        parent_span: SpanContext | None = None,
    ) -> AgentResponse:
        """Выполнить стратегию (LLMCallStrategy Protocol).
        
        Этот метод реализует LLMCallStrategy Protocol для обратной совместимости
        с AgentLoop. Выбирает стратегию через select_strategy() и делегирует выполнение.
        
        Args:
            session: Состояние сессии
            prompt: Текст промпта пользователя (None для продолжения)
            mcp_manager: MCP manager
            system_prompt: Системный промпт (keyword-only, опционально)
            parent_span: Родительский span для tracing (keyword-only, опционально)
        
        Returns:
            AgentResponse с результатом выполнения стратегии
        
        Raises:
            ValueError: Если стратегия не найдена
        """
        # Выбираем стратегию (без context_meta, т.к. это прямой вызов)
        strategy_name, _ = self.select_strategy(session, context_meta=None)

        # Получаем экземпляр стратегии
        strategy = self._strategy_registry.create_instance(strategy_name, self._deps)
        if strategy is None:
            raise ValueError(f"Failed to create strategy instance: {strategy_name}")

        # Получаем agent_name из session config
        agent_name = self._resolve_agent_name(session)

        # Обновляем deps с правильным agent_name
        from codelab.server.agent.strategies.descriptor import StrategyDependencies

        deps_with_agent = StrategyDependencies(
            event_bus=self._deps.event_bus,
            execution_engine=self._deps.execution_engine,
            tracer=self._deps.tracer,
            agent_name=agent_name,
        )

        # Создаём стратегию с правильным agent_name
        strategy = self._strategy_registry.create_instance(strategy_name, deps_with_agent)
        if strategy is None:
            raise ValueError(f"Failed to create strategy instance: {strategy_name}")

        logger.debug(
            "dispatching to strategy",
            strategy=strategy_name,
            agent_name=agent_name,
            session_id=session.session_id,
        )

        # Делегируем выполнение
        return await strategy.execute(
            session=session,
            prompt=prompt,
            mcp_manager=mcp_manager,
            system_prompt=system_prompt,
            parent_span=parent_span,
        )

    async def continue_execution(
        self,
        session: SessionState,
        mcp_manager: Any | None = None,
        *,
        parent_span: SpanContext | None = None,
    ) -> AgentResponse:
        """Продолжить выполнение после tool_results (LLMCallStrategy Protocol).
        
        Args:
            session: Состояние сессии
            mcp_manager: MCP manager
            parent_span: Родительский span (keyword-only, опционально)
        
        Returns:
            AgentResponse с результатом
        """
        # Используем текущую стратегию
        strategy = self.get_current_strategy()
        if strategy is None:
            raise ValueError(f"No strategy instance for: {self._current_strategy_name}")

        # Получаем agent_name из session config
        agent_name = self._resolve_agent_name(session)

        # Обновляем deps с правильным agent_name
        from codelab.server.agent.strategies.descriptor import StrategyDependencies

        deps_with_agent = StrategyDependencies(
            event_bus=self._deps.event_bus,
            execution_engine=self._deps.execution_engine,
            tracer=self._deps.tracer,
            agent_name=agent_name,
        )

        # Создаём стратегию с правильным agent_name
        strategy = self._strategy_registry.create_instance(
            self._current_strategy_name,
            deps_with_agent,
        )
        if strategy is None:
            raise ValueError(f"Failed to create strategy instance: {self._current_strategy_name}")

        return await strategy.continue_execution(
            session=session,
            mcp_manager=mcp_manager,
            parent_span=parent_span,
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
        """
        primary_agents = self._agent_registry.get_primary_agents()
        if not primary_agents:
            # Fallback если Registry пуст
            return "primary"

        # Сортируем по priority (меньше = выше приоритет)
        sorted_agents = sorted(primary_agents.values(), key=lambda a: a.priority)
        return sorted_agents[0].name

    # =========================================================================
    # Fallback Notification
    # =========================================================================

    @staticmethod
    def build_fallback_notification(
        session_id: str,
        requested: str,
        actual: str,
        reason: str,
    ) -> ACPMessage:
        """Построить notification о fallback.
        
        Args:
            session_id: ID сессии
            requested: Запрошенная стратегия
            actual: Фактическая стратегия (fallback)
            reason: Причина fallback
        
        Returns:
            ACPMessage notification
        """
        return ACPMessage.notification(
            "session/update",
            {
                "sessionId": session_id,
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {
                        "type": "text",
                        "text": (
                            f"[system] Strategy '{requested}' unavailable ({reason}). "
                            f"Falling back to '{actual}'."
                        ),
                    },
                },
            },
        )

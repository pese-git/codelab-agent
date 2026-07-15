"""Провайдеры мультиагентных компонентов (APP scope).

Шина событий, движок выполнения, фабрика агентов, реестры стратегий/агентов
и компоненты Context Manager (compactor, кэш файлов, менеджер контекста).
"""

from __future__ import annotations

from typing import Annotated

import structlog
from dishka import Provider, Scope, from_context, provide

from ..agent.context.file_cache import InvalidationSignalBus, SessionFileCacheRegistry
from ..agent.context.manager import DefaultContextManager
from ..agent.context_compactor import ContextCompactor
from ..agent.event_bus.bus import AgentEventBus, RetryConfig
from ..agent.execution_engine import ExecutionEngine
from ..agent.factory import AgentFactory
from ..agent.registry import AgentRegistry
from ..agent.strategies.descriptor import StrategyDependencies
from ..agent.strategies.dispatcher import StrategyDispatcher
from ..agent.strategies.registry import StrategyRegistry
from ..config import AppConfig
from ..llm import LLMProvider
from ..llm.registry import LLMProviderRegistry
from ..observability import EventTimeline, MetricsTracker, Tracer
from ..tools.base import ToolRegistry as ToolRegistryProtocol

logger = structlog.get_logger()


class EventBusProvider(Provider):
    """Провайдер шины событий (APP scope).

    Создаёт AgentEventBus и подключает observability компоненты
    для автоматического сбора метрик и записи событий.
    """

    @provide(scope=Scope.APP)
    def get_event_bus(
        self,
        timeline: EventTimeline,
        metrics: MetricsTracker,
    ) -> AgentEventBus:
        """Создаёт AgentEventBus с подключёнными observability."""
        bus = AgentEventBus(retry_config=RetryConfig(max_attempts=3, base_delay=0.1))
        timeline.subscribe_to_bus(bus)
        metrics.subscribe_to_bus(bus)
        return bus


class MultiAgentProvider(Provider):
    """Провайдер мультиагентных компонентов (APP scope).

    Создаёт:
    - ExecutionEngine — композиционный движок выполнения
    - AgentFactory — фабрика создания LLMAdapter
    - StrategyRegistry — реестр стратегий (Registry Pattern)
    - StrategyDependencies — контейнер зависимостей для стратегий
    - StrategyDispatcher — маршрутизация по стратегиям (только routing)
    - AgentRegistry — реестр агентов с hot reload
    """

    @provide(scope=Scope.APP)
    async def get_context_compactor(
        self,
        llm_provider: LLMProvider,
    ) -> ContextCompactor:
        """Создаёт ContextCompactor для автоматического сжатия контекста.

        Использует дефолтные значения из спецификации мультиагентной системы:
        - context_window_limit: 128000
        - compaction_reserved_tokens: 4096
        - slicer_model: openai/gpt-4o-mini
        """
        from codelab.server.agent.config.models import AgentsGlobalConfig

        defaults = AgentsGlobalConfig()
        return ContextCompactor(
            llm=llm_provider,
            model=defaults.slicer_model,
            max_context_tokens=defaults.context_window_limit,
            reserved_tokens=defaults.compaction_reserved_tokens,
        )

    @provide(scope=Scope.APP)
    def get_invalidation_signal_bus(self) -> InvalidationSignalBus:
        """Создаёт InvalidationSignalBus — единый источник сигналов изменения файлов.

        Интеграция Фаза 2 ↔ Фаза 4: FileCacheDecorator публикует сигналы при fs/write,
        DefaultContextManager подписывается для обнаружения изменений baseline.
        """
        return InvalidationSignalBus()

    @provide(scope=Scope.APP)
    def get_session_file_cache_registry(
        self,
        config: AppConfig,
        signal_bus: InvalidationSignalBus,
    ) -> SessionFileCacheRegistry:
        """Создаёт SessionFileCacheRegistry с общим signal_bus.

        Управляет жизненным циклом кэша файлов для каждой сессии.
        """
        return SessionFileCacheRegistry(
            max_files_per_session=config.agents.context.cache_max_files,
            signal_bus=signal_bus,
        )

    @provide(scope=Scope.APP)
    def get_context_manager(
        self,
        tool_registry: ToolRegistryProtocol,
        config: AppConfig,
        metrics_tracker: MetricsTracker,
        tracer: Tracer,
        llm_provider: LLMProvider,
        signal_bus: InvalidationSignalBus,
    ) -> DefaultContextManager:
        """Создаёт DefaultContextManager с метриками и трейсингом.

        ContextManager автоматически собирает релевантные файлы через
        TaskAnalyzer + ContextGatherer, записывает метрики и span'ы.
        Подписывается на signal_bus для обнаружения изменений файлов (Фаза 4).
        """
        return DefaultContextManager(
            tool_registry=tool_registry,
            config=config.agents.context,
            llm=llm_provider,
            model=config.agents.context.analyzer_model,
            metrics_tracker=metrics_tracker,
            tracer=tracer,
            signal_bus=signal_bus,
        )

    @provide(scope=Scope.APP)
    def get_execution_engine(
        self,
        tool_registry: ToolRegistryProtocol,
        compactor: ContextCompactor,
        config: AppConfig,
        context_manager: DefaultContextManager,
    ) -> ExecutionEngine:
        """Создаёт ExecutionEngine с ContextCompactor и ContextManager.

        Compactor автоматически сжимает историю в build_context() и
        build_continuation_context() — это работает для всех стратегий
        (Single, Orchestrated, Hierarchical, Choreography) без дублирования.

        ContextManager собирает релевантные файлы при enabled=true.
        """
        return ExecutionEngine(
            tool_registry=tool_registry,
            compactor=compactor,
            context_config=config.agents.context,
            context_manager=context_manager,
        )

    @provide(scope=Scope.APP)
    def get_agent_factory(
        self,
        llm_registry: LLMProviderRegistry,
        tool_registry: ToolRegistryProtocol,
        tracer: Tracer,
    ) -> AgentFactory:
        """Создаёт AgentFactory."""
        return AgentFactory(llm_registry, tool_registry, tracer)

    @provide(scope=Scope.APP)
    def get_strategy_registry(self) -> StrategyRegistry:
        """Создаёт и заполняет StrategyRegistry.

        Регистрирует все доступные стратегии:
        - SingleStrategy (всегда доступна)
        - Будущие стратегии: OrchestratedStrategy, HierarchicalStrategy
        """
        from codelab.server.protocol.handlers.strategies.single_strategy import (
            SINGLE_STRATEGY_DESCRIPTOR,
        )

        registry = StrategyRegistry()
        registry.register(SINGLE_STRATEGY_DESCRIPTOR)

        logger.info(
            "StrategyRegistry created",
            registered_strategies=len(registry.list_all()),
        )

        return registry

    @provide(scope=Scope.APP)
    def get_strategy_dependencies(
        self,
        event_bus: AgentEventBus,
        execution_engine: ExecutionEngine,
        tracer: Tracer,
    ) -> StrategyDependencies:
        """Создаёт StrategyDependencies — контейнер зависимостей для стратегий."""
        return StrategyDependencies(
            event_bus=event_bus,
            execution_engine=execution_engine,
            tracer=tracer,
            agent_name="primary",
        )

    @provide(scope=Scope.APP)
    def get_strategy_dispatcher(
        self,
        config: Annotated[AppConfig, from_context(provides=AppConfig)],
        strategy_registry: StrategyRegistry,
        agent_registry: AgentRegistry,
        strategy_dependencies: StrategyDependencies,
    ) -> StrategyDispatcher:
        """Создаёт StrategyDispatcher.

        StrategyDispatcher теперь ТОЛЬКО маршрутизация (priority chain + fallback).
        Использует StrategyRegistry для получения списка доступных стратегий.
        """
        return StrategyDispatcher(
            strategy_registry=strategy_registry,
            agent_registry=agent_registry,
            strategy_dependencies=strategy_dependencies,
            default_strategy=config.agents.strategy,
            fallback_strategy=config.agents.fallback_strategy,
        )

    @provide(scope=Scope.APP)
    async def get_agent_registry(
        self,
        event_bus: AgentEventBus,
        agent_factory: AgentFactory,
        config: Annotated[AppConfig, from_context(provides=AppConfig)],
    ) -> AgentRegistry:
        """Создаёт и инициализирует AgentRegistry.

        Инициализация загружает конфигурации агентов из:
        - ~/.codelab/agents/*.md (глобальные)
        - .codelab/agents/*.md (проектные)
        """
        from codelab.server.agent.config.models import AgentsGlobalConfig

        # AppConfig._derive_agents_default_model гарантирует непустой default_model;
        # мягкий fallback повторяет ту же деривацию на случай нарушения инварианта.
        default_model = config.agents.default_model
        if default_model is None:
            default_model = f"{config.llm.provider}/{config.llm.model}"
        global_config = AgentsGlobalConfig(
            default_model=default_model,
            max_steps=config.agents.max_steps,
        )
        registry = AgentRegistry(event_bus, agent_factory, global_config)
        await registry.initialize()
        return registry

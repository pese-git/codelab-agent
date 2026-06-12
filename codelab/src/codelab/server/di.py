"""DI контейнер для серверной части ACP.

Архитектура скоупов:
- APP: синглтоны на всё время жизни сервера (LLM, ToolRegistry, менеджеры, стадии пайплайна)
- REQUEST: на одно WebSocket соединение (ClientRPCService, ACPProtocol)

Пример использования:
    container = make_container(config, storage)
    async with container() as request_scope:
        protocol = await request_scope.get(ACPProtocol)
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Annotated

import structlog
from dishka import (
    AsyncContainer,
    Provider,
    Scope,
    from_context,
    make_async_container,
    provide,
)

from .agent.event_bus.bus import AgentEventBus, RetryConfig
from .agent.execution_engine import ExecutionEngine
from .agent.factory import AgentFactory
from .agent.orchestrator import AgentOrchestrator
from .agent.registry import AgentRegistry
from .agent.state import OrchestratorConfig
from .agent.strategies.descriptor import StrategyDependencies
from .agent.strategies.dispatcher import StrategyDispatcher
from .agent.strategies.registry import StrategyRegistry
from .agent.system_prompt_builder import SystemPromptBuilder
from .config import AppConfig
from .llm import LLMProvider, MockLLMProvider
from .llm.base import LLMConfig, LLMTimeoutConfig
from .llm.errors import ProviderNotFoundError
from .llm.registry import LLMProviderRegistry
from .llm.resolver import ModelResolver
from .observability import EventTimeline, MetricsTracker, Tracer
from .observability.exporters import FileEventExporter, FileMetricsExporter, FileSpanExporter
from .protocol.core import ACPProtocol
from .protocol.handlers.client_rpc_handler import ClientRPCHandler
from .protocol.handlers.config_option_builder import ConfigOptionBuilder
from .protocol.handlers.global_policy_manager import GlobalPolicyManager
from .protocol.handlers.permission_manager import PermissionManager
from .protocol.handlers.pipeline import PromptPipeline
from .protocol.handlers.pipeline.stages import LLMLoopStage
from .protocol.handlers.plan_builder import PlanBuilder
from .protocol.handlers.prompt_orchestrator import PromptOrchestrator
from .protocol.handlers.slash_commands import CommandRegistry, SlashCommandRouter
from .protocol.handlers.slash_commands.builtin import (
    HelpCommandHandler,
    ModeCommandHandler,
    StatusCommandHandler,
)
from .protocol.handlers.state_manager import StateManager
from .protocol.handlers.tool_call_handler import ToolCallHandler
from .protocol.handlers.turn_lifecycle_manager import TurnLifecycleManager
from .protocol.session_runtime import SessionRuntimeRegistry
from .rpc_holder import ClientRPCServiceHolder
from .storage import SessionStorage
from .storage.global_policy_storage import GlobalPolicyStorage
from .tools.base import ToolRegistry as ToolRegistryProtocol
from .tools.registry import SimpleToolRegistry

logger = structlog.get_logger()

# Тип для observability debug mode (чтобы отличить от require_auth)
class ObservabilityDebug:
    """Marker type for observability debug mode."""
    def __init__(self, enabled: bool = False):
        self.enabled = enabled


class ObservabilityFlushManager:
    """Менеджер периодического flush observability данных в файлы.

    Запускает asyncio task для периодического flush и предоставляет
    метод для ручного flush при завершении сессии.

    Attributes:
        enabled: Включить ли periodic flush.
        flush_interval: Интервал flush в секундах.
    """

    def __init__(
        self,
        enabled: bool = True,
        flush_interval: int = 60,
    ) -> None:
        self.enabled = enabled
        self.flush_interval = flush_interval
        self._task: asyncio.Task | None = None

    async def start(
        self,
        tracer: Tracer,
        timeline: EventTimeline,
        metrics: MetricsTracker,
        span_exporter: FileSpanExporter,
        event_exporter: FileEventExporter,
        metrics_exporter: FileMetricsExporter,
    ) -> None:
        """Запустить periodic flush task.

        Args:
            tracer: Экземпляр Tracer.
            timeline: Экземпляр EventTimeline.
            metrics: Экземпляр MetricsTracker.
            span_exporter: Экземпляр FileSpanExporter.
            event_exporter: Экземпляр FileEventExporter.
            metrics_exporter: Экземпляр FileMetricsExporter.
        """
        if not self.enabled:
            logger.info("observability flush manager disabled")
            return

        self._tracer = tracer
        self._timeline = timeline
        self._metrics = metrics
        self._span_exporter = span_exporter
        self._event_exporter = event_exporter
        self._metrics_exporter = metrics_exporter

        self._task = asyncio.create_task(self._flush_loop())
        logger.info(
            "observability flush manager started",
            flush_interval=self.flush_interval,
        )

    async def _flush_loop(self) -> None:
        """Основной цикл периодического flush."""
        while True:
            try:
                await asyncio.sleep(self.flush_interval)
                await self.flush_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in observability flush loop: %s", e)

    async def flush_all(self) -> None:
        """Выполнить flush всех observability данных."""
        try:
            span_result = None
            event_result = None
            metrics_result = None

            span_exporter = getattr(self, "_span_exporter", None)
            if span_exporter:
                span_result = span_exporter.flush(getattr(self, "_tracer", None))

            event_exporter = getattr(self, "_event_exporter", None)
            if event_exporter:
                event_result = event_exporter.flush(getattr(self, "_timeline", None))

            metrics_exporter = getattr(self, "_metrics_exporter", None)
            if metrics_exporter:
                metrics_result = metrics_exporter.flush(getattr(self, "_metrics", None))

            if span_result or event_result or metrics_result:
                logger.debug(
                    "observability data flushed",
                    spans=bool(span_result),
                    events=bool(event_result),
                    metrics=bool(metrics_result),
                )
        except Exception as e:
            logger.error("Failed to flush observability data: %s", e)

    async def stop(self) -> None:
        """Остановить periodic flush и выполнить финальный flush."""
        if self._task:
            self._task.cancel()
            with suppress(Exception):
                await self._task

        # Финальный flush
        await self.flush_all()


class ObservabilityProvider(Provider):
    """Провайдер observability компонентов (APP scope).

    Создаёт и настраивает:
    - Tracer — span hierarchy для tracing LLM вызовов
    - EventTimeline — хронология событий сессии
    - MetricsTracker — автоматический сбор метрик
    - FileSpanExporter — экспорт span'ов в файлы
    - FileEventExporter — экспорт событий в файлы
    - FileMetricsExporter — экспорт метрик в файлы
    """

    @provide(scope=Scope.APP)
    def get_tracer(
        self,
        debug: Annotated[ObservabilityDebug, from_context(provides=ObservabilityDebug)],
    ) -> Tracer:
        """Создаёт Tracer для observability."""
        return Tracer(debug=debug.enabled)

    @provide(scope=Scope.APP)
    def get_event_timeline(
        self,
        debug: Annotated[ObservabilityDebug, from_context(provides=ObservabilityDebug)],
    ) -> EventTimeline:
        """Создаёт EventTimeline для записи событий сессии."""
        return EventTimeline(debug=debug.enabled)

    @provide(scope=Scope.APP)
    def get_metrics_tracker(
        self,
        debug: Annotated[ObservabilityDebug, from_context(provides=ObservabilityDebug)],
    ) -> MetricsTracker:
        """Создаёт MetricsTracker для сбора метрик."""
        return MetricsTracker(debug=debug.enabled)

    @provide(scope=Scope.APP)
    def get_file_span_exporter(
        self,
        config: Annotated[AppConfig, from_context(provides=AppConfig)],
    ) -> FileSpanExporter:
        """Создаёт FileSpanExporter для экспорта span'ов."""
        return FileSpanExporter(
            export_dir=config.observability.export_dir,
            max_file_size=config.observability.max_file_size,
        )

    @provide(scope=Scope.APP)
    def get_file_event_exporter(
        self,
        config: Annotated[AppConfig, from_context(provides=AppConfig)],
    ) -> FileEventExporter:
        """Создаёт FileEventExporter для экспорта событий."""
        return FileEventExporter(export_dir=config.observability.export_dir)

    @provide(scope=Scope.APP)
    def get_file_metrics_exporter(
        self,
        config: Annotated[AppConfig, from_context(provides=AppConfig)],
    ) -> FileMetricsExporter:
        """Создаёт FileMetricsExporter для экспорта метрик."""
        return FileMetricsExporter(export_dir=config.observability.export_dir)


class ObservabilityFlushProvider(Provider):
    """Провайдер менеджера периодического flush observability данных."""

    @provide(scope=Scope.APP)
    async def get_flush_manager(
        self,
        config: Annotated[AppConfig, from_context(provides=AppConfig)],
        tracer: Tracer,
        timeline: EventTimeline,
        metrics: MetricsTracker,
        span_exporter: FileSpanExporter,
        event_exporter: FileEventExporter,
        metrics_exporter: FileMetricsExporter,
    ) -> AsyncIterator[ObservabilityFlushManager]:
        """Создаёт и запускает ObservabilityFlushManager."""
        manager = ObservabilityFlushManager(
            enabled=config.observability.enabled,
            flush_interval=config.observability.flush_interval,
        )

        await manager.start(
            tracer=tracer,
            timeline=timeline,
            metrics=metrics,
            span_exporter=span_exporter,
            event_exporter=event_exporter,
            metrics_exporter=metrics_exporter,
        )

        yield manager

        # Cleanup — финальный flush при остановке
        await manager.stop()


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
    def get_execution_engine(
        self,
        tool_registry: ToolRegistryProtocol,
    ) -> ExecutionEngine:
        """Создаёт ExecutionEngine."""
        return ExecutionEngine(tool_registry=tool_registry)

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

        global_config = AgentsGlobalConfig(
            default_model=config.agents.default_model,
            max_steps=config.agents.max_steps,
        )
        registry = AgentRegistry(event_bus, agent_factory, global_config)
        await registry.initialize()
        return registry


class ManagersProvider(Provider):
    """Провайдер stateless менеджеров (APP scope)."""

    @provide(scope=Scope.APP)
    def get_state_manager(self) -> StateManager:
        """Менеджер состояния сессии."""
        return StateManager()

    @provide(scope=Scope.APP)
    def get_plan_builder(self) -> PlanBuilder:
        """Построитель планов выполнения."""
        return PlanBuilder()

    @provide(scope=Scope.APP)
    def get_turn_lifecycle_manager(self) -> TurnLifecycleManager:
        """Менеджер жизненного цикла prompt-turn."""
        return TurnLifecycleManager()

    @provide(scope=Scope.APP)
    def get_tool_call_handler(self) -> ToolCallHandler:
        """Обработчик tool calls."""
        return ToolCallHandler()

    @provide(scope=Scope.APP)
    def get_permission_manager(self) -> PermissionManager:
        """Менеджер разрешений."""
        return PermissionManager()

    @provide(scope=Scope.APP)
    def get_client_rpc_handler(self) -> ClientRPCHandler:
        """Обработчик agent→client RPC."""
        return ClientRPCHandler()


class SlashCommandsProvider(Provider):
    """Провайдер slash commands (APP scope)."""

    @provide(scope=Scope.APP)
    def get_command_registry(
        self,
        strategy_dispatcher: StrategyDispatcher,
    ) -> CommandRegistry:
        """Реестр команд."""
        from codelab.server.protocol.handlers.slash_commands.builtin.strategy import (
            StrategyCommandHandler,
        )

        registry = CommandRegistry()
        registry.register(StatusCommandHandler())
        registry.register(ModeCommandHandler())
        registry.register(StrategyCommandHandler(strategy_dispatcher))
        registry.register(HelpCommandHandler(registry))
        return registry

    @provide(scope=Scope.APP)
    def get_slash_command_router(
        self,
        command_registry: CommandRegistry,
    ) -> SlashCommandRouter:
        """Маршрутизатор slash команд."""
        return SlashCommandRouter(command_registry)


class StorageProvider(Provider):
    """Провайдер хранилищ (APP scope)."""

    @provide(scope=Scope.APP)
    def get_global_policy_storage(self) -> GlobalPolicyStorage:
        """Хранилище глобальных политик."""
        return GlobalPolicyStorage()

    @provide(scope=Scope.APP)
    async def get_global_policy_manager(
        self,
        storage: GlobalPolicyStorage,
    ) -> GlobalPolicyManager:
        """Менеджер глобальных политик с инициализацией."""
        manager = GlobalPolicyManager(storage=storage)
        await manager.initialize()
        return manager


class LLMProvider_(Provider):
    """Провайдер LLM провайдеров (APP scope)."""

    @provide(scope=Scope.APP)
    async def get_llm_provider(
        self,
        config: Annotated[AppConfig, from_context(provides=AppConfig)],
        registry: LLMProviderRegistry,
    ) -> LLMProvider:
        """Создаёт LLM провайдера через Registry.
        
        Registry автоматически инициализирует провайдер через default_config,
        установленный в RegistryProvider.get_llm_registry().
        """
        provider_id = config.llm.provider

        try:
            return await registry.get_provider(provider_id)
        except ProviderNotFoundError:
            # Fallback на mock если провайдер не зарегистрирован
            provider = MockLLMProvider()
            await provider.initialize(LLMConfig(
                model=config.llm.model,
                temperature=config.llm.temperature,
                max_tokens=config.llm.max_tokens,
                timeout=LLMTimeoutConfig(
                    connect=config.llm.timeout.connect,
                    read=config.llm.timeout.read,
                    write=config.llm.timeout.write,
                    pool=config.llm.timeout.pool,
                ),
            ))
            return provider


class ToolsProvider(Provider):
    """Провайдер инструментов (APP scope)."""

    @provide(scope=Scope.APP)
    def get_tool_registry(self) -> ToolRegistryProtocol:
        """Реестр инструментов."""
        return SimpleToolRegistry()


class RuntimeRegistryProvider(Provider):
    """Провайдер SessionRuntimeRegistry (REQUEST scope)."""

    @provide(scope=Scope.REQUEST)
    async def get_runtime_registry(self) -> AsyncIterator[SessionRuntimeRegistry]:
        """Реестр runtime-состояний сессий.

        Dishka автоматически вызовет cleanup() при выходе из REQUEST scope.
        """
        registry = SessionRuntimeRegistry()
        yield registry
        await registry.cleanup()


class AgentProvider(Provider):
    """Провайдер агентов (APP scope)."""

    @provide(scope=Scope.APP)
    def get_agent_orchestrator(
        self,
        config: Annotated[AppConfig, from_context(provides=AppConfig)],
        llm_provider: LLMProvider,
        tool_registry: ToolRegistryProtocol,
        llm_registry: LLMProviderRegistry,
    ) -> AgentOrchestrator:
        """Создаёт AgentOrchestrator."""
        orchestrator_config = OrchestratorConfig(
            enabled=True,
            agent_class="naive",
            model=config.llm.model,
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens,
            llm_provider_class=config.llm.provider,
            system_prompt=config.agent.system_prompt,
        )

        # Создать model resolver для multi-provider support
        from codelab.server.llm.resolver import ModelResolver

        model_resolver = ModelResolver(
            registry=llm_registry,
            default_provider=config.llm.provider,
            provider_configs=config.llm.providers,
        )

        return AgentOrchestrator(
            config=orchestrator_config,
            llm_provider=llm_provider,
            tool_registry=tool_registry,
            llm_registry=llm_registry,
            model_resolver=model_resolver,
        )


class PipelineProvider(Provider):
    """Провайдер pipeline стадий (APP scope)."""

    @provide(scope=Scope.APP)
    def get_system_prompt_builder(
        self,
        config: Annotated[AppConfig, from_context(provides=AppConfig)],
        agent_registry: AgentRegistry,
    ) -> SystemPromptBuilder:
        """Создаёт SystemPromptBuilder из конфигурации и AgentRegistry."""
        return SystemPromptBuilder(
            global_prompt=config.agent.system_prompt,
            agent_registry=agent_registry,
        )

    @provide(scope=Scope.APP)
    def get_llm_loop_stage(
        self,
        tool_registry: ToolRegistryProtocol,
        tool_call_handler: ToolCallHandler,
        permission_manager: PermissionManager,
        state_manager: StateManager,
        plan_builder: PlanBuilder,
        global_policy_manager: GlobalPolicyManager,
        tracer: Tracer,
        strategy_dispatcher: StrategyDispatcher,
        system_prompt_builder: SystemPromptBuilder,
    ) -> LLMLoopStage:
        """Стадия LLM loop."""
        from .protocol.handlers.pipeline.stages import LLMLoopStage
        return LLMLoopStage(
            tool_registry=tool_registry,
            tool_call_handler=tool_call_handler,
            permission_manager=permission_manager,
            state_manager=state_manager,
            plan_builder=plan_builder,
            system_prompt_builder=system_prompt_builder,
            global_policy_manager=global_policy_manager,
            tracer=tracer,
            strategy_dispatcher=strategy_dispatcher,
        )

    @provide(scope=Scope.APP)
    def get_prompt_pipeline(
        self,
        state_manager: StateManager,
        slash_router: SlashCommandRouter,
        plan_builder: PlanBuilder,
        turn_lifecycle_manager: TurnLifecycleManager,
        tool_registry: ToolRegistryProtocol,
        permission_manager: PermissionManager,
        llm_loop_stage: LLMLoopStage,
    ) -> PromptPipeline:
        """Собирает PromptPipeline из всех стадий."""
        from .protocol.handlers.pipeline import (
            PlanBuildingStage,
            SlashCommandStage,
            TurnLifecycleStage,
            ValidationStage,
        )
        from .protocol.handlers.pipeline.stages.directives import DirectivesStage

        return PromptPipeline(stages=[
            ValidationStage(state_manager),
            SlashCommandStage(slash_router),
            PlanBuildingStage(plan_builder),
            TurnLifecycleStage(turn_lifecycle_manager, action="open"),
            DirectivesStage(tool_registry, permission_manager),
            llm_loop_stage,
            TurnLifecycleStage(turn_lifecycle_manager, action="close"),
        ])


class PromptOrchestratorProvider(Provider):
    """Провайдер PromptOrchestrator (APP scope)."""

    @provide(scope=Scope.APP)
    def get_client_rpc_service_holder(self) -> ClientRPCServiceHolder:
        """Создаёт holder для ClientRPCService (обновляется per-request)."""
        return ClientRPCServiceHolder()

    @provide(scope=Scope.APP)
    def get_prompt_orchestrator(
        self,
        state_manager: StateManager,
        plan_builder: PlanBuilder,
        turn_lifecycle_manager: TurnLifecycleManager,
        tool_call_handler: ToolCallHandler,
        permission_manager: PermissionManager,
        client_rpc_handler: ClientRPCHandler,
        tool_registry: ToolRegistryProtocol,
        llm_loop_stage: LLMLoopStage,
        holder: ClientRPCServiceHolder,
        global_policy_manager: GlobalPolicyManager,
        command_registry: CommandRegistry,
        pipeline: PromptPipeline,
    ) -> PromptOrchestrator:
        """Создаёт PromptOrchestrator со всеми зависимостями."""
        return PromptOrchestrator(
            state_manager=state_manager,
            plan_builder=plan_builder,
            turn_lifecycle_manager=turn_lifecycle_manager,
            tool_call_handler=tool_call_handler,
            permission_manager=permission_manager,
            client_rpc_handler=client_rpc_handler,
            tool_registry=tool_registry,
            llm_loop_stage=llm_loop_stage,
            client_rpc_service_holder=holder,
            global_policy_manager=global_policy_manager,
            command_registry=command_registry,
            pipeline=pipeline,
        )


class RegistryProvider(Provider):
    """Провайдер LLM Registry и ConfigOptionBuilder (APP scope)."""

    @provide(scope=Scope.APP)
    def get_llm_registry(
        self,
        config: Annotated[AppConfig, from_context(provides=AppConfig)],
    ) -> LLMProviderRegistry:
        """Создаёт реестр провайдеров с ProviderInfo из AppConfig."""
        registry = LLMProviderRegistry()

        # Устанавливаем default config для автоинициализации провайдеров
        # Все провайдеры, получаемые через get_provider(), будут автоматически
        # инициализированы этой конфигурацией
        default_llm_config = LLMConfig(
            api_key=config.llm.api_key,
            model=config.llm.model,
            base_url=config.llm.base_url,
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens,
            timeout=LLMTimeoutConfig(
                connect=config.llm.timeout.connect,
                read=config.llm.timeout.read,
                write=config.llm.timeout.write,
                pool=config.llm.timeout.pool,
            ),
        )
        registry.set_default_config(default_llm_config)

        # Регистрируем провайдеры из AppConfig (загружено из TOML при load())
        for provider_id, provider_cfg in config.llm.providers.items():
            provider_info = provider_cfg.to_provider_info(provider_id)
            factory = self._get_provider_factory(provider_id)
            registry.register(provider_id, factory, info=provider_info)
            logger.debug(
                "provider registered from config",
                provider_id=provider_id,
                models_count=len(provider_cfg.models),
            )

        # Mock провайдер без TOML config
        if "mock" not in registry.get_registered_providers():
            registry.register("mock", lambda: MockLLMProvider())

        logger.info(
            "llm registry created",
            providers_count=len(registry.get_registered_providers()),
            models_count=len(registry.list_all_models()),
        )

        return registry

    @staticmethod
    def _get_provider_factory(provider_id: str):
        """Возвращает factory-функцию для провайдера."""
        from codelab.server.llm.providers.anthropic import AnthropicProvider
        from codelab.server.llm.providers.go import GoProvider
        from codelab.server.llm.providers.lmstudio import LMStudioProvider
        from codelab.server.llm.providers.ollama import OllamaProvider
        from codelab.server.llm.providers.openai import OpenAIProvider
        from codelab.server.llm.providers.openrouter import OpenRouterProvider
        from codelab.server.llm.providers.zen import ZenProvider

        factories = {
            "openai": OpenAIProvider,
            "openrouter": OpenRouterProvider,
            "anthropic": AnthropicProvider,
            "zen": ZenProvider,
            "go": GoProvider,
            "ollama": OllamaProvider,
            "lmstudio": LMStudioProvider,
        }
        return factories.get(provider_id, lambda: MockLLMProvider())

    @provide(scope=Scope.APP)
    def get_config_option_builder(
        self,
        registry: LLMProviderRegistry,
    ) -> ConfigOptionBuilder:
        """Создаёт билдер config options."""
        return ConfigOptionBuilder(registry)

    @provide(scope=Scope.APP)
    def get_model_resolver(
        self,
        config: Annotated[AppConfig, from_context(provides=AppConfig)],
        registry: LLMProviderRegistry,
    ) -> ModelResolver:
        """Создаёт ModelResolver для dynamic model selection.

        ModelResolver резолвит ссылки на модели в формате "provider/model"
        в конкретные LLMProvider экземпляры через Registry.
        Поддерживает кэширование на уровне сессии и инвалидацию
        при смене модели через session/set_config_option.
        """
        return ModelResolver(
            registry=registry,
            default_provider=config.llm.provider,
            provider_configs=config.llm.providers,
        )


class RequestProvider(Provider):
    """Провайдер REQUEST-scoped зависимостей (на WebSocket соединение)."""

    @provide(scope=Scope.REQUEST)
    def get_acp_protocol(
        self,
        require_auth: Annotated[bool, from_context(provides=bool)],
        auth_api_key: Annotated[str | None, from_context(provides=str | None)],
        storage: SessionStorage,
        agent_orchestrator: AgentOrchestrator,
        tool_registry: ToolRegistryProtocol,
        prompt_orchestrator: PromptOrchestrator,
        holder: ClientRPCServiceHolder,
        registry: LLMProviderRegistry,
        config_option_builder: ConfigOptionBuilder,
        runtime_registry: SessionRuntimeRegistry,
        agent_registry: AgentRegistry,
        strategy_registry: StrategyRegistry,
        command_registry: CommandRegistry,
        model_resolver: ModelResolver,
        trace_messages: Annotated[bool, from_context(provides="trace_messages")],
    ) -> ACPProtocol:
        """Создаёт ACPProtocol для текущего соединения."""
        # ClientRPCService создаётся вручную в handle_ws_request (требует runtime callback)
        # и устанавливается в holder перед созданием ACPProtocol
        client_rpc_service = holder.service

        # Создаем middleware для трассировки сообщений если включено
        middleware = []
        if trace_messages:
            from codelab.server.protocol.middleware.message_trace import (
                create_message_trace_middleware,
            )

            middleware.append(create_message_trace_middleware(enabled=True))

        return ACPProtocol(
            require_auth=require_auth,
            auth_api_key=auth_api_key,
            storage=storage,
            agent_orchestrator=agent_orchestrator,
            client_rpc_service=client_rpc_service,
            tool_registry=tool_registry,
            prompt_orchestrator=prompt_orchestrator,
            llm_registry=registry,
            config_option_builder=config_option_builder,
            middleware=middleware if middleware else None,
            runtime_registry=runtime_registry,
            agent_registry=agent_registry,
            strategy_registry=strategy_registry,
            command_registry=command_registry,
            model_resolver=model_resolver,
        )


def make_container(
    config: AppConfig,
    storage: SessionStorage,
    *,
    require_auth: bool = False,
    auth_api_key: str | None = None,
    trace_messages: bool = False,
    observability_debug: bool = False,
) -> AsyncContainer:
    """Создаёт DI контейнер со всеми провайдерами.

    Args:
        config: Глобальная конфигурация приложения.
        storage: Хранилище сессий.
        require_auth: Требовать аутентификацию.
        auth_api_key: API ключ для аутентификации.
        trace_messages: Включить детальное логирование всех JSON-RPC сообщений.
        observability_debug: Включить debug mode для observability (полные payload'ы).

    Returns:
        AsyncContainer для получения зависимостей.
    """
    container = make_async_container(
        ObservabilityProvider(),
        ObservabilityFlushProvider(),
        EventBusProvider(),
        MultiAgentProvider(),
        ManagersProvider(),
        SlashCommandsProvider(),
        StorageProvider(),
        RegistryProvider(),
        LLMProvider_(),
        ToolsProvider(),
        RuntimeRegistryProvider(),
        AgentProvider(),
        PipelineProvider(),
        PromptOrchestratorProvider(),
        RequestProvider(),
        context={
            AppConfig: config,
            SessionStorage: storage,
            bool: require_auth,
            str | None: auth_api_key,
            "trace_messages": trace_messages,
            ObservabilityDebug: ObservabilityDebug(observability_debug),
        },
    )
    return container

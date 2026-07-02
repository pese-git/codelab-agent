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
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from typing import Annotated, Any

import structlog
from dishka import (
    AsyncContainer,
    Provider,
    Scope,
    from_context,
    make_async_container,
    provide,
)

from .agent.context_compactor import ContextCompactor
from .agent.event_bus.bus import AgentEventBus, RetryConfig
from .agent.execution_engine import ExecutionEngine
from .agent.factory import AgentFactory
from .agent.registry import AgentRegistry
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
from .llm.scripted_mock import ScriptedMockLLMProvider
from .observability import EventTimeline, MetricsTracker, Tracer
from .observability.exporters import FileEventExporter, FileMetricsExporter, FileSpanExporter
from .protocol.background_executor import BackgroundExecutor
from .protocol.commands import (
    AuthenticateCommandHandler,
    InitializeCommandHandler,
    PermissionResponseCommandHandler,
    SessionCancelCommandHandler,
    SessionListCommandHandler,
    SessionLoadCommandHandler,
    SessionNewCommandHandler,
    SessionPromptCommandHandler,
    SetConfigOptionCommandHandler,
    SetModeCommandHandler,
)
from .protocol.commands import (
    CommandRegistry as MethodCommandRegistry,
)
from .protocol.config_spec_builder import ConfigSpecBuilder
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
from .protocol.mcp_session_manager import MCPSessionManager
from .protocol.orchestrator_builder import PromptOrchestratorBuilder
from .protocol.pending_registry import PendingRequestRegistry
from .protocol.response_router import ResponseRouter
from .protocol.session_runtime import SessionRuntimeRegistry
from .rpc_holder import ClientRPCServiceHolder
from .storage import SessionStorage
from .storage.global_policy_storage import GlobalPolicyStorage
from .tools.base import ToolRegistry as ToolRegistryProtocol
from .tools.registry import SimpleToolRegistry

logger = structlog.get_logger()


def _make_mock_provider() -> LLMProvider:
    """Создать mock-провайдер.

    Если задан CODELAB_MOCK_SCENARIO (путь к JSON-сценарию), возвращает
    сценарный ScriptedMockLLMProvider (конечный автомат для e2e-flow),
    иначе — обычный MockLLMProvider с дефолтным ответом.
    """
    scenario_path = os.getenv("CODELAB_MOCK_SCENARIO")
    if scenario_path:
        logger.info("loading scripted mock scenario", path=scenario_path)
        return ScriptedMockLLMProvider.from_file(scenario_path)
    return MockLLMProvider()


def _make_async_provider(value: Any) -> Callable[[], Awaitable[Any]]:
    """Создаёт async-функцию, возвращающую value.

    Используется для передачи синхронных значений в места,
    где ожидается async provider (Callable[[], Awaitable[T]]).
    """

    async def _provider() -> Any:
        return value

    return _provider

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
    def get_execution_engine(
        self,
        tool_registry: ToolRegistryProtocol,
        compactor: ContextCompactor,
    ) -> ExecutionEngine:
        """Создаёт ExecutionEngine с ContextCompactor.

        Compactor автоматически сжимает историю в build_context() и
        build_continuation_context() — это работает для всех стратегий
        (Single, Orchestrated, Hierarchical, Choreography) без дублирования.
        """
        return ExecutionEngine(
            tool_registry=tool_registry,
            compactor=compactor,
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


class PipelineProvider(Provider):
    """Провайдер pipeline стадий и builder-ов (APP scope)."""

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
        config: Annotated[AppConfig, from_context(provides=AppConfig)],
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
            streaming_enabled=config.llm.streaming,
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
    def get_orchestrator_builder(
        self,
        tool_registry: ToolRegistryProtocol,
        agent_registry: AgentRegistry,
        llm_loop_stage: LLMLoopStage,
        global_policy_manager: GlobalPolicyManager,
    ) -> PromptOrchestratorBuilder:
        """Создаёт PromptOrchestratorBuilder."""
        return PromptOrchestratorBuilder(
            tool_registry=tool_registry,
            agent_registry=agent_registry,
            llm_loop_stage=llm_loop_stage,
            global_policy_manager=global_policy_manager,
        )

    @provide(scope=Scope.APP)
    def get_prompt_orchestrator(
        self,
        builder: PromptOrchestratorBuilder,
        holder: ClientRPCServiceHolder,
    ) -> PromptOrchestrator:
        """Создаёт PromptOrchestrator через Builder."""
        orchestrator = builder.build()
        # Устанавливаем holder для client_rpc_service
        orchestrator.client_rpc_service_holder = holder
        return orchestrator


class ConfigSpecProvider(Provider):
    """Провайдер ConfigSpecBuilder (APP scope)."""

    @provide(scope=Scope.APP)
    def get_config_spec_builder(
        self,
        config_option_builder: ConfigOptionBuilder,
        agent_registry: AgentRegistry,
        strategy_registry: StrategyRegistry,
    ) -> ConfigSpecBuilder:
        """Создаёт ConfigSpecBuilder."""
        return ConfigSpecBuilder(
            config_option_builder=config_option_builder,
            agent_registry=agent_registry,
            strategy_registry=strategy_registry,
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
            registry.register("mock", _make_mock_provider)

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
        return factories.get(provider_id, _make_mock_provider)

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
    def get_pending_registry(self) -> PendingRequestRegistry:
        """Создаёт PendingRequestRegistry для текущего соединения."""
        return PendingRequestRegistry()

    @provide(scope=Scope.REQUEST)
    def get_response_router(
        self,
        storage: SessionStorage,
        pending_registry: PendingRequestRegistry,
        holder: ClientRPCServiceHolder,
    ) -> ResponseRouter:
        """Создаёт ResponseRouter для текущего соединения."""
        return ResponseRouter(
            storage=storage,
            pending_registry=pending_registry,
            client_rpc_service=holder.service,
        )

    @provide(scope=Scope.REQUEST)
    def get_method_command_registry(
        self,
        storage: SessionStorage,
        config_spec_builder: ConfigSpecBuilder,
        mcp_session_manager: MCPSessionManager,
        prompt_orchestrator: PromptOrchestrator,
        runtime_registry: SessionRuntimeRegistry,
        pending_registry: PendingRequestRegistry,
        model_resolver: ModelResolver,
        agent_factory: AgentFactory,
        require_auth: Annotated[bool, from_context(provides=bool)],
        auth_api_key: Annotated[str | None, from_context(provides=str | None)],
        command_registry: CommandRegistry,
    ) -> MethodCommandRegistry:
        """Создаёт CommandRegistry с CommandHandlers для текущего соединения.

        Создаётся per-request, т.к. CommandHandlers зависят от
        request-specific данных (authenticated, runtime_capabilities).
        """
        config_specs = config_spec_builder.build()

        auth_methods = [
            {
                "id": "local",
                "name": "Local authentication",
                "description": "Local authentication flow",
                "type": "api_key",
            }
        ]

        async def _on_session_created(session_state: Any, params: dict) -> None:
            await mcp_session_manager.setup_if_needed(session_state, params)

        async def _on_session_loaded(session_state: Any, params: dict) -> None:
            await mcp_session_manager.setup_if_needed(session_state, params)

        llm_adapter = agent_factory.get_primary_adapter()

        # Session-создающие хендлеры зависят от per-request negotiated состояния
        # (client runtime capabilities из initialize и auth-статуса из authenticate).
        # Создаём их заранее, чтобы initialize/authenticate могли обновлять их
        # через callback-и — иначе session/new получает runtime_capabilities=None
        # и tool-runtime считается недоступным.
        session_new_handler = SessionNewCommandHandler(
            storage=storage,
            config_specs=config_specs,
            auth_methods=auth_methods,
            require_auth=require_auth,
            authenticated=False,
            runtime_capabilities=None,
            command_registry=command_registry,
            on_session_created=_on_session_created,
        )
        session_load_handler = SessionLoadCommandHandler(
            storage=storage,
            config_specs=config_specs,
            auth_methods=auth_methods,
            require_auth=require_auth,
            authenticated=False,
            runtime_capabilities=None,
            pending_registry=pending_registry,
            on_session_loaded=_on_session_loaded,
        )

        # Callbacks для side effects: пробрасываем negotiated состояние в
        # session-создающие хендлеры.
        def _on_capabilities_negotiated(capabilities: Any) -> None:
            session_new_handler._runtime_capabilities = capabilities
            session_load_handler._runtime_capabilities = capabilities

        def _on_authenticated(authenticated: bool) -> None:
            session_new_handler._authenticated = authenticated
            session_load_handler._authenticated = authenticated

        registry = MethodCommandRegistry()
        registry.register(InitializeCommandHandler(
            supported_protocol_versions=(1,),
            require_auth=require_auth,
            auth_methods=auth_methods,
            on_capabilities_negotiated=_on_capabilities_negotiated,
        ))
        registry.register(AuthenticateCommandHandler(
            require_auth=require_auth,
            auth_api_key=auth_api_key,
            auth_methods=auth_methods,
            on_authenticated=_on_authenticated,
        ))
        registry.register(session_new_handler)
        registry.register(session_load_handler)
        registry.register(SessionListCommandHandler(
            storage=storage,
            page_size=50,
        ))
        registry.register(SessionPromptCommandHandler(
            storage=storage,
            orchestrator_provider=_make_async_provider(prompt_orchestrator),
            runtime_registry=runtime_registry,
            mcp_provider=mcp_session_manager.ensure_initialized,
        ))
        registry.register(SessionCancelCommandHandler(
            storage=storage,
            orchestrator_provider=_make_async_provider(prompt_orchestrator),
            llm_adapter=llm_adapter,
        ))
        registry.register(PermissionResponseCommandHandler(
            storage=storage,
        ))
        registry.register(SetConfigOptionCommandHandler(
            storage=storage,
            config_specs=config_specs,
            model_resolver=model_resolver,
        ))
        registry.register(SetModeCommandHandler(
            storage=storage,
            config_specs=config_specs,
        ))

        return registry

    @provide(scope=Scope.REQUEST)
    def get_mcp_session_manager(
        self,
        runtime_registry: SessionRuntimeRegistry,
        tool_registry: ToolRegistryProtocol,
    ) -> MCPSessionManager:
        """Создаёт MCPSessionManager для текущего соединения."""
        return MCPSessionManager(
            runtime_registry=runtime_registry,
            tool_registry=tool_registry,
        )

    @provide(scope=Scope.REQUEST)
    def get_background_executor(
        self,
        storage: SessionStorage,
        prompt_orchestrator: PromptOrchestrator,
        mcp_session_manager: MCPSessionManager,
        runtime_registry: SessionRuntimeRegistry,
    ) -> BackgroundExecutor:
        """Создаёт BackgroundExecutor для текущего соединения."""
        return BackgroundExecutor(
            storage=storage,
            orchestrator_provider=_make_async_provider(prompt_orchestrator),
            mcp_provider=mcp_session_manager.ensure_initialized,
            runtime_registry=runtime_registry,
        )

    @provide(scope=Scope.REQUEST)
    def get_acp_protocol(
        self,
        storage: SessionStorage,
        method_registry: MethodCommandRegistry,
        response_router: ResponseRouter,
        background_executor: BackgroundExecutor,
        pending_registry: PendingRequestRegistry,
        runtime_registry: SessionRuntimeRegistry,
        agent_factory: AgentFactory,
        prompt_orchestrator: PromptOrchestrator,
        trace_messages: Annotated[bool, from_context(provides="trace_messages")],
    ) -> ACPProtocol:
        """Создаёт ACPProtocol (Facade) для текущего соединения."""
        # Создаем middleware для трассировки сообщений если включено
        middleware = []
        if trace_messages:
            from codelab.server.protocol.middleware.message_trace import (
                create_message_trace_middleware,
            )
            middleware.append(create_message_trace_middleware(enabled=True))

        llm_adapter = agent_factory.get_primary_adapter()

        return ACPProtocol(
            storage=storage,
            method_registry=method_registry,
            response_router=response_router,
            background_executor=background_executor,
            pending_registry=pending_registry,
            runtime_registry=runtime_registry,
            middleware=middleware if middleware else None,
            llm_adapter=llm_adapter,
            orchestrator_provider=_make_async_provider(prompt_orchestrator),
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
        PipelineProvider(),
        PromptOrchestratorProvider(),
        ConfigSpecProvider(),
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

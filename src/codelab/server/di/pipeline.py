"""Провайдеры prompt-пайплайна и оркестратора (APP scope).

Стадии пайплайна, сборка PromptPipeline, PromptOrchestrator через Builder и
ConfigSpecBuilder.
"""

from __future__ import annotations

from typing import Annotated

from dishka import Provider, Scope, from_context, provide

from ..agent.context.file_cache import SessionFileCacheRegistry
from ..agent.core.strategies.dispatcher import StrategyDispatcher
from ..agent.core.strategies.registry import StrategyRegistry
from ..agent.core.system_prompt_builder import SystemPromptBuilder
from ..agent.registry import AgentRegistry
from ..config import AppConfig
from ..observability import Tracer
from ..protocol.config_spec_builder import ConfigSpecBuilder
from ..protocol.handlers.config_option_builder import ConfigOptionBuilder
from ..protocol.handlers.global_policy_manager import GlobalPolicyManager
from ..protocol.handlers.permission_manager import PermissionManager
from ..protocol.handlers.pipeline import PromptPipeline
from ..protocol.handlers.pipeline.stages import LLMLoopStage
from ..protocol.handlers.plan_builder import PlanBuilder
from ..protocol.handlers.prompt_orchestrator import PromptOrchestrator
from ..protocol.handlers.slash_commands import CommandRegistry, SlashCommandRouter
from ..protocol.handlers.state_manager import StateManager
from ..protocol.handlers.tool_call_handler import ToolCallHandler
from ..protocol.handlers.turn_lifecycle_manager import TurnLifecycleManager
from ..protocol.orchestrator_builder import PromptOrchestratorBuilder
from ..protocol.turn_cancellation import TurnCancellationRegistry
from ..rpc_holder import ClientRPCServiceHolder
from ..tools.base import ToolRegistry as ToolRegistryProtocol
from ..tools.executors.terminal_alias_registry import TerminalAliasRegistry


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
        turn_cancellation: TurnCancellationRegistry,
        config: Annotated[AppConfig, from_context(provides=AppConfig)],
    ) -> LLMLoopStage:
        """Стадия LLM loop."""
        from ..protocol.handlers.pipeline.stages import LLMLoopStage

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
            loop_guard_limit=config.agent.tool_loop_guard_limit,
            turn_cancellation=turn_cancellation,
        )

    @provide(scope=Scope.APP)
    def get_turn_cancellation(self) -> TurnCancellationRegistry:
        """Процессный реестр отмены turn'ов (P0-39).

        APP-scope обязателен: сигнал должен переживать границу запроса, иначе
        отмена и идущий turn окажутся в разных экземплярах.
        """
        return TurnCancellationRegistry()

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
        from ..protocol.handlers.pipeline import (
            PlanBuildingStage,
            SlashCommandStage,
            TurnLifecycleStage,
            ValidationStage,
        )
        from ..protocol.handlers.pipeline.stages.directives import DirectivesStage

        return PromptPipeline(
            stages=[
                ValidationStage(),
                SlashCommandStage(slash_router),
                PlanBuildingStage(plan_builder),
                TurnLifecycleStage(turn_lifecycle_manager, action="open"),
                DirectivesStage(tool_registry, permission_manager),
                llm_loop_stage,
                TurnLifecycleStage(turn_lifecycle_manager, action="close"),
            ]
        )


class PromptOrchestratorProvider(Provider):
    """Провайдер PromptOrchestrator (APP scope)."""

    @provide(scope=Scope.APP)
    def get_client_rpc_service_holder(self) -> ClientRPCServiceHolder:
        """Создаёт holder для ClientRPCService (обновляется per-request)."""
        return ClientRPCServiceHolder()

    @provide(scope=Scope.APP)
    def get_terminal_alias_registry(self) -> TerminalAliasRegistry:
        """Процессный реестр alias'ов терминалов (ADR-007 шаг A, ADR-008 шаг 5.3).

        APP-scope обязателен: связка alias → client terminalId не персистится, и
        второй экземпляр означал бы alias, выданный одним и неразрешимый другим.
        Прежде реестр создавался внутри executor'а, а единственность держалась на
        том, что точка создания одна, — на дисциплине того же рода, что однажды не
        сработала у `terminal_counter`.
        """
        return TerminalAliasRegistry()

    @provide(scope=Scope.APP)
    def get_orchestrator_builder(
        self,
        tool_registry: ToolRegistryProtocol,
        agent_registry: AgentRegistry,
        llm_loop_stage: LLMLoopStage,
        command_registry: CommandRegistry,
        slash_router: SlashCommandRouter,
        global_policy_manager: GlobalPolicyManager,
        session_file_cache_registry: SessionFileCacheRegistry,
        turn_cancellation: TurnCancellationRegistry,
        terminal_aliases: TerminalAliasRegistry,
    ) -> PromptOrchestratorBuilder:
        """Создаёт PromptOrchestratorBuilder."""
        return PromptOrchestratorBuilder(
            tool_registry=tool_registry,
            agent_registry=agent_registry,
            llm_loop_stage=llm_loop_stage,
            command_registry=command_registry,
            slash_router=slash_router,
            global_policy_manager=global_policy_manager,
            session_file_cache_registry=session_file_cache_registry,
            turn_cancellation=turn_cancellation,
            terminal_aliases=terminal_aliases,
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

"""PromptOrchestratorBuilder — Builder для PromptOrchestrator.

Инкапсулирует сложную сборку PromptOrchestrator с 12+ компонентами.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agent.registry import AgentRegistry
    from ..client_rpc.service import ClientRPCService
    from ..tools.base import ToolRegistry
    from .handlers.global_policy_manager import GlobalPolicyManager
    from .handlers.pipeline.stages import LLMLoopStage
    from .handlers.prompt_orchestrator import PromptOrchestrator


class PromptOrchestratorBuilder:
    """Builder для PromptOrchestrator.

    Инкапсулирует сложную сборку с 12+ компонентами:
    - StateManager, PlanBuilder, TurnLifecycleManager
    - ToolCallHandler, PermissionManager, ClientRPCHandler
    - SystemPromptBuilder, LLMLoopStage
    - SlashCommandRouter, CommandRegistry
    - PromptPipeline

    Attributes:
        tool_registry: Глобальный реестр инструментов.
        agent_registry: Реестр агентов.
        llm_loop_stage: Стадия LLM loop (с strategy_dispatcher и tracer).
        global_policy_manager: Менеджер глобальных политик.
        client_rpc_service: Сервис для agent->client RPC.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        agent_registry: AgentRegistry,
        llm_loop_stage: LLMLoopStage,
        global_policy_manager: GlobalPolicyManager | None = None,
        client_rpc_service: ClientRPCService | None = None,
    ) -> None:
        """Инициализирует PromptOrchestratorBuilder.

        Args:
            tool_registry: Глобальный реестр инструментов.
            agent_registry: Реестр агентов.
            llm_loop_stage: Стадия LLM loop (с strategy_dispatcher и tracer).
            global_policy_manager: Менеджер глобальных политик (опционально).
            client_rpc_service: Сервис для agent->client RPC (опционально).
        """
        self._tool_registry = tool_registry
        self._agent_registry = agent_registry
        self._llm_loop_stage = llm_loop_stage
        self._global_policy_manager = global_policy_manager
        self._client_rpc_service = client_rpc_service

    def build(self) -> PromptOrchestrator:
        """Собирает PromptOrchestrator со всеми зависимостями.

        Returns:
            Полностью сконфигурированный PromptOrchestrator.
        """
        # Локальные импорты для избежания circular imports
        from .handlers.client_rpc_handler import ClientRPCHandler
        from .handlers.permission_manager import PermissionManager
        from .handlers.pipeline import (
            PlanBuildingStage,
            PromptPipeline,
            SlashCommandStage,
            TurnLifecycleStage,
            ValidationStage,
        )
        from .handlers.pipeline.stages.directives import DirectivesStage
        from .handlers.plan_builder import PlanBuilder
        from .handlers.prompt_orchestrator import PromptOrchestrator
        from .handlers.slash_commands import CommandRegistry, SlashCommandRouter
        from .handlers.slash_commands.builtin import (
            HelpCommandHandler,
            ModeCommandHandler,
            StatusCommandHandler,
        )
        from .handlers.state_manager import StateManager
        from .handlers.tool_call_handler import ToolCallHandler
        from .handlers.turn_lifecycle_manager import TurnLifecycleManager

        # Создаём stateless менеджеры
        state_manager = StateManager()
        plan_builder = PlanBuilder()
        turn_lifecycle_manager = TurnLifecycleManager()
        tool_call_handler = ToolCallHandler()
        permission_manager = PermissionManager()
        client_rpc_handler = ClientRPCHandler()

        # Slash commands
        command_registry = CommandRegistry()
        slash_router = SlashCommandRouter(command_registry)
        command_registry.register(StatusCommandHandler())
        command_registry.register(ModeCommandHandler())
        command_registry.register(HelpCommandHandler(command_registry))

        # Собираем pipeline — используем готовый LLMLoopStage из DI
        pipeline = PromptPipeline(stages=[
            ValidationStage(state_manager),
            SlashCommandStage(slash_router),
            PlanBuildingStage(plan_builder),
            TurnLifecycleStage(turn_lifecycle_manager, action="open"),
            DirectivesStage(self._tool_registry, permission_manager),
            self._llm_loop_stage,
            TurnLifecycleStage(turn_lifecycle_manager, action="close"),
        ])

        # Финальный объект
        return PromptOrchestrator(
            state_manager=state_manager,
            plan_builder=plan_builder,
            turn_lifecycle_manager=turn_lifecycle_manager,
            tool_call_handler=tool_call_handler,
            permission_manager=permission_manager,
            client_rpc_handler=client_rpc_handler,
            tool_registry=self._tool_registry,
            llm_loop_stage=self._llm_loop_stage,
            client_rpc_service=self._client_rpc_service,
            global_policy_manager=self._global_policy_manager,
            command_registry=command_registry,
            pipeline=pipeline,
        )

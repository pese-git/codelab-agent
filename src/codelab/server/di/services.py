"""Провайдеры leaf-сервисов протокольного слоя (APP scope).

Stateless-менеджеры, реестр инструментов, хранилище глобальных политик и
реестр/маршрутизатор slash-команд.
"""

from __future__ import annotations

from dishka import Provider, Scope, provide

from ..agent.strategies.dispatcher import StrategyDispatcher
from ..config import AppConfig
from ..observability import MetricsTracker, Tracer
from ..protocol.handlers.client_rpc_handler import ClientRPCHandler
from ..protocol.handlers.global_policy_manager import GlobalPolicyManager
from ..protocol.handlers.permission_manager import PermissionManager
from ..protocol.handlers.plan_builder import PlanBuilder
from ..protocol.handlers.slash_commands import CommandRegistry, SlashCommandRouter
from ..protocol.handlers.slash_commands.builtin import (
    HelpCommandHandler,
    ModeCommandHandler,
    StatusCommandHandler,
)
from ..protocol.handlers.state_manager import StateManager
from ..protocol.handlers.tool_call_handler import ToolCallHandler
from ..protocol.handlers.turn_lifecycle_manager import TurnLifecycleManager
from ..storage.global_policy_storage import GlobalPolicyStorage
from ..tools.base import ToolRegistry as ToolRegistryProtocol
from ..tools.registry import SimpleToolRegistry


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
        metrics_tracker: MetricsTracker,
        tracer: Tracer,
        config: AppConfig,
    ) -> CommandRegistry:
        """Реестр команд."""
        from codelab.server.protocol.handlers.slash_commands.builtin.context import (
            ContextCommandHandler,
        )
        from codelab.server.protocol.handlers.slash_commands.builtin.strategy import (
            StrategyCommandHandler,
        )

        registry = CommandRegistry()
        registry.register(StatusCommandHandler())
        registry.register(ModeCommandHandler())
        registry.register(StrategyCommandHandler(strategy_dispatcher))
        registry.register(ContextCommandHandler(metrics_tracker, config.agents.context, tracer))
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


class ToolsProvider(Provider):
    """Провайдер инструментов (APP scope)."""

    @provide(scope=Scope.APP)
    def get_tool_registry(self) -> ToolRegistryProtocol:
        """Реестр инструментов."""
        return SimpleToolRegistry()

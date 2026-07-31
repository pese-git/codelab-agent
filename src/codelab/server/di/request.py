"""Провайдеры REQUEST-scoped зависимостей (на одно WebSocket соединение).

Реестр runtime-состояний сессий, per-request реестр методов ACP с
command-handler'ами, MCP session manager, background executor и фасад ACPProtocol.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated, Any

from dishka import Provider, Scope, from_context, provide

from ..agent.factory import AgentFactory
from ..llm.resolver import ModelResolver
from ..protocol.background_executor import BackgroundExecutor
from ..protocol.commands import (
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
from ..protocol.commands import (
    CommandRegistry as MethodCommandRegistry,
)
from ..protocol.config_spec_builder import ConfigSpecBuilder
from ..protocol.core import ACPProtocol
from ..protocol.handlers.prompt_orchestrator import PromptOrchestrator
from ..protocol.handlers.slash_commands import CommandRegistry
from ..protocol.mcp_session_manager import MCPSessionManager
from ..protocol.pending_registry import PendingRequestRegistry
from ..protocol.response_router import ResponseRouter
from ..protocol.session_runtime import SessionRuntimeRegistry
from ..protocol.state import ClientRuntimeCapabilities, SessionState
from ..rpc_holder import ClientRPCServiceHolder
from ..storage import SessionRepository, SessionStorage
from ..tools.base import ToolRegistry as ToolRegistryProtocol


def _make_async_provider(value: Any) -> Callable[[], Awaitable[Any]]:
    """Создаёт async-функцию, возвращающую value.

    Используется для передачи синхронных значений в места,
    где ожидается async provider (Callable[[], Awaitable[T]]).
    """

    async def _provider() -> Any:
        return value

    return _provider


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
        repository: SessionRepository,
        pending_registry: PendingRequestRegistry,
        holder: ClientRPCServiceHolder,
    ) -> ResponseRouter:
        """Создаёт ResponseRouter для текущего соединения."""
        return ResponseRouter(
            storage=storage,
            repository=repository,
            pending_registry=pending_registry,
            client_rpc_service=holder.service,
        )

    @provide(scope=Scope.REQUEST)
    def get_method_command_registry(
        self,
        storage: SessionStorage,
        repository: SessionRepository,
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

        async def _on_session_created(session_state: SessionState, params: dict) -> None:
            await mcp_session_manager.setup_if_needed(session_state, params)

        async def _on_session_loaded(session_state: SessionState, params: dict) -> None:
            await mcp_session_manager.setup_if_needed(session_state, params)

        llm_adapter = agent_factory.get_primary_adapter()

        # Session-создающие хендлеры зависят от per-request negotiated состояния
        # (client runtime capabilities из initialize и auth-статуса из authenticate).
        # Создаём их заранее, чтобы initialize/authenticate могли обновлять их
        # через callback-и — иначе session/new получает runtime_capabilities=None
        # и tool-runtime считается недоступным.
        session_new_handler = SessionNewCommandHandler(
            repository=repository,
            config_specs=config_specs,
            auth_methods=auth_methods,
            require_auth=require_auth,
            authenticated=False,
            runtime_capabilities=None,
            command_registry=command_registry,
            on_session_created=_on_session_created,
        )
        session_load_handler = SessionLoadCommandHandler(
            repository=repository,
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
        def _on_capabilities_negotiated(capabilities: ClientRuntimeCapabilities | None) -> None:
            session_new_handler._runtime_capabilities = capabilities
            session_load_handler._runtime_capabilities = capabilities

        def _on_authenticated(authenticated: bool) -> None:
            session_new_handler._authenticated = authenticated
            session_load_handler._authenticated = authenticated

        registry = MethodCommandRegistry()
        registry.register(
            InitializeCommandHandler(
                supported_protocol_versions=(1,),
                require_auth=require_auth,
                auth_methods=auth_methods,
                on_capabilities_negotiated=_on_capabilities_negotiated,
            )
        )
        registry.register(
            AuthenticateCommandHandler(
                require_auth=require_auth,
                auth_api_key=auth_api_key,
                auth_methods=auth_methods,
                on_authenticated=_on_authenticated,
            )
        )
        registry.register(session_new_handler)
        registry.register(session_load_handler)
        registry.register(
            SessionListCommandHandler(
                repository=repository,
                page_size=50,
            )
        )
        registry.register(
            SessionPromptCommandHandler(
                storage=storage,
                orchestrator_provider=_make_async_provider(prompt_orchestrator),
                runtime_registry=runtime_registry,
                mcp_provider=mcp_session_manager.ensure_initialized,
            )
        )
        registry.register(
            SessionCancelCommandHandler(
                repository=repository,
                orchestrator_provider=_make_async_provider(prompt_orchestrator),
                llm_adapter=llm_adapter,
            )
        )
        registry.register(
            PermissionResponseCommandHandler(
                storage=storage,
                repository=repository,
            )
        )
        registry.register(
            SetConfigOptionCommandHandler(
                repository=repository,
                config_specs=config_specs,
                model_resolver=model_resolver,
            )
        )
        registry.register(
            SetModeCommandHandler(
                repository=repository,
                config_specs=config_specs,
            )
        )

        return registry

    @provide(scope=Scope.REQUEST)
    def get_mcp_session_manager(
        self,
        runtime_registry: SessionRuntimeRegistry,
        tool_registry: ToolRegistryProtocol,
        command_registry: CommandRegistry,
    ) -> MCPSessionManager:
        """Создаёт MCPSessionManager для текущего соединения."""
        return MCPSessionManager(
            runtime_registry=runtime_registry,
            tool_registry=tool_registry,
            command_registry=command_registry,
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
        repository: SessionRepository,
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
            repository=repository,
            method_registry=method_registry,
            response_router=response_router,
            background_executor=background_executor,
            pending_registry=pending_registry,
            runtime_registry=runtime_registry,
            middleware=middleware if middleware else None,
            llm_adapter=llm_adapter,
            orchestrator_provider=_make_async_provider(prompt_orchestrator),
        )

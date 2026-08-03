"""Тест-фабрика для построения ACPProtocol без DI-контейнера.

Раньше эту сборку («default self-wiring») делал сам `ACPProtocol.__init__`
через legacy-ветки и `_create_default_method_registry`. В проде протокол
всегда создаётся через DI (`codelab.server.di.make_container`), а legacy-путь
использовался только тестами. Чтобы убрать legacy из продакшн-кода, вся эта
сборка перенесена сюда.

Использование:
    from tests.server._protocol_factory import build_protocol

    protocol = build_protocol()                       # дефолты
    protocol = build_protocol(send_callback=cb)        # с capture нотификаций
    protocol = build_protocol(client_rpc_service=svc)  # с agent->client RPC

Возвращает полностью собранный `ACPProtocol` (Facade) с реальными
компонентами — теми же командными обёртками, что использовались в legacy-пути,
так что поведение идентично старому `ACPProtocol(...)`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from codelab.server.messages import ACPMessage
from codelab.server.protocol.core import ACPProtocol
from codelab.server.protocol.pending_registry import PendingRequestRegistry
from codelab.server.protocol.session_runtime import SessionRuntimeRegistry
from codelab.server.protocol.state import ProtocolOutcome

if TYPE_CHECKING:
    from codelab.server.protocol.commands.base import CommandRegistry


class _Assembler:
    """Держатель per-connection состояния и ленивых компонентов.

    Командные обёртки читают/пишут состояние здесь (раньше — прямо на
    ACPProtocol). Атрибуты названы как в старом фасаде (`_require_auth`, ...),
    чтобы тела обёрток совпадали с legacy один-в-один.
    """

    _supported_protocol_versions = (1,)

    def __init__(self, **kw: Any) -> None:
        from codelab.server.storage import InMemoryStorage, SessionRepository

        self._storage = kw.get("storage") or InMemoryStorage()
        # Доменный порт над тем же backend — как в DI (write-фаза D4-d1, ADR-006).
        self._repository = SessionRepository(backend=self._storage)
        self._pending_registry = kw.get("pending_registry") or PendingRequestRegistry()
        self._runtime_registry = kw.get("runtime_registry") or SessionRuntimeRegistry()
        self._require_auth = kw.get("require_auth", False)
        self._auth_api_key = kw.get("auth_api_key")
        self._client_rpc_service = kw.get("client_rpc_service")
        self._tool_registry = kw.get("tool_registry")
        self._prompt_orchestrator = kw.get("prompt_orchestrator")
        self._global_policy_manager = kw.get("global_policy_manager")
        self._agent_registry = kw.get("agent_registry")
        self._strategy_registry = kw.get("strategy_registry")
        self._command_registry = kw.get("command_registry")
        self._config_option_builder = kw.get("config_option_builder")
        self._model_resolver = kw.get("model_resolver")
        self._mcp_http_enabled = kw.get("mcp_http_enabled", True)
        self._mcp_sse_enabled = kw.get("mcp_sse_enabled", True)
        self._authenticated = False
        self._runtime_capabilities: Any | None = None
        self._auth_methods: list[dict[str, Any]] = [
            {
                "id": "local",
                "name": "Local authentication",
                "description": "Local authentication flow",
                "type": "api_key",
            }
        ]
        self._mcp_session_manager: Any | None = None
        self._config_specs: dict[str, dict[str, Any]] = self._build_config_specs()

    # ── config specs ────────────────────────────────────────────────────────
    def _build_config_specs(self) -> dict[str, dict[str, Any]]:
        from codelab.server.protocol.config_spec_builder import ConfigSpecBuilder

        return ConfigSpecBuilder(
            config_option_builder=self._config_option_builder,
            agent_registry=self._agent_registry,
            strategy_registry=self._strategy_registry,
        ).build()

    # ── MCP ──────────────────────────────────────────────────────────────────
    def get_mcp_session_manager(self) -> Any:
        if self._mcp_session_manager is not None:
            return self._mcp_session_manager
        if self._tool_registry is None:
            from codelab.server.tools.registry import SimpleToolRegistry

            self._tool_registry = SimpleToolRegistry()
        from codelab.server.protocol.mcp_session_manager import MCPSessionManager

        self._mcp_session_manager = MCPSessionManager(
            runtime_registry=self._runtime_registry,
            tool_registry=self._tool_registry,
        )
        return self._mcp_session_manager

    async def ensure_mcp_initialized(self, session: Any) -> Any:
        return await self.get_mcp_session_manager().ensure_initialized(session)

    # ── orchestrator ──────────────────────────────────────────────────────────
    async def get_prompt_orchestrator(self) -> Any:
        if self._prompt_orchestrator is not None:
            return self._prompt_orchestrator

        from codelab.server.agent.core.system_prompt_builder import SystemPromptBuilder
        from codelab.server.protocol.handlers.permission_manager import PermissionManager
        from codelab.server.protocol.handlers.pipeline.stages import LLMLoopStage
        from codelab.server.protocol.handlers.plan_builder import PlanBuilder
        from codelab.server.protocol.handlers.slash_commands import (
            CommandRegistry,
            SlashCommandRouter,
        )
        from codelab.server.protocol.handlers.slash_commands.builtin import (
            ContextCommandHandler,
            HelpCommandHandler,
            ModeCommandHandler,
            StatusCommandHandler,
        )
        from codelab.server.protocol.handlers.state_manager import StateManager
        from codelab.server.protocol.handlers.tool_call_handler import ToolCallHandler
        from codelab.server.protocol.orchestrator_builder import PromptOrchestratorBuilder

        if self._tool_registry is None:
            from codelab.server.tools.registry import SimpleToolRegistry

            self._tool_registry = SimpleToolRegistry()

        llm_loop_stage = LLMLoopStage(
            tool_registry=self._tool_registry,
            tool_call_handler=ToolCallHandler(),
            permission_manager=PermissionManager(),
            state_manager=StateManager(),
            plan_builder=PlanBuilder(),
            system_prompt_builder=SystemPromptBuilder(
                global_prompt="",
                agent_registry=self._agent_registry,
            ),
            global_policy_manager=self._global_policy_manager,
        )

        # Создаём зависимости для slash-команд
        from codelab.server.agent.context.models import ContextConfig
        from codelab.server.observability.metrics_tracker import MetricsTracker
        from codelab.server.observability.tracer import Tracer

        metrics_tracker = MetricsTracker()
        context_config = ContextConfig()
        tracer = Tracer()

        command_registry = CommandRegistry()
        command_registry.register(StatusCommandHandler())
        command_registry.register(ModeCommandHandler())
        # StrategyCommandHandler требует StrategyDispatcher — пропускаем в тестах
        command_registry.register(ContextCommandHandler(metrics_tracker, context_config, tracer))
        command_registry.register(HelpCommandHandler(command_registry))
        slash_router = SlashCommandRouter(command_registry)

        # Сохраняем registry для использования в session/new
        self._command_registry = command_registry

        builder = PromptOrchestratorBuilder(
            tool_registry=self._tool_registry,
            agent_registry=self._agent_registry,
            llm_loop_stage=llm_loop_stage,
            command_registry=command_registry,
            slash_router=slash_router,
            global_policy_manager=self._global_policy_manager,
            client_rpc_service=self._client_rpc_service,
        )
        self._prompt_orchestrator = builder.build()
        return self._prompt_orchestrator


def _build_method_registry(st: _Assembler) -> CommandRegistry:
    """Создаёт CommandRegistry с обёртками, читающими состояние из `st`."""
    from codelab.server.protocol.commands.base import CommandRegistry
    from codelab.server.protocol.handlers import auth, config, session

    registry = CommandRegistry()

    class _InitializeWrapper:
        method_name = "initialize"

        async def handle(self, message: ACPMessage) -> ProtocolOutcome:
            params = message.params or {}
            response = auth.initialize(
                message.id,
                params,
                st._supported_protocol_versions,
                st._require_auth,
                st._auth_methods,
                mcp_http_enabled=st._mcp_http_enabled,
                mcp_sse_enabled=st._mcp_sse_enabled,
            )
            client_capabilities = params.get("clientCapabilities")
            if isinstance(client_capabilities, dict):
                st._runtime_capabilities = auth.parse_client_runtime_capabilities(
                    client_capabilities
                )
            return ProtocolOutcome(response=response)

    class _AuthenticateWrapper:
        method_name = "authenticate"

        async def handle(self, message: ACPMessage) -> ProtocolOutcome:
            params = message.params or {}
            response, authenticated = auth.authenticate(
                message.id,
                params,
                st._require_auth,
                st._auth_api_key,
                st._auth_methods,
            )
            st._authenticated = authenticated
            return ProtocolOutcome(response=response)

    class _SessionNewWrapper:
        """Делегирует прод-обработчику: порядок «создать → side effects → запись».

        Копия тела расходилась с кодом, который проверяет: в проде конверсия в
        домен идёт ДО MCP-setup, чтобы его правки `available_commands` уехали на
        диск (ADR-006, фаза D шаг 5). Обёртка, повторявшая шаги вручную, этот
        порядок не воспроизводила.
        """

        method_name = "session/new"

        async def handle(self, message: ACPMessage) -> ProtocolOutcome:
            from codelab.server.protocol.commands import SessionNewCommandHandler

            async def _on_session_created(created: Any, params: dict) -> None:
                await st.get_mcp_session_manager().setup_if_needed(created, params)

            handler = SessionNewCommandHandler(
                repository=st._repository,
                config_specs=st._config_specs,
                auth_methods=st._auth_methods,
                require_auth=st._require_auth,
                authenticated=st._authenticated,
                runtime_capabilities=st._runtime_capabilities,
                command_registry=st._command_registry,
                on_session_created=_on_session_created,
            )
            return await handler.handle(message)

    class _SessionLoadWrapper:
        """Делегирует прод-обработчику: запись решений загрузки живёт в нём.

        Раньше обёртка звала функцию реплея напрямую и опиралась на то, что
        `InMemoryStorage` отдаёт тот же объект, — то есть проверяла свойство
        хранилища, а не поведение сервера. На файловом бэкенде и после переезда
        загрузки на доменный агрегат (ADR-006, шаг 5) это разошлось бы молча.
        """

        method_name = "session/load"

        async def handle(self, message: ACPMessage) -> ProtocolOutcome:
            from codelab.server.protocol.commands import SessionLoadCommandHandler

            async def _on_session_loaded(session_state: Any, params: dict) -> None:
                await st.get_mcp_session_manager().setup_if_needed(session_state, params)

            handler = SessionLoadCommandHandler(
                repository=st._repository,
                config_specs=st._config_specs,
                auth_methods=st._auth_methods,
                require_auth=st._require_auth,
                authenticated=st._authenticated,
                runtime_capabilities=st._runtime_capabilities,
                pending_registry=st._pending_registry,
                on_session_loaded=_on_session_loaded,
            )
            return await handler.handle(message)

    class _SessionListWrapper:
        method_name = "session/list"

        async def handle(self, message: ACPMessage) -> ProtocolOutcome:
            params = message.params or {}
            response = await session.session_list(message.id, params, st._repository, 50)
            return ProtocolOutcome(response=response)

    class _SessionPromptWrapper:
        """Делегирует прод-обработчику по той же причине, что и отмена.

        Копия тела расходилась бы с кодом, который проверяет: с переездом turn'а на
        доменный агрегат (фаза D ADR-006) она разошлась бы ещё и по типу рабочей
        модели, и по тому, из чего собирается wire-документ на записи.
        """

        method_name = "session/prompt"

        async def handle(self, message: ACPMessage) -> ProtocolOutcome:
            from codelab.server.protocol.commands import SessionPromptCommandHandler

            handler = SessionPromptCommandHandler(
                repository=st._repository,
                orchestrator_provider=st.get_prompt_orchestrator,
                runtime_registry=st._runtime_registry,
                mcp_provider=st.ensure_mcp_initialized,
                notification_callback=st._send_message,
            )
            return await handler.handle(message)

    class _SessionCancelWrapper:
        """Делегирует прод-обработчику: транзакция отмены живёт в нём.

        Раньше обёртка воспроизводила тело обработчика (load → handle_cancel →
        два save) и переставала зависеть от кода, который проверяет. С переездом
        транзакции на доменный агрегат (фаза D ADR-006) копия ещё и разошлась бы
        по типу рабочей модели.
        """

        method_name = "session/cancel"

        async def handle(self, message: ACPMessage) -> ProtocolOutcome:
            from codelab.server.protocol.commands import SessionCancelCommandHandler

            handler = SessionCancelCommandHandler(
                repository=st._repository,
                orchestrator_provider=st.get_prompt_orchestrator,
                llm_adapter=st._llm_adapter,
            )
            return await handler.handle(message)

    class _PermissionResponseWrapper:
        method_name = "session/request_permission_response"

        async def handle(self, message: ACPMessage) -> ProtocolOutcome:
            if message.id is None:
                return ProtocolOutcome(
                    response=ACPMessage.error_response(
                        None, code=-32600, message="Invalid Request: id is required"
                    )
                )
            return ProtocolOutcome(response=ACPMessage.response(message.id, {}))

    class _SetConfigOptionWrapper:
        method_name = "session/set_config_option"

        async def handle(self, message: ACPMessage) -> ProtocolOutcome:
            params = message.params or {}
            return await config.session_set_config_option(
                message.id,
                params,
                st._repository,
                st._config_specs,
                model_resolver=st._model_resolver,
            )

    class _SetModeWrapper:
        method_name = "session/set_mode"

        async def handle(self, message: ACPMessage) -> ProtocolOutcome:
            params = message.params or {}
            return await config.session_set_mode(
                message.id, params, st._repository, st._config_specs
            )

    for wrapper in (
        _InitializeWrapper(),
        _AuthenticateWrapper(),
        _SessionNewWrapper(),
        _SessionLoadWrapper(),
        _SessionListWrapper(),
        _SessionPromptWrapper(),
        _SessionCancelWrapper(),
        _PermissionResponseWrapper(),
        _SetConfigOptionWrapper(),
        _SetModeWrapper(),
    ):
        registry.register(wrapper)
    return registry


def build_protocol(
    *,
    storage: Any | None = None,
    send_callback: Callable[[ACPMessage], Any] | None = None,
    middleware: list[Any] | None = None,
    llm_adapter: Any | None = None,
    orchestrator_provider: Callable[[], Any] | None = None,
    **legacy: Any,
) -> ACPProtocol:
    """Собирает ACPProtocol из реальных компонентов (замена legacy `ACPProtocol()`).

    Принимает те же аргументы, что старый legacy-конструктор
    (`require_auth`, `auth_api_key`, `client_rpc_service`, `tool_registry`,
    `prompt_orchestrator`, `global_policy_manager`, `agent_registry`,
    `strategy_registry`, `command_registry`, `config_option_builder`,
    `model_resolver`, `mcp_http_enabled`, `mcp_sse_enabled`, `runtime_registry`,
    `pending_registry`).
    """
    from codelab.server.protocol.background_executor import BackgroundExecutor
    from codelab.server.protocol.response_router import ResponseRouter

    st = _Assembler(storage=storage, **legacy)
    # прокидываем то, что нужно обёрткам/фоновому исполнителю
    st._send_callback = send_callback
    st._llm_adapter = llm_adapter

    async def _orchestrator_provider() -> Any:
        if orchestrator_provider is not None:
            result = orchestrator_provider()
            if hasattr(result, "__await__"):
                return await result
            return result
        return await st.get_prompt_orchestrator()

    async def _send_message(message: ACPMessage) -> None:
        if send_callback is not None:
            await send_callback(message)

    st._send_message = _send_message

    method_registry = _build_method_registry(st)
    response_router = ResponseRouter(
        storage=st._storage,
        repository=st._repository,
        pending_registry=st._pending_registry,
        client_rpc_service=st._client_rpc_service,
    )
    background_executor = BackgroundExecutor(
        storage=st._storage,
        repository=st._repository,
        orchestrator_provider=_orchestrator_provider,
        mcp_provider=st.ensure_mcp_initialized,
        runtime_registry=st._runtime_registry,
    )

    protocol = ACPProtocol(
        storage=st._storage,
        method_registry=method_registry,
        response_router=response_router,
        background_executor=background_executor,
        pending_registry=st._pending_registry,
        runtime_registry=st._runtime_registry,
        middleware=middleware,
        send_callback=send_callback,
        llm_adapter=llm_adapter,
        orchestrator_provider=_orchestrator_provider,
    )
    # даём тестам доступ к сборщику (для проверок внутреннего состояния)
    protocol._assembler = st  # type: ignore[attr-defined]
    return protocol

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
from typing import Any

from codelab.server.messages import ACPMessage
from codelab.server.protocol.core import ACPProtocol
from codelab.server.protocol.pending_registry import PendingRequestRegistry
from codelab.server.protocol.session_runtime import SessionRuntimeRegistry
from codelab.server.protocol.state import ProtocolOutcome


class _Assembler:
    """Держатель per-connection состояния и ленивых компонентов.

    Командные обёртки читают/пишут состояние здесь (раньше — прямо на
    ACPProtocol). Атрибуты названы как в старом фасаде (`_require_auth`, ...),
    чтобы тела обёрток совпадали с legacy один-в-один.
    """

    _supported_protocol_versions = (1,)

    def __init__(self, **kw: Any) -> None:
        from codelab.server.storage import InMemoryStorage

        self._storage = kw.get("storage") or InMemoryStorage()
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

        from codelab.server.agent.system_prompt_builder import SystemPromptBuilder
        from codelab.server.protocol.handlers.permission_manager import PermissionManager
        from codelab.server.protocol.handlers.pipeline.stages import LLMLoopStage
        from codelab.server.protocol.handlers.plan_builder import PlanBuilder
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
        builder = PromptOrchestratorBuilder(
            tool_registry=self._tool_registry,
            agent_registry=self._agent_registry,
            llm_loop_stage=llm_loop_stage,
            global_policy_manager=self._global_policy_manager,
            client_rpc_service=self._client_rpc_service,
        )
        self._prompt_orchestrator = builder.build()
        return self._prompt_orchestrator


def _build_method_registry(st: _Assembler) -> Any:
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
        method_name = "session/new"

        async def handle(self, message: ACPMessage) -> ProtocolOutcome:
            params = message.params or {}
            response_msg = session.session_new(
                message.id,
                params,
                st._require_auth,
                st._authenticated,
                st._config_specs,
                st._auth_methods,
                st._runtime_capabilities,
                st._command_registry,
            )
            if response_msg.result is not None:
                session_id = response_msg.result.get("sessionId")
                if isinstance(session_id, str):
                    from codelab.server.protocol.session_factory import SessionFactory

                    config_values = {
                        config_id: str(spec["default"])
                        for config_id, spec in st._config_specs.items()
                    }
                    available_commands = (
                        st._command_registry.get_commands_as_dicts()
                        if st._command_registry is not None
                        else []
                    )
                    session_state = SessionFactory.create_session(
                        cwd=params.get("cwd", ""),
                        mcp_servers=params.get("mcpServers", []),
                        config_values=config_values,
                        available_commands=available_commands,
                        runtime_capabilities=st._runtime_capabilities,
                        session_id=session_id,
                    )
                    await st._storage.save_session(session_state)
                    await st.get_mcp_session_manager().setup_if_needed(session_state, params)
            return ProtocolOutcome(response=response_msg)

    class _SessionLoadWrapper:
        method_name = "session/load"

        async def handle(self, message: ACPMessage) -> ProtocolOutcome:
            params = message.params or {}
            return await session.session_load(
                message.id,
                params,
                st._require_auth,
                st._authenticated,
                st._config_specs,
                st._auth_methods,
                st._storage,
            )

    class _SessionListWrapper:
        method_name = "session/list"

        async def handle(self, message: ACPMessage) -> ProtocolOutcome:
            params = message.params or {}
            response = await session.session_list(message.id, params, st._storage, 50)
            return ProtocolOutcome(response=response)

    class _SessionPromptWrapper:
        method_name = "session/prompt"

        async def handle(self, message: ACPMessage) -> ProtocolOutcome:
            params = message.params or {}
            orchestrator = await st.get_prompt_orchestrator()
            session_id = params.get("sessionId")
            if not isinstance(session_id, str):
                return ProtocolOutcome(
                    response=ACPMessage.error_response(
                        message.id, code=-32602,
                        message="Invalid params: sessionId is required",
                    )
                )
            sess = await st._storage.load_session(session_id)
            if sess is None:
                return ProtocolOutcome(
                    response=ACPMessage.error_response(
                        message.id, code=-32001,
                        message=f"Session not found: {session_id}",
                    )
                )
            sess.active_turn = None
            outcome = await orchestrator.handle_prompt(
                request_id=message.id,
                params=params,
                session=sess,
                storage=st._storage,
                mcp_manager=None,
                mcp_prompt_handlers={},
                notification_callback=st._send_message,
            )
            await st._storage.save_session(sess)
            return outcome

    class _SessionCancelWrapper:
        method_name = "session/cancel"

        async def handle(self, message: ACPMessage) -> ProtocolOutcome:
            params = message.params or {}
            orchestrator = await st.get_prompt_orchestrator()
            session_id = params.get("sessionId")
            if not isinstance(session_id, str):
                return ProtocolOutcome(response=None, notifications=[])
            sess = await st._storage.load_session(session_id)
            if sess is None:
                return ProtocolOutcome(
                    response=ACPMessage.response(message.id, None), notifications=[]
                )
            outcome = orchestrator.handle_cancel(
                request_id=message.id, params=params, session=sess
            )
            if st._llm_adapter is not None:
                await st._llm_adapter.cancel_prompt(session_id)
            await st._storage.save_session(sess)

            followup: list[ACPMessage] = list(outcome.followup_responses)
            pending = sess.pending_prompt_response
            if pending is not None:
                followup.append(
                    ACPMessage.response(
                        pending["request_id"], {"stopReason": pending["stop_reason"]}
                    )
                )
                sess.pending_prompt_response = None
                await st._storage.save_session(sess)

            cancel_response = outcome.response or (
                ACPMessage.response(message.id, None) if message.id is not None else None
            )
            return ProtocolOutcome(
                response=cancel_response,
                notifications=outcome.notifications,
                followup_responses=followup,
            )

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
                message.id, params, st._storage, st._config_specs,
                model_resolver=st._model_resolver,
            )

    class _SetModeWrapper:
        method_name = "session/set_mode"

        async def handle(self, message: ACPMessage) -> ProtocolOutcome:
            params = message.params or {}
            return await config.session_set_mode(
                message.id, params, st._storage, st._config_specs
            )

    for wrapper in (
        _InitializeWrapper(), _AuthenticateWrapper(), _SessionNewWrapper(),
        _SessionLoadWrapper(), _SessionListWrapper(), _SessionPromptWrapper(),
        _SessionCancelWrapper(), _PermissionResponseWrapper(),
        _SetConfigOptionWrapper(), _SetModeWrapper(),
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
        pending_registry=st._pending_registry,
        client_rpc_service=st._client_rpc_service,
    )
    background_executor = BackgroundExecutor(
        storage=st._storage,
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

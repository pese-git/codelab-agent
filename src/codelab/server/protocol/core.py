"""Основной класс протокола ACP.

Содержит реализацию класса ACPProtocol — Facade для обработки
ACP-протокола. Делегирует обработку команд CommandHandler-ам,
responses — ResponseRouter, фоновые задачи — BackgroundExecutor.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Protocol

import structlog

from ..messages import ACPMessage
from ..storage import SessionStorage
from .pending_registry import PendingRequestRegistry
from .state import (
    ProtocolOutcome,
)

if TYPE_CHECKING:
    from ..agent.llm_adapter import LLMAdapter
    from ..client_rpc.service import ClientRPCService
    from .handlers.prompt_orchestrator import PromptOrchestrator
    from .session_runtime import SessionRuntimeRegistry

logger = structlog.get_logger()


# Тип обработчика метода: async-функция, принимающая сообщение и возвращающая outcome
MethodHandler = Callable[[ACPMessage], Awaitable[ProtocolOutcome]]


class MiddlewareFn(Protocol):
    """Протокол middleware для сквозной логики (логирование, метрики, auth-check).

    Middleware применяется в порядке onion pattern: первое в списке — внешнее,
    последнее — ближе к обработчику.
    """

    async def __call__(
        self,
        message: ACPMessage,
        next_handler: Callable[[ACPMessage], Awaitable[ProtocolOutcome]],
    ) -> ProtocolOutcome: ...


class ACPProtocol:
    """Facade для ACP-протокола.

    Делегирует обработку команд зарегистрированным CommandHandler-ам,
    responses — ResponseRouter, фоновые задачи — BackgroundExecutor.

    Отвечает только за:
    - Маршрутизацию сообщений через CommandRegistry
    - Применение middleware (Chain of Responsibility)
    - Lifecycle management (cancel, cleanup)

    Пример использования:
        protocol = ACPProtocol(
            method_registry=registry,
            response_router=router,
            background_executor=executor,
        )
        outcome = await protocol.handle(ACPMessage.request("session/list", {}))
    """

    _supported_protocol_versions = (1,)

    def __init__(
        self,
        *,
        storage: SessionStorage | None = None,
        method_registry: Any | None = None,
        response_router: Any | None = None,
        background_executor: Any | None = None,
        pending_registry: PendingRequestRegistry | None = None,
        runtime_registry: SessionRuntimeRegistry | None = None,
        middleware: list[MiddlewareFn] | None = None,
        send_callback: Callable[[ACPMessage], Awaitable[None]] | None = None,
        llm_adapter: LLMAdapter | None = None,
        orchestrator_provider: Callable[[], Awaitable[PromptOrchestrator]] | None = None,
        # Legacy parameters для обратной совместимости
        require_auth: bool = False,
        auth_api_key: str | None = None,
        client_rpc_service: ClientRPCService | None = None,
        tool_registry: Any | None = None,
        prompt_orchestrator: PromptOrchestrator | None = None,
        global_policy_manager: Any | None = None,
        llm_registry: Any | None = None,
        config_option_builder: Any | None = None,
        agent_registry: Any | None = None,
        strategy_registry: Any | None = None,
        command_registry: Any | None = None,
        model_resolver: Any | None = None,
        mcp_http_enabled: bool = True,
        mcp_sse_enabled: bool = True,
    ) -> None:
        """Инициализирует ACPProtocol (Facade).

        Args:
            storage: Хранилище сессий.
            method_registry: Реестр обработчиков команд (Command Pattern).
            response_router: Маршрутизатор ответов от клиента.
            background_executor: Исполнитель фоновых задач.
            pending_registry: Реестр pending permission requests.
            runtime_registry: Реестр runtime-состояний сессий.
            middleware: Список middleware функций для сквозной логики.
            send_callback: Callback для отправки сообщений транспортом.
            llm_adapter: Адаптер LLM для cancellation.
            orchestrator_provider: Функция для получения PromptOrchestrator.
            require_auth: (Legacy) Требуется ли аутентификация.
            auth_api_key: (Legacy) API ключ для аутентификации.
            client_rpc_service: (Legacy) Сервис для agent->client RPC.
            tool_registry: (Legacy) Реестр инструментов.
            prompt_orchestrator: (Legacy) Оркестратор prompt-turn.
            global_policy_manager: (Legacy) Менеджер глобальных политик.
            llm_registry: (Legacy) Реестр LLM провайдеров.
            config_option_builder: (Legacy) Билдер config options.
            agent_registry: (Legacy) Реестр агентов.
            strategy_registry: (Legacy) Реестр стратегий.
            command_registry: (Legacy) Реестр slash-команд.
            model_resolver: (Legacy) Резолвер моделей.
            mcp_http_enabled: (Legacy) Поддерживается ли MCP HTTP transport.
            mcp_sse_enabled: (Legacy) Поддерживается ли MCP SSE transport.
        """
        # Инициализировать хранилище (по умолчанию InMemoryStorage)
        if storage is None:
            from ..storage import InMemoryStorage
            storage = InMemoryStorage()
        self._storage = storage

        self._pending_registry = pending_registry or PendingRequestRegistry()
        self._runtime_registry = runtime_registry
        self._middleware = middleware or []
        self._send_callback = send_callback
        self._llm_adapter = llm_adapter
        self._orchestrator_provider = orchestrator_provider

        # Legacy параметры для обратной совместимости
        self._require_auth = require_auth
        self._auth_api_key = auth_api_key
        self._client_rpc_service = client_rpc_service
        self._tool_registry = tool_registry
        self._prompt_orchestrator = prompt_orchestrator
        self._global_policy_manager = global_policy_manager
        self._llm_registry = llm_registry
        self._config_option_builder = config_option_builder
        self._agent_registry = agent_registry
        self._strategy_registry = strategy_registry
        self._command_registry = command_registry
        self._model_resolver = model_resolver
        self._mcp_http_enabled = mcp_http_enabled
        self._mcp_sse_enabled = mcp_sse_enabled
        self._authenticated = False
        self._auth_methods: list[dict[str, Any]] = [
            {
                "id": "local",
                "name": "Local authentication",
                "description": "Local authentication flow",
                "type": "api_key",
            }
        ]
        self._runtime_capabilities: Any | None = None

        # Создать дефолтные компоненты если не переданы
        if method_registry is None:
            method_registry = self._create_default_method_registry()
        self._method_registry = method_registry

        if response_router is None:
            from .response_router import ResponseRouter
            response_router = ResponseRouter(
                storage=self._storage,
                pending_registry=self._pending_registry,
                client_rpc_service=self._client_rpc_service,
            )
        self._response_router = response_router

        if background_executor is None:
            from .background_executor import BackgroundExecutor
            from .session_runtime import SessionRuntimeRegistry
            # Создаём runtime registry если не передан
            if self._runtime_registry is None:
                self._runtime_registry = SessionRuntimeRegistry()
            background_executor = BackgroundExecutor(
                storage=self._storage,
                orchestrator_provider=self._get_prompt_orchestrator,
                mcp_provider=self._ensure_mcp_initialized_legacy,
                runtime_registry=self._runtime_registry,
            )
        self._background_executor = background_executor

        # Config specs (legacy)
        self._config_specs: dict[str, dict[str, Any]] = self._build_config_specs_legacy()

    @property
    def storage(self) -> SessionStorage:
        """Хранилище сессий (для обратной совместимости)."""
        return self._storage

    @property
    def _handlers(self) -> dict[str, Any]:
        """Legacy dict обработчиков методов (для обратной совместимости)."""
        methods = (
            self._method_registry.list_methods()
            if hasattr(self._method_registry, "list_methods")
            else []
        )
        return {
            method: handler.handle
            for method, handler in [
                (m, self._method_registry.get(m))
                for m in methods
            ]
            if handler is not None
        }

    async def handle(self, message: ACPMessage) -> ProtocolOutcome:
        """Маршрутизирует входящее сообщение по методу через реестр обработчиков.

        Метод является основной точкой входа для HTTP/WS транспорта.
        Использует CommandRegistry для поиска обработчиков (Command Pattern).

        Args:
            message: Входящее JSON-RPC сообщение.

        Returns:
            ProtocolOutcome с результатом обработки.
        """
        # Если method=None, это response (JSON-RPC 2.0)
        if message.method is None:
            logger.debug(
                "response_received_routing_to_handle_client_response",
                request_id=message.id,
            )
            return await self._response_router.handle_client_response(message)

        method = message.method

        # Используем CommandRegistry для поиска обработчика
        command_handler = self._method_registry.get(method)

        if command_handler is None:
            # Уведомления — игнорируем без ошибки
            if message.is_notification:
                return ProtocolOutcome()
            return ProtocolOutcome(
                response=ACPMessage.error_response(
                    message.id, code=-32601, message=f"Method not found: {method}"
                )
            )

        # Применяем middleware в обратном порядке (onion pattern)
        wrapped: Callable[[ACPMessage], Awaitable[ProtocolOutcome]] = command_handler.handle
        for mw in reversed(self._middleware):
            next_handler = wrapped

            async def wrapped_with_middleware(
                msg: ACPMessage,
                _mw: MiddlewareFn = mw,
                _next: Callable[[ACPMessage], Awaitable[ProtocolOutcome]] = next_handler,
            ) -> ProtocolOutcome:
                return await _mw(msg, _next)

            wrapped = wrapped_with_middleware

        return await wrapped(message)

    async def handle_and_process(
        self, message: ACPMessage
    ) -> ProtocolOutcome:
        """Обрабатывает сообщение и запускает фоновые задачи если нужно.

        Расширяет handle() логикой постобработки outcome:
        - Если outcome содержит pending_tool_execution, запускает фоновую задачу
        - Транспорт получает чистый outcome и только отправляет его

        Это основной entry point для транспорта — вместо прямого вызова handle().

        Args:
            message: Входящее ACPMessage.

        Returns:
            ProtocolOutcome для отправки транспортом.
        """
        outcome = await self.handle(message)

        if outcome.pending_tool_execution is not None:
            pending = outcome.pending_tool_execution
            logger.info(
                "scheduling_pending_tool_execution_in_background",
                session_id=pending.session_id,
                tool_call_id=pending.tool_call_id,
            )
            asyncio.create_task(
                self._background_executor.execute_tool_in_background(
                    session_id=pending.session_id,
                    tool_call_id=pending.tool_call_id,
                )
            )

        return outcome

    async def handle_client_response(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает входящий response от клиента (legacy proxy).

        Делегирует ResponseRouter.

        Args:
            message: Входящее JSON-RPC сообщение (response).

        Returns:
            ProtocolOutcome с результатом обработки.
        """
        return await self._response_router.handle_client_response(message)

    async def complete_active_turn(
        self, session_id: str, *, stop_reason: str = "end_turn"
    ) -> ACPMessage | None:
        """Завершает активный prompt-turn и возвращает финальный response.

        Используется транспортом WS для отложенного ответа на `session/prompt`.

        Args:
            session_id: ID сессии.
            stop_reason: Причина остановки.

        Returns:
            ACPMessage с финальным response или None.
        """
        return await self._background_executor.complete_active_turn(
            session_id, stop_reason=stop_reason
        )

    async def should_auto_complete_active_turn(self, session_id: str) -> bool:
        """Возвращает `True`, если active turn можно безопасно автозавершить.

        Если turn ожидает permission-response, автозавершение запрещено.

        Args:
            session_id: ID сессии.

        Returns:
            True если можно автозавершить.
        """
        return await self._background_executor.should_auto_complete_active_turn(session_id)

    async def execute_pending_tool(
        self,
        session_id: str,
        tool_call_id: str,
    ) -> Any:
        """Выполняет pending tool после permission approval и продолжает LLM loop.

        Args:
            session_id: ID сессии.
            tool_call_id: ID tool call для выполнения.

        Returns:
            LLMLoopResult с notifications, stop_reason и pending_permission флагом.
        """
        return await self._background_executor.execute_pending_tool(
            session_id=session_id,
            tool_call_id=tool_call_id,
        )

    async def cancel_active_turns_on_disconnect(self) -> int:
        """Отменяет все активные turn в рамках текущего протокольного инстанса.

        Используется транспортом при разрыве соединения клиента. Метод
        обеспечивает ACP-инвариант остановки in-flight turn и освобождение
        внутренних ожиданий без отправки сетевых сообщений.

        Returns:
            Количество сессий, в которых активный turn был отменен.
        """
        if self._orchestrator_provider is None:
            return 0

        orchestrator = await self._orchestrator_provider()
        cancelled_count = 0
        cursor = None
        while True:
            sessions, cursor = await self._storage.list_sessions(cursor=cursor, limit=100)
            for session_state in sessions:
                if session_state.active_turn is None:
                    continue

                orchestrator.handle_cancel(
                    request_id=None,
                    params={"sessionId": session_state.session_id},
                    session=session_state,
                )
                cancelled_count += 1

                try:
                    await self._storage.save_session(session_state)
                except Exception:
                    continue

            if cursor is None:
                break

        return cancelled_count

    # -----------------------------------------------------------------------
    # Legacy методы для обратной совместимости
    # -----------------------------------------------------------------------

    def _create_default_method_registry(self) -> Any:
        """Создаёт CommandRegistry с legacy обработчиками.

        Используется когда ACPProtocol создаётся напрямую без DI.
        """
        from .commands.base import CommandRegistry
        from .handlers import auth, config, session
        registry = CommandRegistry()

        # Создаём wrapper-ы для legacy handlers
        class _InitializeWrapper:
            method_name = "initialize"

            def __init__(self, protocol: ACPProtocol) -> None:
                self._protocol = protocol

            async def handle(self, message: ACPMessage) -> ProtocolOutcome:
                params = message.params or {}
                response = auth.initialize(
                    message.id,
                    params,
                    self._protocol._supported_protocol_versions,
                    self._protocol._require_auth,
                    self._protocol._auth_methods,
                    mcp_http_enabled=self._protocol._mcp_http_enabled,
                    mcp_sse_enabled=self._protocol._mcp_sse_enabled,
                )
                client_capabilities = params.get("clientCapabilities")
                if isinstance(client_capabilities, dict):
                    self._protocol._runtime_capabilities = auth.parse_client_runtime_capabilities(
                        client_capabilities
                    )
                return ProtocolOutcome(response=response)

        class _AuthenticateWrapper:
            method_name = "authenticate"

            def __init__(self, protocol: ACPProtocol) -> None:
                self._protocol = protocol

            async def handle(self, message: ACPMessage) -> ProtocolOutcome:
                params = message.params or {}
                response, authenticated = auth.authenticate(
                    message.id,
                    params,
                    self._protocol._require_auth,
                    self._protocol._auth_api_key,
                    self._protocol._auth_methods,
                )
                self._protocol._authenticated = authenticated
                return ProtocolOutcome(response=response)

        class _SessionNewWrapper:
            method_name = "session/new"

            def __init__(self, protocol: ACPProtocol) -> None:
                self._protocol = protocol

            async def handle(self, message: ACPMessage) -> ProtocolOutcome:
                params = message.params or {}
                response_msg = session.session_new(
                    message.id,
                    params,
                    self._protocol._require_auth,
                    self._protocol._authenticated,
                    self._protocol._config_specs,
                    self._protocol._auth_methods,
                    self._protocol._runtime_capabilities,
                    self._protocol._command_registry,
                )
                if response_msg.result is not None:
                    session_id = response_msg.result.get("sessionId")
                    if isinstance(session_id, str):
                        from .session_factory import SessionFactory
                        config_values = {
                            config_id: str(spec["default"])
                            for config_id, spec in self._protocol._config_specs.items()
                        }
                        available_commands = (
                            self._protocol._command_registry.get_commands_as_dicts()
                            if self._protocol._command_registry is not None
                            else []
                        )
                        session_state = SessionFactory.create_session(
                            cwd=params.get("cwd", ""),
                            mcp_servers=params.get("mcpServers", []),
                            config_values=config_values,
                            available_commands=available_commands,
                            runtime_capabilities=self._protocol._runtime_capabilities,
                            session_id=session_id,
                        )
                        await self._protocol._storage.save_session(session_state)
                return ProtocolOutcome(response=response_msg)

        class _SessionLoadWrapper:
            method_name = "session/load"

            def __init__(self, protocol: ACPProtocol) -> None:
                self._protocol = protocol

            async def handle(self, message: ACPMessage) -> ProtocolOutcome:
                params = message.params or {}
                return await session.session_load(
                    message.id,
                    params,
                    self._protocol._require_auth,
                    self._protocol._authenticated,
                    self._protocol._config_specs,
                    self._protocol._auth_methods,
                    self._protocol._storage,
                )

        class _SessionListWrapper:
            method_name = "session/list"

            def __init__(self, protocol: ACPProtocol) -> None:
                self._protocol = protocol

            async def handle(self, message: ACPMessage) -> ProtocolOutcome:
                params = message.params or {}
                response = await session.session_list(
                    message.id,
                    params,
                    self._protocol._storage,
                    50,
                )
                return ProtocolOutcome(response=response)

        class _SessionPromptWrapper:
            method_name = "session/prompt"

            def __init__(self, protocol: ACPProtocol) -> None:
                self._protocol = protocol

            async def handle(self, message: ACPMessage) -> ProtocolOutcome:
                params = message.params or {}
                orchestrator = await self._protocol._get_prompt_orchestrator()
                session_id = params.get("sessionId")
                if not isinstance(session_id, str):
                    return ProtocolOutcome(
                        response=ACPMessage.error_response(
                            message.id,
                            code=-32602,
                            message="Invalid params: sessionId is required",
                        )
                    )
                sess = await self._protocol._storage.load_session(session_id)
                if sess is None:
                    return ProtocolOutcome(
                        response=ACPMessage.error_response(
                            message.id,
                            code=-32001,
                            message=f"Session not found: {session_id}",
                        )
                    )
                sess.active_turn = None
                outcome = await orchestrator.handle_prompt(
                    request_id=message.id,
                    params=params,
                    session=sess,
                    storage=self._protocol._storage,
                    mcp_manager=None,
                    mcp_prompt_handlers={},
                    notification_callback=self._protocol._send_message,
                )
                await self._protocol._storage.save_session(sess)
                return outcome

        class _SessionCancelWrapper:
            method_name = "session/cancel"

            def __init__(self, protocol: ACPProtocol) -> None:
                self._protocol = protocol

            async def handle(self, message: ACPMessage) -> ProtocolOutcome:
                params = message.params or {}
                orchestrator = await self._protocol._get_prompt_orchestrator()
                session_id = params.get("sessionId")
                if not isinstance(session_id, str):
                    return ProtocolOutcome(response=None, notifications=[])
                sess = await self._protocol._storage.load_session(session_id)
                if sess is None:
                    return ProtocolOutcome(
                        response=ACPMessage.response(message.id, None),
                        notifications=[],
                    )
                outcome = orchestrator.handle_cancel(
                    request_id=message.id,
                    params=params,
                    session=sess,
                )
                if self._protocol._llm_adapter is not None:
                    await self._protocol._llm_adapter.cancel_prompt(session_id)
                await self._protocol._storage.save_session(sess)
                cancel_response = outcome.response or (
                    ACPMessage.response(message.id, None) if message.id is not None else None
                )
                return ProtocolOutcome(
                    response=cancel_response,
                    notifications=outcome.notifications,
                    followup_responses=list(outcome.followup_responses),
                )

        class _PermissionResponseWrapper:
            method_name = "session/request_permission_response"

            def __init__(self, protocol: ACPProtocol) -> None:
                self._protocol = protocol

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

            def __init__(self, protocol: ACPProtocol) -> None:
                self._protocol = protocol

            async def handle(self, message: ACPMessage) -> ProtocolOutcome:
                params = message.params or {}
                return await config.session_set_config_option(
                    message.id,
                    params,
                    self._protocol._storage,
                    self._protocol._config_specs,
                    model_resolver=self._protocol._model_resolver,
                )

        class _SetModeWrapper:
            method_name = "session/set_mode"

            def __init__(self, protocol: ACPProtocol) -> None:
                self._protocol = protocol

            async def handle(self, message: ACPMessage) -> ProtocolOutcome:
                params = message.params or {}
                return await config.session_set_mode(
                    message.id,
                    params,
                    self._protocol._storage,
                    self._protocol._config_specs,
                )

        registry.register(_InitializeWrapper(self))
        registry.register(_AuthenticateWrapper(self))
        registry.register(_SessionNewWrapper(self))
        registry.register(_SessionLoadWrapper(self))
        registry.register(_SessionListWrapper(self))
        registry.register(_SessionPromptWrapper(self))
        registry.register(_SessionCancelWrapper(self))
        registry.register(_PermissionResponseWrapper(self))
        registry.register(_SetConfigOptionWrapper(self))
        registry.register(_SetModeWrapper(self))

        return registry

    async def _get_prompt_orchestrator(self) -> PromptOrchestrator:
        """Получить PromptOrchestrator (legacy)."""
        if self._prompt_orchestrator is not None:
            return self._prompt_orchestrator

        if self._orchestrator_provider is not None:
            return await self._orchestrator_provider()

        # Создать дефолтный orchestrator
        from ..agent.system_prompt_builder import SystemPromptBuilder
        from .handlers.permission_manager import PermissionManager
        from .handlers.pipeline.stages import LLMLoopStage
        from .handlers.plan_builder import PlanBuilder
        from .handlers.state_manager import StateManager
        from .handlers.tool_call_handler import ToolCallHandler
        from .orchestrator_builder import PromptOrchestratorBuilder

        if self._tool_registry is None:
            from ..tools.registry import SimpleToolRegistry
            self._tool_registry = SimpleToolRegistry()

        # Создаём минимальный LLMLoopStage для legacy режима
        state_manager = StateManager()
        plan_builder = PlanBuilder()
        tool_call_handler = ToolCallHandler()
        permission_manager = PermissionManager()
        system_prompt_builder = SystemPromptBuilder(
            global_prompt="",
            agent_registry=self._agent_registry,
        )

        llm_loop_stage = LLMLoopStage(
            tool_registry=self._tool_registry,
            tool_call_handler=tool_call_handler,
            permission_manager=permission_manager,
            state_manager=state_manager,
            plan_builder=plan_builder,
            system_prompt_builder=system_prompt_builder,
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

    async def _ensure_mcp_initialized_legacy(self, session: Any) -> Any:
        """Legacy MCP initialization (no-op для обратной совместимости)."""
        return None

    async def _send_message(self, message: ACPMessage) -> None:
        """Отправляет сообщение через transport callback."""
        if self._send_callback is not None:
            await self._send_callback(message)

    def _build_config_specs_legacy(self) -> dict[str, dict[str, Any]]:
        """Построить config specs (legacy)."""
        from .config_spec_builder import ConfigSpecBuilder

        builder = ConfigSpecBuilder(
            config_option_builder=self._config_option_builder,
            agent_registry=self._agent_registry,
            strategy_registry=self._strategy_registry,
        )
        return builder.build()

    def _build_active_strategy_config_spec(self) -> dict[str, Any]:
        """Построить config spec для _active_strategy (legacy proxy)."""
        from .config_spec_builder import ConfigSpecBuilder

        builder = ConfigSpecBuilder(
            config_option_builder=self._config_option_builder,
            agent_registry=self._agent_registry,
            strategy_registry=self._strategy_registry,
        )
        return builder._build_strategy_spec()

    def _build_agent_config_spec(self) -> dict[str, Any]:
        """Построить config spec для _agent (legacy proxy)."""
        from .config_spec_builder import ConfigSpecBuilder

        builder = ConfigSpecBuilder(
            config_option_builder=self._config_option_builder,
            agent_registry=self._agent_registry,
            strategy_registry=self._strategy_registry,
        )
        return builder._build_agent_spec()

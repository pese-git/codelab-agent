"""Основной класс протокола ACP.

Содержит реализацию класса ACPProtocol с основной логикой обработки
запросов клиента и управления сессиями.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Protocol

import structlog

from ..mcp import MCPManager, MCPManagerError
from ..mcp.models import MCPServerConfig
from ..mcp.prompt_mapper import mcp_prompts_to_available_commands
from ..messages import ACPMessage, JsonRpcId
from ..storage import SessionStorage
from .handlers import (
    auth,
    config,
    permissions,
    prompt,
    session,
)
from .handlers.slash_commands.builtin.mcp_prompt import MCPPromptCommandHandler
from .pending_registry import PendingRequestRegistry
from .session_factory import SessionFactory
from .session_runtime import SessionRuntimeRegistry
from .state import (
    ClientRuntimeCapabilities,
    LLMLoopResult,
    ProtocolOutcome,
    SessionState,
)

if TYPE_CHECKING:
    from ..agent.llm_adapter import LLMAdapter
    from ..client_rpc.service import ClientRPCService
    from ..llm.registry import LLMProviderRegistry
    from ..llm.resolver import ModelResolver
    from ..tools.base import ToolRegistry
    from .handlers.config_option_builder import ConfigOptionBuilder
    from .handlers.global_policy_manager import GlobalPolicyManager
    from .handlers.prompt_orchestrator import PromptOrchestrator


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
        next_handler: MethodHandler,
    ) -> ProtocolOutcome: ...


logger = structlog.get_logger()


def _get_command_name(cmd: Any) -> str:
    """Извлекает имя команды из dict или AvailableCommand.

    Args:
        cmd: Команда (dict или объект с атрибутом name).

    Returns:
        Имя команды или пустая строка.
    """
    if isinstance(cmd, dict):
        return cmd.get("name", "")
    return getattr(cmd, "name", "")


class ACPProtocol:
    """Диспетчер ACP-методов и in-memory реализация сессионного протокола.

    Класс принимает валидированные JSON-RPC сообщения и возвращает
    `ProtocolOutcome` для транспортного слоя.

    Пример использования:
        protocol = ACPProtocol()
        outcome = protocol.handle(ACPMessage.request("initialize", {}))
    """

    def __init__(
        self,
        *,
        require_auth: bool = False,
        auth_api_key: str | None = None,
        storage: SessionStorage | None = None,
        client_rpc_service: ClientRPCService | None = None,
        tool_registry: ToolRegistry | None = None,
        prompt_orchestrator: PromptOrchestrator | None = None,
        global_policy_manager: GlobalPolicyManager | None = None,
        middleware: list[MiddlewareFn] | None = None,
        send_callback: Callable[[ACPMessage], Awaitable[None]] | None = None,
        llm_registry: LLMProviderRegistry | None = None,
        config_option_builder: ConfigOptionBuilder | None = None,
        runtime_registry: SessionRuntimeRegistry | None = None,
        mcp_http_enabled: bool = True,
        mcp_sse_enabled: bool = True,
        agent_registry: Any | None = None,
        strategy_registry: Any | None = None,
        command_registry: Any | None = None,
        model_resolver: ModelResolver | None = None,
        llm_adapter: LLMAdapter | None = None,
    ) -> None:
        """Инициализирует протокол и хранилище сессий.

        Args:
            require_auth: Требовать аутентификацию перед session setup.
            auth_api_key: API ключ для аутентификации.
            storage: Хранилище сессий (по умолчанию InMemoryStorage).
            client_rpc_service: Сервис ClientRPC для выполнения инструментов (опционально).
            tool_registry: Реестр инструментов для регистрации и выполнения tools (опционально).
            prompt_orchestrator: Оркестратор prompt-turn (опционально, создаётся лениво).
            global_policy_manager: Менеджер глобальных политик разрешений (опционально).
            middleware: Список middleware функций для сквозной логики (опционально).
            send_callback: Callback для отправки сообщений транспортом (опционально).
            llm_registry: Реестр LLM провайдеров для dynamic config options (опционально).
            config_option_builder: Билдер config options из Registry (опционально).
            runtime_registry: Реестр runtime-состояний сессий (опционально).
            mcp_http_enabled: Поддерживается ли MCP HTTP transport (опционально, по умолчанию True).
            mcp_sse_enabled: Поддерживается ли MCP SSE transport (опционально, по умолчанию True).
            agent_registry: Реестр агентов для dynamic _agent config option (опционально).
            strategy_registry: Реестр стратегий для dynamic _active_strategy
                config option (опционально).
            command_registry: Реестр slash-команд для динамической генерации
                available_commands (опционально).
            model_resolver: Резолвер моделей для dynamic model selection (опционально).
            llm_adapter: Адаптер LLM для cancellation и других операций (опционально).
        """

        # Инициализировать хранилище (по умолчанию InMemoryStorage)
        if storage is None:
            from ..storage import InMemoryStorage

            storage = InMemoryStorage()
        self._storage = storage

        # Резолвер моделей для dynamic model selection и cache invalidation
        self._model_resolver = model_resolver

        # LLM адаптер для cancellation и других операций
        self._llm_adapter = llm_adapter

        # Сервис ClientRPC для выполнения встроенных инструментов
        self._client_rpc_service = client_rpc_service

        # Реестр инструментов для регистрации и выполнения tools
        self._tool_registry = tool_registry

        # PromptOrchestrator создаётся один раз, если не передан извне
        self._prompt_orchestrator: PromptOrchestrator | None = prompt_orchestrator

        # GlobalPolicyManager для fallback chain в permission checks
        self._global_policy_manager = global_policy_manager

        # Последние capabilities, согласованные через initialize.
        # Для in-memory demo-сервера это достаточно; по мере роста можно
        # расширить до connection-scoped хранилища.
        self._runtime_capabilities: ClientRuntimeCapabilities | None = None
        # Флаг для сценариев, где агент требует authenticate до session setup.
        self._require_auth = require_auth
        # Локальный API key для production-профиля authenticate (если задан).
        self._auth_api_key = auth_api_key
        # Состояние аутентификации текущего протокольного инстанса.
        self._authenticated = False
        self._auth_methods: list[dict[str, Any]] = [
            {
                "id": "local",
                "name": "Local authentication",
                "description": "Local authentication flow",
                "type": "api_key",
            }
        ]

        # Runtime-реестр futures для permission requests — не персистируется,
        # не входит в SessionState, пересоздаётся при каждом запуске
        self._pending_registry = PendingRequestRegistry()

        # Реестр обработчиков методов — заменяет цепочку if method == "..."
        self._handlers: dict[str, MethodHandler] = {
            "initialize": self._handle_initialize,
            "authenticate": self._handle_authenticate,
            "session/new": self._handle_session_new,
            "session/load": self._handle_session_load,
            "session/list": self._handle_session_list,
            "session/prompt": self._handle_session_prompt,
            "session/cancel": self._handle_session_cancel,
            "session/request_permission_response": self._handle_permission_response_method,
            "session/set_config_option": self._handle_set_config_option,
            "session/set_mode": self._handle_set_mode,
        }

        # Middleware для сквозной логики (логирование, метрики, auth-check)
        self._middleware: list[MiddlewareFn] = middleware or []

        # Callback для отправки сообщений транспортом (используется фоновыми задачами)
        self._send_callback: Callable[[ACPMessage], Awaitable[None]] | None = send_callback

        # LLM Registry и ConfigOptionBuilder для dynamic config options
        self._llm_registry = llm_registry
        self._config_option_builder = config_option_builder

        # Реестр runtime-состояний сессий (REQUEST-scoped)
        self._runtime_registry = runtime_registry or SessionRuntimeRegistry()

        # Agent Registry для dynamic _agent config option
        self._agent_registry = agent_registry

        # Strategy Registry для dynamic _active_strategy config option
        self._strategy_registry = strategy_registry

        # Command Registry для динамической генерации available_commands
        self._command_registry = command_registry

        # MCP transport capabilities — объявляются клиенту при initialize
        self._mcp_http_enabled = mcp_http_enabled
        self._mcp_sse_enabled = mcp_sse_enabled

        # Config specs — строятся динамически из Registry если доступен
        self._config_specs: dict[str, dict[str, Any]] = self._build_config_specs()

    _supported_protocol_versions = (1,)
    _supported_stop_reasons = {
        "end_turn",
        "max_tokens",
        "max_turn_requests",
        "refusal",
        "cancelled",
    }
    _supported_tool_kinds = {
        "read",
        "edit",
        "delete",
        "move",
        "search",
        "execute",
        "think",
        "fetch",
        "switch_mode",
        "other",
    }
    # Размер страницы для `session/list`; cursor указывает смещение в этом срезе.
    _session_list_page_size = 50

    # Default config specs (используются если Registry не доступен)
    _default_config_specs: dict[str, dict[str, Any]] = {
        "mode": {
            "name": "Session Mode",
            "category": "mode",
            "default": "standard",
            "options": [
                {
                    "value": "plan",
                    "name": "Plan",
                    "description": "Read-only planning mode",
                },
                {
                    "value": "standard",
                    "name": "Standard",
                    "description": "Confirm changes before execution",
                },
                {
                    "value": "bypass",
                    "name": "Bypass",
                    "description": "Full autonomy, no confirmation",
                },
            ],
        },
        "model": {
            "name": "Model",
            "category": "model",
            "default": "openai/gpt-4o",
            "options": [
                {
                    "value": "openai/gpt-4o",
                    "name": "GPT-4o",
                    "description": "Balanced speed and quality",
                }
            ],
        },
    }

    def _get_default_model(self) -> str:
        """Получить модель по умолчанию из конфигурации или Registry.

        Returns:
            Модель в формате "provider/model" (например, "openrouter/gpt-4o").
        """
        # Попробовать взять из model_resolver
        if self._model_resolver is not None:
            return f"{self._model_resolver.default_provider}/gpt-4o"

        # Fallback: взять первую модель из Registry
        if self._config_option_builder is not None:
            models = self._config_option_builder.get_model_list()
            if models:
                return models[0].full_id

        # Последний fallback
        return "openai/gpt-4o"

    def _build_config_specs(self) -> dict[str, dict[str, Any]]:
        """Построить config specs из Registry или использовать defaults.

        Включает:
        - mode: ACP standard (permission behavior: ask/code)
        - _agent: custom category (agent selection from Registry)
        - _active_strategy: custom category (strategy selection from StrategyRegistry)
        - model: из config_option_builder

        Returns:
            Dict config_id -> spec
        """
        if self._config_option_builder:
            additional_specs = {
                "mode": self._default_config_specs["mode"],
                "_agent": self._build_agent_config_spec(),
                "_active_strategy": self._build_active_strategy_config_spec(),
            }
            default_model = self._get_default_model()
            return self._config_option_builder.build_config_specs(
                default_model=default_model,
                additional_specs=additional_specs,
            )
        # Fallback без config_option_builder
        specs = dict(self._default_config_specs)
        specs["_agent"] = self._build_agent_config_spec()
        specs["_active_strategy"] = self._build_active_strategy_config_spec()
        return specs

    def _build_active_strategy_config_spec(self) -> dict[str, Any]:
        """Построить config spec для _active_strategy из StrategyRegistry.

        Формирует список доступных стратегий из StrategyRegistry.get_available().
        Включает ТОЛЬКО стратегии, доступные для выполнения (validator возвращает True).

        Returns:
            Config spec для _active_strategy option
        """
        # Metadata для стратегий (display_name, description)
        strategy_metadata = {
            "single": {
                "name": "Single",
                "description": "Single agent execution",
            },
            "multi_orchestrated": {
                "name": "Multi-Orchestrated",
                "description": "Orchestrator + subagents collaboration",
            },
            "multi_choreographed": {
                "name": "Multi-Choreographed",
                "description": "Multiple subagents peer collaboration",
            },
            "hierarchical": {
                "name": "Hierarchical",
                "description": "Primary delegates to subagents",
            },
        }

        # Fallback если StrategyRegistry не доступен
        if not self._strategy_registry or not self._agent_registry:
            return {
                "id": "_active_strategy",
                "name": "Strategy",
                "category": "strategy",
                "type": "select",
                "default": "single",
                "options": [
                    {
                        "value": "single",
                        "name": "Single",
                        "description": "Single agent execution",
                    }
                ],
            }

        # Получить доступные стратегии из Registry
        try:
            available = self._strategy_registry.get_available(self._agent_registry)
        except Exception:
            # Fallback при ошибке
            available = []

        # Если нет доступных стратегий, вернуть только "single"
        if not available:
            return {
                "id": "_active_strategy",
                "name": "Strategy",
                "category": "strategy",
                "type": "select",
                "default": "single",
                "options": [
                    {
                        "value": "single",
                        "name": "Single",
                        "description": "Single agent execution",
                    }
                ],
            }

        # Формировать options из descriptors
        options = []
        for descriptor in available:
            meta = strategy_metadata.get(descriptor.name, {})
            options.append({
                "value": descriptor.name,
                "name": meta.get("name", descriptor.display_name),
                "description": meta.get("description", descriptor.description),
            })

        # Текущая стратегия по умолчанию — первая доступная
        default_strategy = available[0].name if available else "single"

        return {
            "id": "_active_strategy",
            "name": "Strategy",
            "category": "strategy",
            "type": "select",
            "default": default_strategy,
            "options": options,
        }

    def _build_agent_config_spec(self) -> dict[str, Any]:
        """Построить config spec для _agent из AgentRegistry.

        Формирует список primary agents из Registry как options
        для IDE dropdown. Агенты сортируются по priority.

        Returns:
            Config spec для _agent option
        """
        # Fallback если Registry не инициализирован
        if not self._agent_registry:
            return {
                "id": "_agent",
                "name": "Agent",
                "category": "_agent",
                "type": "select",
                "default": "primary",
                "options": [
                    {
                        "value": "primary",
                        "name": "Primary",
                        "description": "Default agent",
                    }
                ],
            }

        # Проверяем инициализацию Registry
        is_initialized = getattr(self._agent_registry, "is_initialized", False)
        if not is_initialized:
            return {
                "id": "_agent",
                "name": "Agent",
                "category": "_agent",
                "type": "select",
                "default": "primary",
                "options": [
                    {
                        "value": "primary",
                        "name": "Primary",
                        "description": "Default agent",
                    }
                ],
            }

        # Получаем primary agents из Registry
        get_primary = getattr(self._agent_registry, "get_primary_agents", None)
        if get_primary is None:
            return {
                "id": "_agent",
                "name": "Agent",
                "category": "_agent",
                "type": "select",
                "default": "primary",
                "options": [
                    {
                        "value": "primary",
                        "name": "Primary",
                        "description": "Default agent",
                    }
                ],
            }

        primary_agents = get_primary()
        if not primary_agents:
            return {
                "id": "_agent",
                "name": "Agent",
                "category": "_agent",
                "type": "select",
                "default": "primary",
                "options": [
                    {
                        "value": "primary",
                        "name": "Primary",
                        "description": "Default agent",
                    }
                ],
            }

        # Сортируем по priority (меньше = выше приоритет)
        sorted_agents = sorted(primary_agents.values(), key=lambda a: a.priority)

        options = []
        for agent in sorted_agents:
            options.append({
                "value": agent.name,
                "name": agent.name.capitalize(),
                "description": f"{agent.model} (priority: {agent.priority})",
            })

        default_agent = sorted_agents[0].name

        return {
            "id": "_agent",
            "name": "Agent",
            "category": "_agent",
            "type": "select",
            "default": default_agent,
            "options": options,
        }

    async def handle(self, message: ACPMessage) -> ProtocolOutcome:
        """Маршрутизирует входящее сообщение по методу через реестр обработчиков.

        Метод является основной точкой входа для HTTP/WS транспорта.

        Пример использования:
            outcome = protocol.handle(ACPMessage.request("session/list", {}))
        """
        # Если method=None, это response (JSON-RPC 2.0)
        # Маршрутизируем на handle_client_response() вместо отклонения.
        if message.method is None:
            logger.debug(
                "response received, routing to handle_client_response",
                request_id=message.id,
            )
            return await self.handle_client_response(message)

        method = message.method
        handler = self._handlers.get(method)

        if handler is None:
            # Уведомления — игнорируем без ошибки
            if message.is_notification:
                return ProtocolOutcome()
            return ProtocolOutcome(
                response=ACPMessage.error_response(
                    message.id, code=-32601, message=f"Method not found: {method}"
                )
            )

        # Применить middleware в обратном порядке (onion pattern)
        wrapped: MethodHandler = handler
        for mw in reversed(self._middleware):
            # Создаём замыкание для корректного захвата переменных
            next_handler = wrapped

            async def wrapped_with_middleware(
                msg: ACPMessage,
                _mw=mw,
                _next=next_handler,
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
                "scheduling pending tool execution in background",
                session_id=pending.session_id,
                tool_call_id=pending.tool_call_id,
            )
            asyncio.create_task(
                self._execute_tool_in_background(
                    session_id=pending.session_id,
                    tool_call_id=pending.tool_call_id,
                )
            )

        return outcome

    async def _execute_tool_in_background(
        self,
        *,
        session_id: str,
        tool_call_id: str,
    ) -> None:
        """Фоновая задача для выполнения tool после permission approval.

        Выполняет инструмент через LLMLoopStage, отправляет notifications
        и завершает turn. Вызывается из handle_and_process().
        """
        try:
            llm_result: LLMLoopResult = await self.execute_pending_tool(
                session_id=session_id,
                tool_call_id=tool_call_id,
            )

            # Отправляем все accumulated notifications
            logger.info(
                "sending notifications after permission approval",
                session_id=session_id,
                tool_call_id=tool_call_id,
                notifications_count=len(llm_result.notifications),
            )
            for notification in llm_result.notifications:
                await self._send_message(notification)

            # Сессия уже сохранена в execute_pending_tool() —
            # там save_session вызывается после orchestrator.execute_pending_tool(),
            # поэтому здесь в in-memory session актуальный permission_request_id.

            # Если LLM loop снова ожидает permission — просто выходим
            if llm_result.pending_permission:
                logger.debug(
                    "llm loop deferred for permission",
                    session_id=session_id,
                )
                return

            # Завершаем turn и отправляем финальный response
            stop_reason = llm_result.stop_reason or "end_turn"
            turn_completion = await self.complete_active_turn(
                session_id, stop_reason=stop_reason
            )
            if turn_completion is not None:
                await self._send_message(turn_completion)
                logger.debug(
                    "turn completion sent after llm loop",
                    session_id=session_id,
                    stop_reason=stop_reason,
                )
        except Exception as exc:
            logger.error(
                "background tool execution failed",
                session_id=session_id,
                tool_call_id=tool_call_id,
                error=str(exc),
                exc_info=True,
            )

    async def _send_message(self, message: ACPMessage) -> None:
        """Отправляет сообщение через transport callback.

        Используется для отправки notifications и turn completion
        из фоновых задач (например, _execute_tool_in_background).
        """
        if self._send_callback is not None:
            await self._send_callback(message)
        else:
            logger.warning(
                "no send callback configured, message not sent",
                method=message.method,
            )

    async def complete_active_turn(
        self, session_id: str, *, stop_reason: str = "end_turn"
    ) -> ACPMessage | None:
        """Завершает активный prompt-turn и возвращает финальный response.

        Используется транспортом WS для отложенного ответа на `session/prompt`.

        Пример использования:
            response = await protocol.complete_active_turn("sess_1", stop_reason="end_turn")
        """
        session = await self._storage.load_session(session_id)
        if session is None:
            return None
        return prompt.complete_active_turn(
            session,
            stop_reason=stop_reason,
        )

    async def should_auto_complete_active_turn(self, session_id: str) -> bool:
        """Возвращает `True`, если active turn можно безопасно автозавершить.

        Если turn ожидает permission-response, автозавершение запрещено.

        Пример использования:
            if await protocol.should_auto_complete_active_turn("sess_1"):
                ...
        """
        session = await self._storage.load_session(session_id)
        if session is None or session.active_turn is None:
            return False
        return prompt.should_auto_complete_active_turn(session)

    async def handle_client_response(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает входящий response от клиента для server-originated requests.

        Сейчас используется для `session/request_permission`, отправленного ранее
        в рамках active prompt-turn.

        Пример использования:
            outcome = await protocol.handle_client_response(client_response)
        """

        if message.id is None:
            logger.debug("handle_client_response: ignoring message with no id")
            return ProtocolOutcome()

        logger.debug(
            "handle_client_response: routing response",
            request_id=message.id,
            has_result=message.result is not None,
        )

        resolved_client_rpc = await self._resolve_pending_client_rpc_response(
            request_id=message.id,
            result=message.result,
            error=message.error.model_dump(exclude_none=True)
            if message.error is not None
            else None,
        )
        if resolved_client_rpc is not None:
            logger.debug(
                "handle_client_response: resolved as pending client RPC",
                request_id=message.id,
            )
            return resolved_client_rpc

        if self._client_rpc_service is not None and self._client_rpc_service.has_pending_request(
            message.id
        ):
            # Пробрасываем response в ClientRPCService для async-ожиданий,
            # используемых tool executors (filesystem/terminal).
            logger.debug(
                "forwarding client response to client_rpc_service",
                request_id=message.id,
                has_error=message.error is not None,
            )
            self._client_rpc_service.handle_response(message.to_dict())
            return ProtocolOutcome()

        if await permissions.consume_cancelled_client_rpc_response(message.id, self._storage):
            # Late response на отмененный agent->client RPC считаем no-op.
            logger.debug(
                "handle_client_response: consumed cancelled client RPC response",
                request_id=message.id,
            )
            return ProtocolOutcome()

        if await permissions.consume_cancelled_permission_response(message.id, self._storage):
            # Late response на уже отмененный permission-request считаем
            # корректно обработанным no-op, чтобы избежать race-эффектов.
            logger.debug(
                "handle_client_response: consumed cancelled permission response",
                request_id=message.id,
            )
            return ProtocolOutcome()

        logger.debug(
            "handle_client_response: attempting to resolve permission response",
            request_id=message.id,
        )
        resolved = await self._resolve_permission_response(message.id, message.result)
        if resolved is None:
            logger.debug(
                "handle_client_response: _resolve_permission_response returned None",
                request_id=message.id,
            )
            return ProtocolOutcome()
        logger.debug(
            "handle_client_response: permission response resolved successfully",
            request_id=message.id,
        )
        return resolved

    async def _resolve_pending_client_rpc_response(
        self,
        *,
        request_id: JsonRpcId,
        result: Any,
        error: dict[str, Any] | None,
    ) -> ProtocolOutcome | None:
        """Обрабатывает response на ожидаемый agent->client fs/* request.

        Пример использования:
            outcome = await protocol._resolve_pending_client_rpc_response(
                request_id="req_1",
                result={"content": "ok"},
                error=None,
            )
        """

        session = await prompt.find_session_by_pending_client_request_id(request_id, self._storage)
        if session is None:
            return None

        return prompt.resolve_pending_client_rpc_response_impl(
            session=session,
            request_id=request_id,
            result=result,
            error=error,
        )

    async def _resolve_permission_response(
        self,
        permission_request_id: JsonRpcId,
        result: Any,
    ) -> ProtocolOutcome | None:
        """Применяет решение по permission-request к активному prompt-turn.

        Пример использования:
            outcome = await protocol._resolve_permission_response(
                "perm_1",
                {"outcome": {"outcome": "selected", "optionId": "allow_once"}},
            )
        """

        logger.debug(
            "_resolve_permission_response: searching for session",
            permission_request_id=permission_request_id,
        )
        session = await permissions.find_session_by_permission_request_id(
            permission_request_id, self._storage
        )
        if session is None:
            logger.debug(
                "_resolve_permission_response: session not found for permission_request_id",
                permission_request_id=permission_request_id,
            )
            return None

        logger.debug(
            "_resolve_permission_response: session found, resolving",
            permission_request_id=permission_request_id,
            session_id=session.session_id,
            active_turn_exists=session.active_turn is not None,
            active_turn_perm_request_id=(
                session.active_turn.permission_request_id if session.active_turn else None
            ),
            active_turn_perm_tool_call_id=(
                session.active_turn.permission_tool_call_id if session.active_turn else None
            ),
        )
        return prompt.resolve_permission_response_impl(
            session=session,
            permission_request_id=permission_request_id,
            result=result,
        )

    async def _get_session_for_runtime(self, session_id: str) -> SessionState | None:
        """Возвращает сессию из storage по id.

        Пример использования:
            session = await protocol._get_session_for_runtime("sess_1")
        """
        return await self._storage.load_session(session_id)

    async def cancel_active_turns_on_disconnect(self) -> int:
        """Отменяет все активные turn в рамках текущего протокольного инстанса.

        Используется транспортом при разрыве соединения клиента. Метод
        обеспечивает ACP-инвариант остановки in-flight turn и освобождение
        внутренних ожиданий без отправки сетевых сообщений.

        Returns:
            Количество сессий, в которых активный turn был отменен.
        """
        cancelled_count = 0
        cursor = None
        while True:
            sessions, cursor = await self._storage.list_sessions(cursor=cursor, limit=100)
            for session_state in sessions:
                if session_state.active_turn is None:
                    continue

                orchestrator = await self._get_prompt_orchestrator()
                orchestrator.handle_cancel(
                    request_id=None,
                    params={"sessionId": session_state.session_id},
                    session=session_state,
                )
                cancelled_count += 1

                try:
                    await self._storage.save_session(session_state)
                except Exception:
                    # Ошибка персистентности не должна блокировать cleanup при disconnect.
                    continue

            if cursor is None:
                break

        return cancelled_count

    async def _get_prompt_orchestrator(self) -> PromptOrchestrator:
        """Получить PromptOrchestrator.

        Если передан явно в конструктор — использует его.
        Если нет — создаёт лениво при первом обращении.
        Если tool_registry не настроен, создаёт SimpleToolRegistry по умолчанию.

        Returns:
            PromptOrchestrator (всегда не None).
        """
        if self._prompt_orchestrator is not None:
            return self._prompt_orchestrator

        from ..tools.registry import SimpleToolRegistry
        from .handlers.client_rpc_handler import ClientRPCHandler

        if self._tool_registry is None:
            self._tool_registry = SimpleToolRegistry()
        from codelab.server.agent.system_prompt_builder import SystemPromptBuilder

        from .handlers.permission_manager import PermissionManager
        from .handlers.pipeline import (
            PlanBuildingStage,
            PromptPipeline,
            SlashCommandStage,
            TurnLifecycleStage,
            ValidationStage,
        )
        from .handlers.pipeline.stages import LLMLoopStage
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

        state_manager = StateManager()
        plan_builder = PlanBuilder()
        turn_lifecycle_manager = TurnLifecycleManager()
        tool_call_handler = ToolCallHandler()
        permission_manager = PermissionManager()
        client_rpc_handler = ClientRPCHandler()
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

        command_registry = CommandRegistry()
        slash_router = SlashCommandRouter(command_registry)
        command_registry.register(StatusCommandHandler())
        command_registry.register(ModeCommandHandler())
        command_registry.register(HelpCommandHandler(command_registry))

        pipeline = PromptPipeline(stages=[
            ValidationStage(state_manager),
            SlashCommandStage(slash_router),
            PlanBuildingStage(plan_builder),
            TurnLifecycleStage(turn_lifecycle_manager, action="open"),
            DirectivesStage(self._tool_registry, permission_manager),
            llm_loop_stage,
            TurnLifecycleStage(turn_lifecycle_manager, action="close"),
        ])

        self._prompt_orchestrator = PromptOrchestrator(
            state_manager=state_manager,
            plan_builder=plan_builder,
            turn_lifecycle_manager=turn_lifecycle_manager,
            tool_call_handler=tool_call_handler,
            permission_manager=permission_manager,
            client_rpc_handler=client_rpc_handler,
            tool_registry=self._tool_registry,
            llm_loop_stage=llm_loop_stage,
            client_rpc_service=self._client_rpc_service,
            global_policy_manager=self._global_policy_manager,
            command_registry=command_registry,
            pipeline=pipeline,
        )
        return self._prompt_orchestrator

    # -----------------------------------------------------------------------
    # Обработчики методов протокола (реестр _handlers)
    # -----------------------------------------------------------------------

    async def _handle_initialize(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает метод initialize."""
        params = message.params or {}
        response = auth.initialize(
            message.id,
            params,
            self._supported_protocol_versions,
            self._require_auth,
            self._auth_methods,
            mcp_http_enabled=self._mcp_http_enabled,
            mcp_sse_enabled=self._mcp_sse_enabled,
        )
        # Сохраняем согласованные runtime-возможности клиента для feature-gate.
        client_capabilities = params.get("clientCapabilities")
        if isinstance(client_capabilities, dict):
            self._runtime_capabilities = auth.parse_client_runtime_capabilities(
                client_capabilities
            )

        # Инициализируем GlobalPolicyManager для fallback chain
        if self._global_policy_manager is None:
            logger.debug("GlobalPolicyManager will be initialized on demand")

        return ProtocolOutcome(response=response)

    async def _handle_authenticate(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает метод authenticate."""
        params = message.params or {}
        response, authenticated = auth.authenticate(
            message.id,
            params,
            self._require_auth,
            self._auth_api_key,
            self._auth_methods,
        )
        self._authenticated = authenticated
        return ProtocolOutcome(response=response)

    async def _handle_session_new(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает метод session/new."""
        params = message.params or {}
        response_msg = session.session_new(
            message.id,
            params,
            self._require_auth,
            self._authenticated,
            self._config_specs,
            self._auth_methods,
            self._runtime_capabilities,
            self._command_registry,
        )

        # Если создание прошло успешно, сохраняем в storage и кэш
        if response_msg.result is not None:
            session_id = response_msg.result.get("sessionId")
            if isinstance(session_id, str):
                config_values = {
                    config_id: str(spec["default"])
                    for config_id, spec in self._config_specs.items()
                }
                # Динамическая генерация available_commands из CommandRegistry
                available_commands = (
                    self._command_registry.get_commands_as_dicts()
                    if self._command_registry is not None
                    else []
                )
                session_state = SessionFactory.create_session(
                    cwd=params.get("cwd", ""),
                    mcp_servers=params.get("mcpServers", []),
                    config_values=config_values,
                    available_commands=available_commands,
                    runtime_capabilities=self._runtime_capabilities,
                    session_id=session_id,
                )

                # Единая точка инициализации MCP серверов
                await self._setup_mcp_if_needed(session_state, params)

                await self._storage.save_session(session_state)

        return ProtocolOutcome(response=response_msg)

    async def _handle_session_load(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает метод session/load."""
        params = message.params or {}
        session_id = params.get("sessionId")
        if isinstance(session_id, str):
            session_obj = await self._get_session_for_runtime(session_id)
            if session_obj is not None:
                session_obj.runtime_capabilities = self._runtime_capabilities

                # Единая точка инициализации MCP серверов
                await self._setup_mcp_if_needed(session_obj, params)

                # Обработка orphaned permission requests после перезапуска сервера.
                if session_obj.active_turn and session_obj.active_turn.permission_request_id:
                    perm_req_id = session_obj.active_turn.permission_request_id
                    if not self._pending_registry.has(perm_req_id):
                        logger.warning(
                            "session_loaded_with_orphaned_permission_request",
                            session_id=session_id,
                            permission_request_id=perm_req_id,
                        )
                        session_obj.active_turn = None
                        await self._storage.save_session(session_obj)

        return await session.session_load(
            message.id,
            params,
            self._require_auth,
            self._authenticated,
            self._config_specs,
            self._auth_methods,
            self._storage,
        )

    async def _handle_session_list(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает метод session/list."""
        params = message.params or {}
        response = await session.session_list(
            message.id,
            params,
            self._storage,
            self._session_list_page_size,
        )
        return ProtocolOutcome(response=response)

    async def _handle_session_prompt(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает метод session/prompt."""
        params = message.params or {}

        orchestrator = await self._get_prompt_orchestrator()
        session_id = params.get("sessionId")
        if not isinstance(session_id, str):
            return ProtocolOutcome(
                response=ACPMessage.error_response(
                    message.id,
                    code=-32602,
                    message="Invalid params: sessionId is required",
                )
            )

        session = await self._storage.load_session(session_id)
        if session is None:
            return ProtocolOutcome(
                response=ACPMessage.error_response(
                    message.id,
                    code=-32001,
                    message=f"Session not found: {session_id}",
                )
            )

        # Очищаем stale active_turn от предыдущего незавершённого turn.
        # Если turn был deferred (ожидает permission/client RPC), а соединение
        # разорвалось или сервер перезапустился — active_turn остаётся в storage
        # и блокирует новые запросы. Новый turn создаст свой active_turn.
        session.active_turn = None

        # Получить MCP manager из registry с defensive re-initialization
        mcp_manager = await self._ensure_mcp_initialized(session)

        # Получить MCP prompt handlers из runtime registry
        runtime = await self._runtime_registry.get(session_id)
        mcp_prompt_handlers = runtime.mcp_prompt_handlers if runtime else {}

        outcome = await orchestrator.handle_prompt(
            request_id=message.id,
            params=params,
            session=session,
            storage=self._storage,
            mcp_manager=mcp_manager,
            mcp_prompt_handlers=mcp_prompt_handlers,
        )

        # Сохраняем сессию (критично для permission flow)
        try:
            await self._storage.save_session(session)
            logger.debug(
                "session saved after prompt",
                session_id=session_id,
                active_turn_exists=session.active_turn is not None,
                active_turn_perm_request_id=(
                    session.active_turn.permission_request_id if session.active_turn else None
                ),
            )
        except Exception as e:
            logger.error(
                "failed_to_save_session_after_prompt",
                session_id=session_id,
                error=str(e),
            )

        return outcome

    async def _handle_session_cancel(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает метод session/cancel."""
        params = message.params or {}

        orchestrator = await self._get_prompt_orchestrator()
        session_id = params.get("sessionId")
        logger.info("session_cancel_received", session_id=session_id, request_id=message.id)
        if not isinstance(session_id, str):
            logger.warning("session_cancel_missing_session_id", params=params)
            return ProtocolOutcome(response=None, notifications=[])

        session = await self._storage.load_session(session_id)
        if session is None:
            return ProtocolOutcome(
                response=ACPMessage.response(message.id, None),
                notifications=[],
            )

        outcome = orchestrator.handle_cancel(
            request_id=message.id,
            params=params,
            session=session,
        )
        logger.info(
            "session_cancel_handled",
            session_id=session_id,
            notifications_count=len(outcome.notifications),
            followup_count=len(outcome.followup_responses),
        )

        # Прервать активный LLM-запрос для этой сессии.
        # handle_cancel помечает флаг и закрывает turn, но asyncio.Task с LLM
        # продолжает работать до ответа модели — нужно явно его отменить.
        if self._llm_adapter is not None:
            await self._llm_adapter.cancel_prompt(session_id)
            logger.info("agent_llm_task_cancelled", session_id=session_id)

        await self._storage.save_session(session)

        # Если cancel завершил deferred turn, отправляем followup response на prompt request
        followup: list[ACPMessage] = list(outcome.followup_responses)
        pending = session.pending_prompt_response
        if pending is not None:
            followup.append(
                ACPMessage.response(
                    pending["request_id"],
                    {"stopReason": pending["stop_reason"]},
                )
            )
            session.pending_prompt_response = None
            await self._storage.save_session(session)

        # Для notification (id=None) не отправляем response
        cancel_response = outcome.response or (
            ACPMessage.response(message.id, None) if message.id is not None else None
        )

        return ProtocolOutcome(
            response=cancel_response,
            notifications=outcome.notifications,
            followup_responses=followup,
        )

    async def _handle_permission_response_method(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает метод session/request_permission_response."""
        if message.id is None:
            return ProtocolOutcome(response=ACPMessage.error_response(
                None, code=-32600, message="Invalid Request: id is required"
            ))
        params = message.params or {}
        return await self._handle_permission_response(
            message.id,
            params,
        )

    async def _handle_set_config_option(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает метод session/set_config_option."""
        params = message.params or {}
        return await config.session_set_config_option(
            message.id,
            params,
            self._storage,
            self._config_specs,
            model_resolver=self._model_resolver,
        )

    async def _handle_set_mode(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает метод session/set_mode."""
        params = message.params or {}
        return await config.session_set_mode(
            message.id,
            params,
            self._storage,
            self._config_specs,
        )

    # -----------------------------------------------------------------------
    # Вспомогательные методы
    # -----------------------------------------------------------------------

    async def _ensure_mcp_initialized(
        self,
        session: SessionState,
    ) -> MCPManager | None:
        """Убеждается что MCP серверы инициализированы для сессии.

        Defensive check: если сессия имеет mcp_servers в state, но mcp_manager
        отсутствует в runtime registry (например, после WebSocket reconnect),
        автоматически переинициализирует MCP серверы.

        Также восстанавливает mcp_prompt_handlers если они потеряны
        (handlers хранятся в runtime registry, не в SessionState).

        Согласно ACP протоколу, клиент ДОЛЖЕН вызывать session/load после
        reconnect для восстановления MCP соединений. Этот метод обеспечивает
        graceful degradation если клиент нарушает протокол.

        Args:
            session: Состояние сессии с mcp_servers.

        Returns:
            MCPManager если инициализирован, иначе None.
        """
        runtime = await self._runtime_registry.get(session.session_id)
        if runtime and runtime.mcp_manager is not None:
            # Восстанавливаем handlers если они потеряны (runtime существует, но handlers пусты)
            if not runtime.mcp_prompt_handlers and session.mcp_servers:
                await self._restore_mcp_prompts(session, runtime.mcp_manager)
            return runtime.mcp_manager

        # MCP manager отсутствует, но есть конфигурация — переинициализировать
        if session.mcp_servers:
            logger.warning(
                "mcp_servers_configured_but_not_initialized",
                session_id=session.session_id,
                mcp_server_count=len(session.mcp_servers),
                hint="Client should call session/load after WebSocket reconnect",
            )
            await self._initialize_mcp_servers(session, session.mcp_servers)

            # Получить обновлённый mcp_manager
            runtime = await self._runtime_registry.get(session.session_id)
            if runtime:
                return runtime.mcp_manager

        return None

    async def _restore_mcp_prompts(
        self,
        session: SessionState,
        mcp_manager: MCPManager,
    ) -> None:
        """Восстанавливает mcp_prompt_handlers в runtime registry.

        Вызывается когда mcp_manager уже есть в runtime registry,
        но runtime.mcp_prompt_handlers пуст (handlers не сохраняются
        между restart сервера).

        Оптимизация: вызывает get_all_prompts() один раз для всех серверов,
        а не для каждого отдельно.

        Args:
            session: Состояние сессии для получения mcp_servers.
            mcp_manager: Существующий MCPManager из runtime registry.
        """
        runtime = await self._runtime_registry.get(session.session_id)
        if runtime is None:
            logger.warning(
                "cannot restore mcp prompts: runtime not found",
                session_id=session.session_id,
            )
            return

        # Очищаем старые MCP prompts из available_commands (оставляем built-in)
        builtin_names = {"status", "mode", "help"}
        session.available_commands = [
            cmd for cmd in session.available_commands
            if _get_command_name(cmd) in builtin_names
        ]
        runtime.mcp_prompt_handlers.clear()
        session.mcp_prompt_handlers.clear()

        # Получаем prompts от всех серверов ОДИН раз
        try:
            all_prompts = await mcp_manager.get_all_prompts()
        except Exception as e:
            logger.warning(
                "failed to get prompts during restore",
                session_id=session.session_id,
                error=str(e),
            )
            return

        # Регистрируем prompts для каждого сервера
        for server_config in session.mcp_servers:
            if not isinstance(server_config, dict):
                continue
            server_name = server_config.get("name")
            if not server_name:
                continue

            server_prompts = all_prompts.get(server_name, [])
            if not server_prompts:
                continue

            # Регистрируем prompts из списка (без повторного вызова get_all_prompts)
            self._register_mcp_prompts_from_list(
                session, mcp_manager, server_name, server_prompts
            )

        # Копируем handlers из session в runtime (основное хранилище)
        runtime.mcp_prompt_handlers.update(session.mcp_prompt_handlers)
        session.mcp_prompt_handlers.clear()

        logger.info(
            "restored mcp prompt handlers",
            session_id=session.session_id,
            handlers_count=len(runtime.mcp_prompt_handlers),
        )

    async def _send_available_commands_update(
        self,
        session_state: SessionState,
        mcp_manager: MCPManager,
    ) -> None:
        """Формирует и отправляет available_commands_update клиенту.

        Объединяет native tools, MCP tools и slash commands из session_state
        в единый список и отправляет notification клиенту.

        Args:
            session_state: Состояние сессии для получения slash commands.
            mcp_manager: MCP менеджер для получения tools.

        Note:
            Используется при изменении MCP tools или prompts для уведомления
            клиента об изменении списка доступных команд.
            Соответствует ACP спецификации: session/update с
            sessionUpdate="available_commands_update".
        """
        try:
            # Собираем все инструменты
            mcp_tools = mcp_manager.get_all_tools()
            native_tools = self._tool_registry.get_available_tools("")
            all_tools = native_tools + mcp_tools

            # Формируем availableCommands
            available_commands: list[dict[str, Any]] = [
                {"name": tool.name, "description": tool.description or ""}
                for tool in all_tools
            ]

            # Добавляем slash-команды из session_state
            for cmd in session_state.available_commands:
                if isinstance(cmd, dict):
                    available_commands.append(cmd)
                elif hasattr(cmd, "model_dump"):
                    available_commands.append(cmd.model_dump(exclude_none=True))
                else:
                    available_commands.append(cmd)

            # Отправляем notification
            notification = ACPMessage.notification(
                "session/update",
                {
                    "sessionId": session_state.session_id,
                    "update": {
                        "sessionUpdate": "available_commands_update",
                        "availableCommands": available_commands,
                    },
                },
            )
            await self._send_message(notification)

            logger.info(
                "sent available_commands_update",
                session_id=session_state.session_id,
                tools_count=len(all_tools),
                slash_commands_count=len(session_state.available_commands),
            )
        except Exception as e:
            logger.error(
                "failed to send available_commands_update",
                session_id=session_state.session_id,
                error=str(e),
            )

    async def _setup_mcp_if_needed(
        self,
        session_state: SessionState,
        params: dict[str, Any],
    ) -> None:
        """Единая точка инициализации MCP серверов — не дублируется.

        Вызывается из session/new и session/load.
        """
        mcp_servers = params.get("mcpServers", [])
        if not mcp_servers or not isinstance(mcp_servers, list):
            return

        # Проверить есть ли уже MCP в registry
        runtime = await self._runtime_registry.get(session_state.session_id)
        if runtime and runtime.mcp_manager is not None:
            return  # Уже инициализирован

        await self._initialize_mcp_servers(session_state, mcp_servers)

    async def _handle_permission_response(
        self,
        request_id: JsonRpcId,
        params: dict[str, Any],
    ) -> ProtocolOutcome:
        """Обрабатывает response на session/request_permission от клиента.
        
        Логика:
        1. Найти сессию с активным permission request
        2. Проверить, не был ли request отменен (late response handling)
        3. Извлечь решение из response
        4. Обновить policy если нужно (для allow_always/reject_always)
        5. Обновить tool call status и отправить notifications
        
        Args:
            request_id: ID permission request
            params: Параметры (sessionId, result с outcome и optionId)
        
        Returns:
            ProtocolOutcome с response и notifications
        """
        session_id = params.get("sessionId", "")
        
        # Найти сессию по permission request ID через storage
        session = await permissions.find_session_by_permission_request_id(
            request_id, self._storage
        )

        if session is None:
            # Проверить, был ли request отменен (late response handling)
            cancelled_session = await permissions.find_session_with_cancelled_permission(
                request_id, self._storage
            )
            if cancelled_session is not None:
                logger.debug(
                    "ignoring late response on cancelled permission request",
                    request_id=request_id,
                    session_id=cancelled_session.session_id,
                )
                # Удалить из tombstone
                cancelled_session.cancelled_permission_requests.discard(request_id)
                await self._storage.save_session(cancelled_session)
                return ProtocolOutcome(response=ACPMessage.response(request_id, {}))

            # Неизвестный request
            logger.warning(
                "permission response for unknown request",
                request_id=request_id,
            )
            return ProtocolOutcome(
                response=ACPMessage.error_response(
                    request_id,
                    code=-32603,
                    message="Unknown permission request",
                )
            )

        # Получить PermissionManager из handlers (инициализируется в prompt.py)
        from .handlers.permission_manager import PermissionManager

        # Создать временный PermissionManager для извлечения данных
        permission_manager = PermissionManager()

        result = params.get("result", {})
        
        # Извлечь решение из response
        outcome = permission_manager.extract_permission_outcome(result)
        option_id = permission_manager.extract_permission_option_id(result)

        if outcome != "selected" or option_id is None:
            logger.warning(
                "invalid permission response format",
                request_id=request_id,
                session_id=session_id,
                outcome=outcome,
            )
            return ProtocolOutcome(
                response=ACPMessage.error_response(
                    request_id,
                    code=-32603,
                    message="Invalid permission response",
                )
            )

        # Получить tool_call_id из active_turn
        if session.active_turn is None or session.active_turn.permission_tool_call_id is None:
            logger.warning(
                "no permission tool call in active turn",
                request_id=request_id,
                session_id=session_id,
            )
            return ProtocolOutcome(
                response=ACPMessage.error_response(
                    request_id,
                    code=-32603,
                    message="No pending tool call",
                )
            )

        tool_call_id = session.active_turn.permission_tool_call_id

        # Сохранить policy если нужно (для allow_always/reject_always)
        acceptance_updates = permission_manager.build_permission_acceptance_updates(
            session,
            session_id,
            tool_call_id,
            option_id,
        )

        logger.debug(
            "permission response handled",
            request_id=request_id,
            session_id=session_id,
            option_id=option_id,
            tool_call_id=tool_call_id,
        )

        return ProtocolOutcome(
            response=ACPMessage.response(request_id, {}),
            notifications=acceptance_updates,
        )

    async def execute_pending_tool(
        self,
        session_id: str,
        tool_call_id: str,
    ) -> LLMLoopResult:
        """Выполняет pending tool после permission approval и продолжает LLM loop.
        
        Вызывается из http_server.py после того как permission был одобрен.
        Создаёт PromptOrchestrator и делегирует ему выполнение.
        Согласно ACP протоколу (05-Prompt Turn.md, Step 6), после выполнения
        инструмента результат передаётся LLM для продолжения диалога.
        
        Args:
            session_id: ID сессии
            tool_call_id: ID tool call для выполнения
            
        Returns:
            LLMLoopResult с notifications, stop_reason и pending_permission флагом
        """
        session = await self._storage.load_session(session_id)
        if session is None:
            logger.error(
                "session not found for pending tool execution",
                session_id=session_id,
                tool_call_id=tool_call_id,
            )
            return LLMLoopResult(notifications=[], stop_reason="end_turn")
        
        # Получить MCP manager из runtime registry с defensive re-initialization
        mcp_manager = await self._ensure_mcp_initialized(session)

        # Получить или создать PromptOrchestrator (переиспользуется)
        orchestrator = await self._get_prompt_orchestrator()
        if orchestrator is None:
            logger.error(
                "orchestrator not configured for pending tool execution",
                session_id=session_id,
                tool_call_id=tool_call_id,
            )
            return LLMLoopResult(notifications=[], stop_reason="end_turn")

        llm_result = await orchestrator.execute_pending_tool(
            session=session,
            session_id=session_id,
            tool_call_id=tool_call_id,
            mcp_manager=mcp_manager,
        )

        # Сохраняем сессию — критично для permission flow, т.к.
        # LLM loop мог установить новый permission_request_id
        # (агент вызвал ещё tool после выполнения предыдущего).
        try:
            await self._storage.save_session(session)
            logger.debug(
                "session saved after execute_pending_tool",
                session_id=session_id,
                active_turn_perm_request_id=(
                    session.active_turn.permission_request_id
                    if session.active_turn
                    else None
                ),
            )
        except Exception as save_exc:
            logger.error(
                "failed_to_save_session_after_execute_pending_tool",
                session_id=session_id,
                error=str(save_exc),
            )

        return llm_result

    async def _initialize_mcp_servers(
        self,
        session_state: SessionState,
        mcp_servers: list[dict[str, Any]],
    ) -> None:
        """Инициализирует MCP серверы для сессии.
        
        Создаёт MCPManager, подключается к каждому MCP серверу,
        получает инструменты и промпты, регистрирует их для сессии.
        
        Args:
            session_state: Состояние сессии для сохранения MCPManager.
            mcp_servers: Список конфигураций MCP серверов из параметров session/new.
        
        Примечание:
            При ошибке подключения к серверу, ошибка логируется,
            но не прерывает инициализацию других серверов (graceful degradation).
        """
        if not mcp_servers:
            return
        
        # Создаём MCPManager для этой сессии
        mcp_manager = MCPManager(session_state.session_id)
        await self._runtime_registry.set_mcp_manager(
            session_state.session_id, mcp_manager
        )
        
        # Регистрируем callback для отправки available_commands_update при изменении инструментов
        async def _on_mcp_tools_changed() -> None:
            """Отправляет available_commands_update клиенту при изменении MCP инструментов."""
            await self._send_available_commands_update(session_state, mcp_manager)

        mcp_manager.register_tool_change_callback(_on_mcp_tools_changed)

        # Регистрируем callback для уведомлений о статусе серверов
        async def _on_mcp_server_status_changed() -> None:
            """Отправляет notification о disconnect/reconnect MCP сервера."""
            try:
                servers_info = mcp_manager.get_servers_info()
                for server_info in servers_info:
                    status_text = (
                        f"MCP server '{server_info['name']}' "
                        f"status: {server_info['state']}"
                    )
                    notification = ACPMessage.notification(
                        "session/update",
                        {
                            "sessionId": session_state.session_id,
                            "update": {
                                "sessionUpdate": "agent_message_chunk",
                                "content": {
                                    "type": "text",
                                    "text": f"[system] {status_text}",
                                },
                            },
                        },
                    )
                    await self._send_message(notification)
            except Exception as e:
                logger.error(
                    "failed to send MCP server status notification",
                    session_id=session_state.session_id,
                    error=str(e),
                )

        mcp_manager.register_server_status_callback(_on_mcp_server_status_changed)

        # Регистрируем callback для отправки available_commands_update при изменении prompts
        async def _on_mcp_prompts_changed() -> None:
            """Отправляет available_commands_update клиенту при изменении MCP prompts.

            При получении notifications/prompts/list_changed от MCP сервера:
            1. Очищает старые MCP prompt handlers (оставляя built-in)
            2. Перерегистрирует prompts из обновлённого списка
            3. Сохраняет handlers в runtime registry
            4. Отправляет available_commands_update клиенту

            Note:
                Реализует требование MCP спецификации: при изменении списка prompts
                клиент должен быть уведомлён для обновления UI.
            """
            try:
                # Получаем runtime для хранения handlers
                runtime = await self._runtime_registry.get(session_state.session_id)
                if runtime is None:
                    logger.warning(
                        "cannot handle prompts change: runtime not found",
                        session_id=session_state.session_id,
                    )
                    return

                # Очищаем старые MCP prompts (оставляем built-in)
                builtin_names = {"status", "mode", "help"}
                session_state.available_commands = [
                    cmd for cmd in session_state.available_commands
                    if _get_command_name(cmd) in builtin_names
                ]
                runtime.mcp_prompt_handlers.clear()
                session_state.mcp_prompt_handlers.clear()

                # Получаем prompts от всех серверов и регистрируем заново
                all_prompts = await mcp_manager.get_all_prompts()
                for server_config in session_state.mcp_servers:
                    if not isinstance(server_config, dict):
                        continue
                    server_name = server_config.get("name")
                    if not server_name:
                        continue
                    server_prompts = all_prompts.get(server_name, [])
                    if server_prompts:
                        self._register_mcp_prompts_from_list(
                            session_state, mcp_manager, server_name, server_prompts
                        )

                # Копируем handlers из session в runtime (основное хранилище)
                runtime.mcp_prompt_handlers.update(session_state.mcp_prompt_handlers)
                session_state.mcp_prompt_handlers.clear()

                # Отправляем notification с обновлённым списком команд
                await self._send_available_commands_update(session_state, mcp_manager)

                logger.info(
                    "refreshed MCP prompts and sent available_commands_update",
                    session_id=session_state.session_id,
                    prompts_count=len(runtime.mcp_prompt_handlers),
                )
            except Exception as e:
                logger.error(
                    "failed to handle MCP prompts change",
                    session_id=session_state.session_id,
                    error=str(e),
                )

        mcp_manager.register_prompt_change_callback(_on_mcp_prompts_changed)

        for server_config_dict in mcp_servers:
            # Пропускаем невалидные конфигурации
            if not isinstance(server_config_dict, dict):
                logger.warning(
                    "invalid mcp server config, skipping",
                    session_id=session_state.session_id,
                    config=server_config_dict,
                )
                continue
            
            # Проверяем обязательные поля
            name = server_config_dict.get("name")
            command = server_config_dict.get("command")
            if not name or not command:
                logger.warning(
                    "mcp server config missing name or command",
                    session_id=session_state.session_id,
                    config=server_config_dict,
                )
                continue
            
            try:
                # Преобразуем dict в MCPServerConfig
                config = MCPServerConfig(
                    name=name,
                    command=command,
                    args=server_config_dict.get("args", []),
                    env=server_config_dict.get("env", []),
                )
                
                # Добавляем сервер и получаем список инструментов
                # MCP инструменты НЕ регистрируются в глобальном ToolRegistry,
                # т.к. они привязаны к сессии. Доступ к ним через
                # self._runtime_registry.get(session_id).mcp_manager.
                tool_definitions = await mcp_manager.add_server(config)
                
                logger.info(
                    "mcp server initialized",
                    session_id=session_state.session_id,
                    server=name,
                    tools_count=len(tool_definitions),
                    tool_names=[td.name for td in tool_definitions],
                )
                
                # Получаем prompts от MCP сервера и регистрируем как slash-команды
                await self._register_mcp_prompts_as_slash_commands(
                    session_state, mcp_manager, name
                )
                
                # Отправляем initial available_commands_update клиенту
                # Callback вызывается только при notifications/tools/list_changed
                # от MCP сервера, но не при первоначальном подключении
                await _on_mcp_tools_changed()
                
            except MCPManagerError as e:
                # Graceful degradation: логируем ошибку, но продолжаем
                logger.error(
                    "failed to initialize mcp server",
                    session_id=session_state.session_id,
                    server=name,
                    error=str(e),
                )
            except Exception as e:
                # Непредвиденные ошибки также логируем без прерывания
                logger.exception(
                    "unexpected error initializing mcp server",
                    session_id=session_state.session_id,
                    server=name,
                    error=str(e),
                )
    
    async def _register_mcp_prompts_as_slash_commands(
        self,
        session_state: SessionState,
        mcp_manager: MCPManager,
        server_name: str,
    ) -> None:
        """Регистрирует MCP prompts как slash-команды для сессии.

        Получает prompts от указанного MCP сервера, создаёт обработчики
        и сохраняет их в runtime registry для использования при маршрутизации.

        Args:
            session_state: Состояние сессии для обновления available_commands.
            mcp_manager: Менеджер MCP серверов.
            server_name: Имя сервера для получения prompts.
        """
        try:
            all_prompts = await mcp_manager.get_all_prompts()
            server_prompts = all_prompts.get(server_name, [])

            if not server_prompts:
                logger.debug(
                    "no prompts from mcp server",
                    session_id=session_state.session_id,
                    server=server_name,
                )
                return

            # Регистрируем prompts (временно в session_state.mcp_prompt_handlers)
            self._register_mcp_prompts_from_list(
                session_state, mcp_manager, server_name, server_prompts
            )

            # Копируем handlers в runtime (основное хранилище)
            runtime = await self._runtime_registry.get(session_state.session_id)
            if runtime is not None:
                runtime.mcp_prompt_handlers.update(session_state.mcp_prompt_handlers)
                session_state.mcp_prompt_handlers.clear()
        except Exception as e:
            # Graceful degradation: логируем ошибку, но продолжаем
            logger.warning(
                "failed to register mcp prompts as slash commands",
                session_id=session_state.session_id,
                server=server_name,
                error=str(e),
            )
    
    def _register_mcp_prompts_from_list(
        self,
        session_state: SessionState,
        mcp_manager: MCPManager,
        server_name: str,
        server_prompts: list,
    ) -> None:
        """Регистрирует prompts из списка без повторного вызова get_all_prompts().

        Сохраняет handlers в runtime registry (runtime.mcp_prompt_handlers),
        т.к. handlers содержат ссылки на MCPManager и не могут быть сериализованы.

        Args:
            session_state: Состояние сессии для обновления available_commands.
            mcp_manager: Менеджер MCP серверов.
            server_name: Имя сервера.
            server_prompts: Список prompts для регистрации.

        Note:
            Этот метод синхронный и не может получить runtime напрямую.
            Handlers сохраняются в session_state.mcp_prompt_handlers,
            а затем копируются в runtime вызывающим кодом.
        """
        for prompt_def in server_prompts:
            # Формируем arguments_hint из аргументов prompt
            arguments_hint = None
            if prompt_def.arguments:
                arg_parts = []
                for arg in prompt_def.arguments:
                    if arg.required:
                        arg_parts.append(f"<{arg.name}>")
                    else:
                        arg_parts.append(f"[{arg.name}]")
                arguments_hint = " ".join(arg_parts)

            # Создаём handler для этого prompt
            handler = MCPPromptCommandHandler(
                server_id=server_name,
                prompt_name=prompt_def.name,
                mcp_manager=mcp_manager,
                description=prompt_def.title or prompt_def.description or prompt_def.name,
                arguments_hint=arguments_hint,
            )

            # Сохраняем handler в session_state (временное хранение)
            # Вызывающий код (_restore_mcp_prompts, _on_mcp_prompts_changed)
            # копирует handlers в runtime.mcp_prompt_handlers
            session_state.mcp_prompt_handlers[prompt_def.name] = handler

            # Добавляем определение команды в available_commands
            prompt_commands = mcp_prompts_to_available_commands([prompt_def])
            session_state.available_commands.extend(prompt_commands)

            logger.debug(
                "registered mcp prompt as slash command",
                session_id=session_state.session_id,
                server=server_name,
                prompt=prompt_def.name,
            )

        logger.info(
            "registered mcp prompts as slash commands",
            session_id=session_state.session_id,
            server=server_name,
            prompts_count=len(server_prompts),
        )

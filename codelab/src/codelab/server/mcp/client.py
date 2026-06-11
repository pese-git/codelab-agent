"""MCP клиент для взаимодействия с MCP серверами.

Реализует высокоуровневый API для работы с MCP серверами:
инициализацию, получение списка инструментов и вызов инструментов.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from enum import Enum
from typing import Any

from .models import (
    MCPCallToolParams,
    MCPCallToolResult,
    MCPCapabilities,
    MCPClientInfo,
    MCPGetPromptParams,
    MCPGetPromptResult,
    MCPInitializeParams,
    MCPInitializeResult,
    MCPListPromptsParams,
    MCPListPromptsResult,
    MCPListResourcesParams,
    MCPListResourcesResult,
    MCPListResourceTemplatesParams,
    MCPListResourceTemplatesResult,
    MCPListToolsResult,
    MCPProgressNotification,
    MCPPrompt,
    MCPReadResourceParams,
    MCPReadResourceResult,
    MCPResource,
    MCPResourceTemplate,
    MCPRoot,
    MCPServerConfig,
    MCPTool,
)
from .transport import (
    HttpTransportError,
    SseTransportError,
    StdioTransportError,
)
from .transport_factory import MCPTransport, TransportFactory

logger = logging.getLogger(__name__)


# Версия MCP протокола
MCP_PROTOCOL_VERSION = "2024-11-05"

# Информация о нашем клиенте
ACP_CLIENT_INFO = MCPClientInfo(
    name="codelab",
    version="1.0.0"
)


class MCPClientState(Enum):
    """Состояние MCP клиента."""
    
    CREATED = "created"
    """Клиент создан, но не подключен."""
    
    CONNECTING = "connecting"
    """Выполняется подключение к серверу."""
    
    INITIALIZING = "initializing"
    """Выполняется MCP initialize handshake."""
    
    READY = "ready"
    """Клиент готов к работе."""
    
    FAILED = "failed"
    """Произошла ошибка при подключении."""
    
    CLOSED = "closed"
    """Соединение закрыто."""


class MCPClientError(Exception):
    """Базовое исключение для ошибок MCP клиента."""
    pass


class MCPInitializeError(MCPClientError):
    """Ошибка при инициализации MCP соединения."""
    pass


class MCPToolCallError(MCPClientError):
    """Ошибка при вызове инструмента MCP."""
    pass


class MCPClient:
    """Клиент для взаимодействия с одним MCP сервером.
    
    Управляет жизненным циклом подключения к MCP серверу:
    запуск процесса, инициализация, получение инструментов, вызов.
    
    Attributes:
        config: Конфигурация MCP сервера.
        state: Текущее состояние клиента.
        capabilities: Capabilities сервера после инициализации.
        tools: Список доступных инструментов.
        server_name: Имя сервера (из config или от сервера).
    
    Example:
        >>> config = MCPServerConfig(
        ...     name="filesystem",
        ...     command="mcp-server-filesystem",
        ...     args=["--stdio"]
        ... )
        >>> client = MCPClient(config)
        >>> await client.connect()
        >>> tools = await client.list_tools()
        >>> result = await client.call_tool("read_file", {"path": "/tmp/test.txt"})
        >>> await client.disconnect()
    """
    
    def __init__(self, config: MCPServerConfig) -> None:
        """Инициализация MCP клиента.
        
        Args:
            config: Конфигурация MCP сервера для подключения.
        """
        self.config = config
        self._transport: MCPTransport | None = None
        self._state: MCPClientState = MCPClientState.CREATED
        self._capabilities: MCPCapabilities | None = None
        self._server_info: dict[str, str] | None = None
        self._tools: list[MCPTool] = []
        self._resources: list[MCPResource] = []
        self._resource_templates: list[MCPResourceTemplate] = []
        self._prompts: list[MCPPrompt] = []
        self._resources_cache: dict[str, MCPReadResourceResult] = {}
        self._prompts_cache: dict[str, MCPGetPromptResult] = {}
        
        # Notification handling
        self._notification_queue: asyncio.Queue = asyncio.Queue()
        self._notification_handlers: dict[str, list] = {}
        self._notification_task: asyncio.Task | None = None
        
        # Progress notification callbacks
        self._progress_callbacks: list[Callable] = []
        
        # Roots support (MCP specification)
        self._roots: list[MCPRoot] = []
    
    @property
    def state(self) -> MCPClientState:
        """Текущее состояние клиента."""
        return self._state
    
    @property
    def capabilities(self) -> MCPCapabilities | None:
        """Capabilities MCP сервера (доступны после initialize)."""
        return self._capabilities
    
    @property
    def tools(self) -> list[MCPTool]:
        """Список доступных инструментов (после list_tools)."""
        return self._tools
    
    @property
    def server_name(self) -> str:
        """Имя сервера из конфигурации."""
        return self.config.name
    
    @property
    def is_ready(self) -> bool:
        """Проверить, готов ли клиент к работе."""
        return self._state == MCPClientState.READY
    
    @property
    def roots(self) -> list[MCPRoot]:
        """Текущие roots клиента."""
        return self._roots.copy()
    
    async def set_roots(self, roots: list[MCPRoot]) -> None:
        """Установить roots и уведомить сервер об изменении.
        
        Отправляет notifications/roots/list_changed если клиент уже
        инициализирован и сервер поддерживает roots.
        
        Args:
            roots: Новый список roots.
        """
        old_roots = self._roots.copy()
        self._roots = roots.copy()
        
        # Если уже инициализированы, отправляем notification
        if self._state == MCPClientState.READY and self._transport:
            # Проверяем, изменились ли roots
            old_uris = {r.uri for r in old_roots}
            new_uris = {r.uri for r in roots}
            
            if old_uris != new_uris:
                logger.debug(
                    "Sending roots/list_changed to MCP server: %s (roots=%d)",
                    self.config.name,
                    len(roots),
                )
                await self._transport.send_notification(
                    method="notifications/roots/list_changed"
                )
    
    def _handle_roots_list(self) -> list[dict[str, Any]]:
        """Обработать запрос roots/list от сервера.
        
        Returns:
            Список roots в формате для JSON-RPC ответа.
        """
        return [
            {"uri": root.uri, "name": root.name}
            for root in self._roots
        ]
    
    async def _handle_roots_list_request(
        self, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Обработать входящий запрос roots/list от сервера.
        
        Согласно MCP спецификации, сервер может запросить список roots
        через JSON-RPC запрос. Клиент должен ответить списком roots.
        
        Args:
            params: Параметры запроса (обычно пустые).
        
        Returns:
            Словарь с ключом "roots" и списком roots.
        """
        logger.debug(
            "Handling roots/list request from MCP server: %s",
            self.config.name
        )
        
        roots_data = self._handle_roots_list()
        return {"roots": roots_data}
    
    async def connect(self) -> None:
        """Запустить MCP сервер и установить соединение.
        
        Запускает процесс MCP сервера (для stdio) или устанавливает HTTP/SSE соединение.
        Выбор транспорта определяется config.type.
        
        Raises:
            MCPClientError: Если клиент уже подключен.
            MCPClientError: Если не удалось установить соединение.
        """
        if self._state not in (MCPClientState.CREATED, MCPClientState.CLOSED):
            raise MCPClientError(f"Cannot connect in state {self._state}")
        
        self._state = MCPClientState.CONNECTING
        
        logger.info(
            "Connecting to MCP server: %s (type=%s)",
            self.config.name,
            self.config.type,
        )
        
        try:
            # Используем фабрику для создания транспорта
            self._transport = TransportFactory.create(self.config)
            await self._transport.connect()
            
            # Регистрируем обработчик notifications в транспорте
            # Transport будет вызывать этот метод при получении любой notification
            if hasattr(self._transport, 'register_notification_handler'):
                self._transport.register_notification_handler(
                    "*",  # Регистрируем для всех notifications
                    self._on_transport_notification
                )
            
            # Регистрируем обработчик для входящих запросов от сервера
            # Согласно MCP спецификации, сервер может отправлять запросы клиенту
            # (например, roots/list)
            if hasattr(self._transport, 'register_request_handler'):
                self._transport.register_request_handler(
                    "roots/list",
                    self._handle_roots_list_request
                )
                logger.debug(
                    "Registered roots/list request handler for server: %s",
                    self.config.name
                )
            
            logger.debug("MCP %s connection established: %s", self.config.type, self.config.name)
            
        except ValueError as e:
            self._state = MCPClientState.FAILED
            raise MCPClientError(str(e)) from e
        except (StdioTransportError, HttpTransportError, SseTransportError) as e:
            self._state = MCPClientState.FAILED
            raise MCPClientError(f"Failed to connect to MCP server: {e}") from e
    
    async def initialize(self) -> MCPCapabilities:
        """Выполнить MCP initialize handshake.
        
        Отправляет initialize запрос и получает capabilities сервера.
        После успешной инициализации отправляет notifications/initialized.
        
        Returns:
            Capabilities MCP сервера.
        
        Raises:
            MCPInitializeError: Если инициализация не удалась.
            MCPClientError: Если клиент не в состоянии CONNECTING.
        """
        if self._state != MCPClientState.CONNECTING:
            raise MCPClientError(f"Cannot initialize in state {self._state}")
        
        if not self._transport:
            raise MCPClientError("Transport not initialized")
        
        self._state = MCPClientState.INITIALIZING
        
        logger.debug("Sending initialize to MCP server: %s", self.config.name)
        
        try:
            # Формируем capabilities клиента
            client_capabilities: dict[str, Any] = {}
            
            # Добавляем roots support если есть roots
            if self._roots:
                client_capabilities["roots"] = {"listChanged": True}
            
            # Формируем параметры инициализации
            params = MCPInitializeParams(
                protocolVersion=MCP_PROTOCOL_VERSION,
                capabilities=client_capabilities,
                clientInfo=ACP_CLIENT_INFO,
            )
            
            # Отправляем initialize
            result_data = await self._transport.send_request(
                method="initialize",
                params=params.model_dump(by_alias=True),
                timeout=30.0,
            )
            
            # Парсим результат
            result = MCPInitializeResult.model_validate(result_data)
            
            self._capabilities = result.capabilities
            self._server_info = {
                "name": result.server_info.name,
                "version": result.server_info.version,
            }
            
            logger.info(
                "MCP server initialized: %s (server=%s v%s)",
                self.config.name,
                result.server_info.name,
                result.server_info.version,
            )
            
            # Отправляем notifications/initialized
            await self._transport.send_notification(
                method="notifications/initialized"
            )
            
            self._state = MCPClientState.READY
            
            return self._capabilities
            
        except (StdioTransportError, HttpTransportError, SseTransportError) as e:
            self._state = MCPClientState.FAILED
            raise MCPInitializeError(
                f"Initialize failed for {self.config.name}: {e}"
            ) from e
        except Exception as e:
            self._state = MCPClientState.FAILED
            raise MCPInitializeError(
                f"Initialize error for {self.config.name}: {e}"
            ) from e
    
    async def list_tools(self) -> list[MCPTool]:
        """Получить список доступных инструментов от MCP сервера.
        
        Вызывает tools/list и кэширует результат.
        
        Returns:
            Список определений инструментов.
        
        Raises:
            MCPClientError: Если клиент не готов или запрос не удался.
        """
        if self._state != MCPClientState.READY:
            raise MCPClientError(f"Cannot list tools in state {self._state}")
        
        if not self._transport:
            raise MCPClientError("Transport not available")
        
        # Проверяем, поддерживает ли сервер tools
        # По MCP спецификации: tools=null — не поддерживает, tools={} — поддерживает
        if self._capabilities and self._capabilities.tools is None:
            logger.debug(
                "MCP server %s does not support tools",
                self.config.name
            )
            return []
        
        logger.debug("Requesting tools list from: %s", self.config.name)
        
        try:
            result_data = await self._transport.send_request(
                method="tools/list",
                timeout=30.0,
            )
            
            result = MCPListToolsResult.model_validate(result_data)
            self._tools = result.tools
            
            logger.info(
                "MCP server %s provides %d tools",
                self.config.name,
                len(self._tools)
            )
            
            for tool in self._tools:
                logger.debug("  - %s: %s", tool.name, tool.description)
            
            return self._tools
            
        except StdioTransportError as e:
            raise MCPClientError(f"Failed to list tools: {e}") from e
    
    async def list_resources(self) -> list[MCPResource]:
        """Получить список доступных ресурсов от MCP сервера.
        
        Вызывает resources/list с поддержкой cursor-based пагинации.
        Автоматически собирает все страницы результатов.
        
        Returns:
            Список определений ресурсов.
        
        Raises:
            MCPClientError: Если клиент не готов или запрос не удался.
        """
        if self._state != MCPClientState.READY:
            raise MCPClientError(f"Cannot list resources in state {self._state}")
        
        if not self._transport:
            raise MCPClientError("Transport not available")
        
        # Проверяем, поддерживает ли сервер resources
        # По MCP спецификации: resources=null — не поддерживает, resources={} — поддерживает
        if self._capabilities and self._capabilities.resources is None:
            logger.debug(
                "MCP server %s does not support resources",
                self.config.name
            )
            return []
        
        logger.debug("Requesting resources list from: %s", self.config.name)
        
        try:
            all_resources: list[MCPResource] = []
            cursor: str | None = None
            
            # Пагинация: собираем все страницы пока есть nextCursor
            while True:
                params = MCPListResourcesParams(cursor=cursor)
                params_dict = params.model_dump(exclude_none=True)
                
                result_data = await self._transport.send_request(
                    method="resources/list",
                    params=params_dict if params_dict else None,
                    timeout=30.0,
                )
                
                result = MCPListResourcesResult.model_validate(result_data)
                all_resources.extend(result.resources)
                
                if result.next_cursor is None:
                    break
                cursor = result.next_cursor
            
            self._resources = all_resources
            
            logger.info(
                "MCP server %s provides %d resources",
                self.config.name,
                len(self._resources)
            )
            
            return self._resources
            
        except StdioTransportError as e:
            raise MCPClientError(f"Failed to list resources: {e}") from e
    
    async def list_resource_templates(self) -> list[MCPResourceTemplate]:
        """Получить список шаблонов ресурсов от MCP сервера.
        
        Вызывает resources/templates/list с поддержкой cursor-based пагинации.
        Автоматически собирает все страницы результатов.
        
        Returns:
            Список определений шаблонов ресурсов.
        
        Raises:
            MCPClientError: Если клиент не готов или запрос не удался.
        """
        if self._state != MCPClientState.READY:
            raise MCPClientError(
                f"Cannot list resource templates in state {self._state}"
            )
        
        if not self._transport:
            raise MCPClientError("Transport not available")
        
        # Проверяем, поддерживает ли сервер resources (templates — часть resources capability)
        if self._capabilities and self._capabilities.resources is None:
            logger.debug(
                "MCP server %s does not support resources/templates",
                self.config.name
            )
            return []
        
        logger.debug(
            "Requesting resource templates list from: %s",
            self.config.name
        )
        
        try:
            all_templates: list[MCPResourceTemplate] = []
            cursor: str | None = None
            
            # Пагинация: собираем все страницы пока есть nextCursor
            while True:
                params = MCPListResourceTemplatesParams(cursor=cursor)
                params_dict = params.model_dump(exclude_none=True)
                
                result_data = await self._transport.send_request(
                    method="resources/templates/list",
                    params=params_dict if params_dict else None,
                    timeout=30.0,
                )
                
                result = MCPListResourceTemplatesResult.model_validate(result_data)
                all_templates.extend(result.resource_templates)
                
                if result.next_cursor is None:
                    break
                cursor = result.next_cursor
            
            self._resource_templates = all_templates
            
            logger.info(
                "MCP server %s provides %d resource templates",
                self.config.name,
                len(self._resource_templates)
            )
            
            return self._resource_templates
            
        except StdioTransportError as e:
            raise MCPClientError(
                f"Failed to list resource templates: {e}"
            ) from e
    
    async def read_resource(self, uri: str) -> MCPReadResourceResult:
        """Прочитать содержимое ресурса по URI.
        
        Args:
            uri: URI ресурса для чтения.
        
        Returns:
            Содержимое ресурса.
        
        Raises:
            MCPClientError: Если клиент не готов или запрос не удался.
        """
        if self._state != MCPClientState.READY:
            raise MCPClientError(f"Cannot read resource in state {self._state}")
        
        if not self._transport:
            raise MCPClientError("Transport not available")
        
        # Проверяем кэш
        if uri in self._resources_cache:
            logger.debug("Returning cached resource: %s", uri)
            return self._resources_cache[uri]
        
        logger.debug(
            "Reading MCP resource: %s (server=%s)",
            uri, self.config.name
        )
        
        try:
            params = MCPReadResourceParams(uri=uri)
            result_data = await self._transport.send_request(
                method="resources/read",
                params=params.model_dump(),
                timeout=30.0,
            )
            
            result = MCPReadResourceResult.model_validate(result_data)
            
            # Кэшируем результат
            self._resources_cache[uri] = result
            
            logger.debug(
                "MCP resource %s read successfully (%d contents)",
                uri, len(result.contents)
            )
            
            return result
            
        except StdioTransportError as e:
            raise MCPClientError(f"Failed to read resource {uri}: {e}") from e
    
    async def list_prompts(self) -> list[MCPPrompt]:
        """Получить список доступных промптов от MCP сервера.
        
        Вызывает prompts/list с поддержкой cursor-based пагинации.
        Автоматически собирает все страницы результатов.
        
        Returns:
            Список определений промптов.
        
        Raises:
            MCPClientError: Если клиент не готов или запрос не удался.
        """
        if self._state != MCPClientState.READY:
            raise MCPClientError(f"Cannot list prompts in state {self._state}")
        
        if not self._transport:
            raise MCPClientError("Transport not available")
        
        # Проверяем, поддерживает ли сервер prompts
        # По MCP спецификации: prompts=null — не поддерживает, prompts={} — поддерживает
        if self._capabilities and self._capabilities.prompts is None:
            logger.debug(
                "MCP server %s does not support prompts",
                self.config.name
            )
            return []
        
        logger.debug("Requesting prompts list from: %s", self.config.name)
        
        try:
            all_prompts: list[MCPPrompt] = []
            cursor: str | None = None
            
            # Пагинация: собираем все страницы пока есть nextCursor
            while True:
                params = MCPListPromptsParams(cursor=cursor)
                params_dict = params.model_dump(exclude_none=True)
                
                result_data = await self._transport.send_request(
                    method="prompts/list",
                    params=params_dict if params_dict else None,
                    timeout=30.0,
                )
                
                result = MCPListPromptsResult.model_validate(result_data)
                all_prompts.extend(result.prompts)
                
                if result.next_cursor is None:
                    break
                cursor = result.next_cursor
            
            self._prompts = all_prompts
            
            logger.info(
                "MCP server %s provides %d prompts",
                self.config.name,
                len(self._prompts)
            )
            
            return self._prompts
            
        except StdioTransportError as e:
            raise MCPClientError(f"Failed to list prompts: {e}") from e
    
    async def get_prompt(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> MCPGetPromptResult:
        """Получить конкретный промпт с аргументами.
        
        Args:
            name: Имя промпта.
            arguments: Аргументы для промпта.
        
        Returns:
            Промпт с заполненными placeholder'ами.
        
        Raises:
            MCPClientError: Если клиент не готов или запрос не удался.
        """
        if self._state != MCPClientState.READY:
            raise MCPClientError(f"Cannot get prompt in state {self._state}")
        
        if not self._transport:
            raise MCPClientError("Transport not available")
        
        # Создаём cache key
        cache_key = f"{name}:{sorted((arguments or {}).items())}"
        
        # Проверяем кэш
        if cache_key in self._prompts_cache:
            logger.debug("Returning cached prompt: %s", name)
            return self._prompts_cache[cache_key]
        
        logger.debug(
            "Getting MCP prompt: %s (server=%s)",
            name, self.config.name
        )
        
        try:
            params = MCPGetPromptParams(
                name=name,
                arguments=arguments if arguments else None,
            )
            params_dict = params.model_dump(exclude_none=True)
            
            result_data = await self._transport.send_request(
                method="prompts/get",
                params=params_dict,
                timeout=30.0,
            )
            
            result = MCPGetPromptResult.model_validate(result_data)
            
            # Кэшируем результат
            self._prompts_cache[cache_key] = result
            
            logger.debug(
                "MCP prompt %s retrieved successfully (%d messages)",
                name, len(result.messages)
            )
            
            return result
            
        except StdioTransportError as e:
            raise MCPClientError(f"Failed to get prompt {name}: {e}") from e
    
    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        timeout: float = 60.0,
        _meta: dict[str, Any] | None = None,
    ) -> MCPCallToolResult:
        """Вызвать инструмент MCP сервера.
        
        Args:
            name: Имя инструмента для вызова.
            arguments: Аргументы для инструмента.
            timeout: Таймаут выполнения в секундах.
            _meta: Опциональные метаданные (например, progressToken для progress notifications).
        
        Returns:
            Результат вызова инструмента.
        
        Raises:
            MCPToolCallError: Если вызов не удался.
            MCPClientError: Если клиент не готов.
        """
        if self._state != MCPClientState.READY:
            raise MCPClientError(f"Cannot call tool in state {self._state}")
        
        if not self._transport:
            raise MCPClientError("Transport not available")
        
        logger.debug(
            "Calling MCP tool: %s.%s with args=%s",
            self.config.name,
            name,
            arguments
        )
        
        try:
            params = MCPCallToolParams(
                name=name,
                arguments=arguments or {},
                meta=_meta,
            )
            
            result_data = await self._transport.send_request(
                method="tools/call",
                params=params.model_dump(by_alias=True, exclude_none=True),
                timeout=timeout,
            )
            
            result = MCPCallToolResult.model_validate(result_data)
            
            if result.is_error:
                logger.warning(
                    "MCP tool %s.%s returned error: %s",
                    self.config.name,
                    name,
                    result.get_text_content()
                )
            else:
                logger.debug(
                    "MCP tool %s.%s completed successfully",
                    self.config.name,
                    name
                )
            
            return result
            
        except (StdioTransportError, HttpTransportError, SseTransportError) as e:
            raise MCPToolCallError(
                f"Tool call {name} failed: {e}"
            ) from e
    
    async def disconnect(self) -> None:
        """Закрыть соединение с MCP сервером.
        
        Выполняет graceful shutdown транспорта.
        """
        if self._state == MCPClientState.CLOSED:
            return
        
        logger.info("Disconnecting from MCP server: %s", self.config.name)
        
        if self._transport:
            # Единый интерфейс — все транспорты реализуют close()
            await self._transport.close()
            self._transport = None
        
        self._state = MCPClientState.CLOSED
        self._capabilities = None
        self._tools = []
    
    async def __aenter__(self) -> MCPClient:
        """Асинхронный контекстный менеджер - вход.
        
        Выполняет подключение и инициализацию.
        """
        await self.connect()
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Асинхронный контекстный менеджер - выход.
        
        Выполняет отключение.
        """
        await self.disconnect()
    
    # ===== Notification Handling =====
    
    def register_handler(self, method: str, callback) -> None:
        """Зарегистрировать обработчик для notification.
        
        Args:
            method: Имя метода notification.
            callback: Функция для вызова при получении notification.
        """
        if method not in self._notification_handlers:
            self._notification_handlers[method] = []
        self._notification_handlers[method].append(callback)
        
        logger.debug(
            "Registered notification handler for: %s",
            method
        )
    
    def register_progress_callback(self, callback: Callable) -> None:
        """Зарегистрировать callback для progress notifications.

        Callback вызывается при получении notifications/progress от сервера.
        Получает MCPProgressNotification как аргумент.

        Args:
            callback: Async или sync функция, принимающая MCPProgressNotification.
        """
        self._progress_callbacks.append(callback)
        logger.debug(
            "Registered progress callback for: %s",
            self.config.name
        )
    
    async def start_notification_processing(self) -> None:
        """Запустить фоновую задачу обработки notifications."""
        if self._notification_task is not None:
            return
        
        self._notification_task = asyncio.create_task(
            self._process_notifications(),
            name=f"mcp_notification_processor_{self.config.name}"
        )
        
        logger.debug(
            "Started notification processing for: %s",
            self.config.name
        )
    
    async def _process_notifications(self) -> None:
        """Фоновая задача обработки notifications."""
        while self._state == MCPClientState.READY:
            try:
                notification = await asyncio.wait_for(
                    self._notification_queue.get(),
                    timeout=1.0,
                )
                
                method = notification.get("method", "unknown")
                
                logger.debug(
                    "Processing MCP notification: method=%s server=%s",
                    method,
                    self.config.name
                )
                
                # Вызываем зарегистрированные handlers
                handlers = self._notification_handlers.get(method, [])
                for handler in handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(notification.get("params", {}))
                        else:
                            handler(notification.get("params", {}))
                    except Exception as e:
                        logger.error(
                            "Error in notification handler for %s: %s",
                            method, e
                        )
                
                # Специальная обработка progress notifications
                if method == "notifications/progress":
                    await self._handle_progress_notification(
                        notification.get("params", {})
                    )
                
                self._notification_queue.task_done()
                
            except TimeoutError:
                # Таймаут — продолжаем цикл
                continue
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(
                    "Error processing notification: %s",
                    e
                )
    
    async def handle_notification(self, notification_data: dict) -> None:
        """Обработать входящую notification.
        
        Args:
            notification_data: Данные notification.
        """
        method = notification_data.get("method", "unknown")
        
        logger.debug(
            "Received MCP notification: method=%s server=%s",
            method,
            self.config.name
        )
        
        # Помещаем в очередь
        await self._notification_queue.put(notification_data)
    
    async def _on_transport_notification(self, notification_data: dict[str, Any]) -> None:
        """Обработчик notifications от транспорта.
        
        Вызывается transport'ом при получении любой notification от сервера.
        Делегирует обработку в handle_notification.
        
        Args:
            notification_data: Полный JSON-RPC объект notification.
        """
        await self.handle_notification(notification_data)
    
    async def _handle_progress_notification(
        self, params: dict[str, Any]
    ) -> None:
        """Обработать progress notification и вызвать callbacks.

        Парсит params в MCPProgressNotification и вызывает все
        зарегистрированные progress callbacks.

        Args:
            params: Параметры notification из JSON-RPC.
        """
        try:
            progress = MCPProgressNotification.model_validate(params)
        except Exception as e:
            logger.warning(
                "Failed to parse progress notification from %s: %s",
                self.config.name, e
            )
            return
        
        logger.debug(
            "Progress notification from %s: token=%s progress=%s/%s",
            self.config.name,
            progress.progress_token,
            progress.progress,
            progress.total,
        )
        
        for callback in self._progress_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(progress)
                else:
                    callback(progress)
            except Exception as e:
                logger.error(
                    "Error in progress callback for %s: %s",
                    self.config.name, e
                )
    
    async def stop_notification_processing(self) -> None:
        """Остановить фоновую задачу обработки notifications."""
        if self._notification_task is not None:
            self._notification_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._notification_task
            self._notification_task = None
            
            logger.debug(
                "Stopped notification processing for: %s",
                self.config.name
            )

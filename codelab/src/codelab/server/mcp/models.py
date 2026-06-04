"""Pydantic модели для MCP (Model Context Protocol).

Содержит модели для JSON-RPC 2.0 сообщений MCP протокола,
включая запросы, ответы, нотификации и модели инструментов.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ===== JSON-RPC 2.0 Base Models =====


class MCPRequest(BaseModel):
    """JSON-RPC 2.0 запрос для MCP протокола.
    
    Используется для отправки запросов к MCP серверу с ожиданием ответа.
    """
    
    model_config = ConfigDict(populate_by_name=True)
    
    jsonrpc: Literal["2.0"] = "2.0"
    """Версия JSON-RPC протокола."""
    
    id: int | str
    """Уникальный идентификатор запроса для сопоставления с ответом."""
    
    method: str
    """Имя вызываемого метода."""
    
    params: dict[str, Any] | None = None
    """Параметры метода (опционально)."""


class MCPResponse(BaseModel):
    """JSON-RPC 2.0 ответ от MCP сервера.
    
    Содержит либо результат успешного выполнения, либо ошибку.
    """
    
    model_config = ConfigDict(populate_by_name=True)
    
    jsonrpc: Literal["2.0"] = "2.0"
    """Версия JSON-RPC протокола."""
    
    id: int | str | None
    """Идентификатор запроса, на который это ответ."""
    
    result: dict[str, Any] | None = None
    """Результат успешного выполнения (отсутствует при ошибке)."""
    
    error: MCPError | None = None
    """Информация об ошибке (отсутствует при успехе)."""


class MCPNotification(BaseModel):
    """JSON-RPC 2.0 нотификация для MCP протокола.
    
    Односторонняя отправка сообщения без ожидания ответа.
    """
    
    model_config = ConfigDict(populate_by_name=True)
    
    jsonrpc: Literal["2.0"] = "2.0"
    """Версия JSON-RPC протокола."""
    
    method: str
    """Имя метода нотификации."""
    
    params: dict[str, Any] | None = None
    """Параметры нотификации (опционально)."""


class MCPError(BaseModel):
    """Структура ошибки JSON-RPC 2.0.
    
    Содержит код ошибки, сообщение и дополнительные данные.
    """
    
    code: int
    """Код ошибки (стандартные JSON-RPC или MCP-специфичные)."""
    
    message: str
    """Краткое описание ошибки."""
    
    data: Any | None = None
    """Дополнительные данные об ошибке (опционально)."""


# ===== MCP Server Info Models =====


class MCPServerInfo(BaseModel):
    """Информация о MCP сервере.
    
    Возвращается сервером при инициализации.
    """
    
    name: str
    """Имя MCP сервера."""
    
    version: str
    """Версия сервера."""


class MCPClientInfo(BaseModel):
    """Информация о MCP клиенте.
    
    Отправляется серверу при инициализации.
    """
    
    name: str
    """Имя клиента."""
    
    version: str
    """Версия клиента."""


class MCPCapabilities(BaseModel):
    """Capabilities MCP сервера.
    
    Описывает поддерживаемые возможности сервера.
    """
    
    model_config = ConfigDict(extra="allow")
    
    tools: dict[str, Any] | None = None
    """Поддержка инструментов (tools)."""
    
    resources: dict[str, Any] | None = None
    """Поддержка ресурсов (resources)."""
    
    prompts: dict[str, Any] | None = None
    """Поддержка промптов (prompts)."""
    
    logging: dict[str, Any] | None = None
    """Поддержка логирования."""


class MCPInitializeParams(BaseModel):
    """Параметры запроса initialize.
    
    Отправляются MCP серверу для инициализации соединения.
    """
    
    model_config = ConfigDict(populate_by_name=True)
    
    protocol_version: str = Field(alias="protocolVersion")
    """Версия MCP протокола (например, "2024-11-05")."""
    
    capabilities: dict[str, Any] = Field(default_factory=dict)
    """Capabilities клиента."""
    
    client_info: MCPClientInfo = Field(alias="clientInfo")
    """Информация о клиенте."""


class MCPInitializeResult(BaseModel):
    """Результат initialize от MCP сервера.
    
    Содержит информацию о сервере и его capabilities.
    """
    
    model_config = ConfigDict(populate_by_name=True)
    
    protocol_version: str = Field(alias="protocolVersion")
    """Версия протокола, согласованная сервером."""
    
    capabilities: MCPCapabilities
    """Capabilities сервера."""
    
    server_info: MCPServerInfo = Field(alias="serverInfo")
    """Информация о сервере."""
    
    instructions: str | None = None
    """Инструкции от сервера (опционально)."""


# ===== MCP Tool Models =====


class MCPToolInputSchema(BaseModel):
    """JSON Schema для входных параметров инструмента.
    
    Описывает структуру аргументов, которые принимает инструмент.
    """
    
    model_config = ConfigDict(extra="allow")
    
    type: str = "object"
    """Тип схемы (обычно object)."""
    
    properties: dict[str, Any] = Field(default_factory=dict)
    """Описания свойств (аргументов инструмента)."""
    
    required: list[str] = Field(default_factory=list)
    """Список обязательных аргументов."""


class MCPToolAnnotations(BaseModel):
    """Аннотации MCP инструмента (ToolAnnotations по MCP spec 2025-06-18).

    Используются для UX/kind mapping — не влияют на security/permission решения.
    """

    model_config = ConfigDict(populate_by_name=True)

    title: str | None = None
    """Человекочитаемое название инструмента."""

    read_only_hint: bool | None = Field(default=None, alias="readOnlyHint")
    """True если инструмент только читает данные (не изменяет)."""

    destructive_hint: bool | None = Field(default=None, alias="destructiveHint")
    """True если инструмент может разрушительно изменять данные."""

    idempotent_hint: bool | None = Field(default=None, alias="idempotentHint")
    """True если повторный вызов с теми же аргументами не меняет результат."""

    open_world_hint: bool | None = Field(default=None, alias="openWorldHint")
    """True если инструмент работает с открытым миром (внешние API, веб)."""


class MCPTool(BaseModel):
    """Определение инструмента MCP сервера.

    Содержит имя, описание и схему входных параметров.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str
    """Уникальное имя инструмента."""

    description: str | None = None
    """Описание назначения инструмента."""

    input_schema: MCPToolInputSchema = Field(
        alias="inputSchema",
        default_factory=MCPToolInputSchema
    )
    """JSON Schema входных параметров."""

    annotations: MCPToolAnnotations | None = None
    """Опциональные аннотации инструмента (hints для kind inference)."""


class MCPListToolsResult(BaseModel):
    """Результат запроса tools/list.
    
    Содержит список доступных инструментов на MCP сервере.
    """
    
    tools: list[MCPTool]
    """Список доступных инструментов."""


# ===== MCP Resource Models =====


class MCPAnnotations(BaseModel):
    """Аннотации для ресурсов и шаблонов (MCP spec 2025-06-18+).
    
    Содержат метаданные для отображения и приоритизации.
    """
    
    model_config = ConfigDict(populate_by_name=True)
    
    audience: list[str] | None = None
    """Целевая аудитория: 'user' и/или 'assistant'."""
    
    priority: float | None = None
    """Приоритет от 0.0 до 1.0 (1.0 = наиболее важно)."""
    
    last_modified: str | None = Field(default=None, alias="lastModified")
    """ISO 8601 timestamp последнего изменения."""


class MCPResourceIcon(BaseModel):
    """Иконка для ресурса или шаблона (MCP spec 2025-11-25+).
    
    Содержит URI иконки и метаданные.
    """
    
    model_config = ConfigDict(populate_by_name=True)
    
    src: str
    """URI иконки."""
    
    mime_type: str | None = Field(default=None, alias="mimeType")
    """MIME-тип иконки (например, image/png)."""
    
    sizes: list[str] | None = None
    """Размеры иконки (например, ['48x48', '96x96'])."""


class MCPResource(BaseModel):
    """Определение ресурса MCP сервера.
    
    Содержит URI, имя и описание ресурса.
    """
    
    model_config = ConfigDict(populate_by_name=True)
    
    uri: str
    """Уникальный URI ресурса (RFC 3986)."""
    
    name: str
    """Человекочитаемое имя ресурса."""
    
    title: str | None = None
    """Человекочитаемое отображаемое имя."""
    
    description: str | None = None
    """Описание ресурса."""
    
    mime_type: str | None = Field(default=None, alias="mimeType")
    """MIME-тип ресурса (например, text/plain, image/png)."""
    
    size: int | None = None
    """Размер ресурса в байтах."""
    
    icons: list[MCPResourceIcon] | None = None
    """Массив иконок ресурса."""
    
    annotations: MCPAnnotations | None = None
    """Аннотации для отображения и приоритизации."""


class MCPListResourcesParams(BaseModel):
    """Параметры запроса resources/list.
    
    Поддерживает cursor-based пагинацию.
    """
    
    cursor: str | None = None
    """Opaque cursor для пагинации."""


class MCPListResourcesResult(BaseModel):
    """Результат запроса resources/list.
    
    Содержит список доступных ресурсов на MCP сервере.
    """
    
    model_config = ConfigDict(populate_by_name=True)
    
    resources: list[MCPResource]
    """Список доступных ресурсов."""
    
    next_cursor: str | None = Field(default=None, alias="nextCursor")
    """Cursor для следующей страницы (отсутствует = конец результатов)."""


class MCPResourceTemplate(BaseModel):
    """Шаблон ресурса MCP сервера.
    
    Содержит URI template для динамических ресурсов.
    """
    
    model_config = ConfigDict(populate_by_name=True)
    
    uri_template: str = Field(alias="uriTemplate")
    """URI template (RFC 6570, например, file:///{path})."""
    
    name: str
    """Человекочитаемое имя шаблона."""
    
    title: str | None = None
    """Человекочитаемое отображаемое имя."""
    
    description: str | None = None
    """Описание шаблона."""
    
    mime_type: str | None = Field(default=None, alias="mimeType")
    """MIME-тип ресурсов этого шаблона."""
    
    icons: list[MCPResourceIcon] | None = None
    """Массив иконок шаблона."""
    
    annotations: MCPAnnotations | None = None
    """Аннотации для отображения и приоритизации."""


class MCPListResourceTemplatesParams(BaseModel):
    """Параметры запроса resources/templates/list.
    
    Поддерживает cursor-based пагинацию.
    """
    
    cursor: str | None = None
    """Opaque cursor для пагинации."""


class MCPListResourceTemplatesResult(BaseModel):
    """Результат запроса resources/templates/list.
    
    Содержит список шаблонов ресурсов на MCP сервере.
    """
    
    model_config = ConfigDict(populate_by_name=True)
    
    resource_templates: list[MCPResourceTemplate] = Field(
        default_factory=list,
        alias="resourceTemplates",
    )
    """Список шаблонов ресурсов."""
    
    next_cursor: str | None = Field(default=None, alias="nextCursor")
    """Cursor для следующей страницы (отсутствует = конец результатов)."""


class MCPReadResourceParams(BaseModel):
    """Параметры запроса resources/read.

    Содержит URI ресурса, который нужно прочитать.
    """

    uri: str
    """URI ресурса для чтения."""


class MCPResourceContent(BaseModel):
    """Типизированный контент ресурса.
    
    Может быть текстовым или бинарным (blob).
    """
    
    model_config = ConfigDict(populate_by_name=True)
    
    uri: str
    """URI ресурса."""
    
    mime_type: str | None = Field(default=None, alias="mimeType")
    """MIME-тип ресурса."""
    
    # Текстовый контент
    text: str | None = None
    """Текстовое содержимое (для text/* ресурсов)."""
    
    # Бинарный контент
    blob: str | None = None
    """Base64-закодированный бинарный контент."""
    
    def get_text_content(self) -> str:
        """Извлечь текстовый контент.
        
        Returns:
            Текст или base64 blob.
        """
        if self.text is not None:
            return self.text
        if self.blob is not None:
            return self.blob
        return ""


class MCPReadResourceResult(BaseModel):
    """Результат запроса resources/read.
    
    Содержит содержимое ресурса.
    """
    
    model_config = ConfigDict(populate_by_name=True)
    
    contents: list[dict[str, Any]] | list[MCPResourceContent] = Field(
        default_factory=list,
    )
    """Список элементов содержимого ресурса."""
    
    def get_text_content(self) -> str:
        """Извлечь текстовый контент из результата.
        
        Returns:
            Объединённый текст из всех текстовых элементов.
        """
        texts: list[str] = []
        for item in self.contents:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    texts.append(item.get("text", ""))
                elif item.get("type") == "resource":
                    resource = item.get("resource", {})
                    if resource.get("text"):
                        texts.append(resource["text"])
                    elif resource.get("blob"):
                        texts.append(resource["blob"])
            elif isinstance(item, MCPResourceContent):
                texts.append(item.get_text_content())
        return "\n".join(texts)


# ===== MCP Prompt Models =====


class MCPPromptArgument(BaseModel):
    """Определение аргумента промпта MCP сервера.
    
    Описывает один аргумент, который принимает промпт.
    """
    
    model_config = ConfigDict(populate_by_name=True)
    
    name: str
    """Имя аргумента."""
    
    title: str | None = None
    """Человекочитаемое отображаемое имя аргумента."""
    
    description: str | None = None
    """Описание аргумента."""
    
    required: bool = False
    """Обязателен ли аргумент."""


class MCPPrompt(BaseModel):
    """Определение промпта MCP сервера.
    
    Содержит имя, описание и аргументы промпта.
    Промпты — это переиспользуемые шаблоны для структурирования
    взаимодействий с языковой моделью.
    """
    
    model_config = ConfigDict(populate_by_name=True)
    
    name: str
    """Уникальное имя промпта."""
    
    title: str | None = None
    """Человекочитаемое отображаемое имя промпта."""
    
    description: str | None = None
    """Описание промпта."""
    
    arguments: list[MCPPromptArgument] = Field(default_factory=list)
    """Список аргументов промпта."""


class MCPListPromptsParams(BaseModel):
    """Параметры запроса prompts/list.
    
    Поддерживает cursor-based пагинацию.
    """
    
    cursor: str | None = None
    """Opaque cursor для пагинации."""


class MCPListPromptsResult(BaseModel):
    """Результат запроса prompts/list.
    
    Содержит список доступных промптов на MCP сервере.
    """
    
    model_config = ConfigDict(populate_by_name=True)
    
    prompts: list[MCPPrompt]
    """Список доступных промптов."""
    
    next_cursor: str | None = Field(default=None, alias="nextCursor")
    """Cursor для следующей страницы (отсутствует = конец результатов)."""


class MCPGetPromptParams(BaseModel):
    """Параметры запроса prompts/get.
    
    Содержит имя промпта и аргументы для заполнения placeholder'ов.
    """
    
    name: str
    """Имя промпта для получения."""
    
    arguments: dict[str, str] | None = None
    """Аргументы для заполнения placeholder'ов промпта."""


class MCPPromptMessage(BaseModel):
    """Сообщение в результате prompts/get.
    
    Содержит роль отправителя и контент сообщения.
    """
    
    model_config = ConfigDict(populate_by_name=True)
    
    role: str
    """Роль отправителя: 'user' или 'assistant'."""
    
    content: dict[str, Any]
    """Контент сообщения (MCPContent: text, image, resource)."""


class MCPGetPromptResult(BaseModel):
    """Результат запроса prompts/get.
    
    Содержит промпт с заполненными placeholder'ами.
    """
    
    model_config = ConfigDict(populate_by_name=True)
    
    description: str | None = None
    """Описание промпта."""
    
    messages: list[dict[str, Any]] | list[MCPPromptMessage] = Field(
        default_factory=list,
    )
    """Список сообщений промпта."""


# ===== MCP Tool Call Models =====


class MCPCallToolParams(BaseModel):
    """Параметры запроса tools/call.
    
    Содержит имя инструмента и аргументы для вызова.
    """
    
    name: str
    """Имя вызываемого инструмента."""
    
    arguments: dict[str, Any] = Field(default_factory=dict)
    """Аргументы для инструмента."""


class MCPTextContent(BaseModel):
    """Текстовый контент в результате вызова инструмента."""
    
    type: Literal["text"] = "text"
    """Тип контента."""
    
    text: str
    """Текстовое содержимое."""


class MCPImageContent(BaseModel):
    """Изображение в результате вызова инструмента (base64)."""
    
    type: Literal["image"] = "image"
    """Тип контента."""
    
    data: str
    """Base64-закодированное изображение."""
    
    mime_type: str = Field(alias="mimeType")
    """MIME-тип изображения (например, image/png)."""


class MCPEmbeddedResource(BaseModel):
    """Встроенный ресурс в результате вызова инструмента."""
    
    type: Literal["resource"] = "resource"
    """Тип контента."""
    
    resource: dict[str, Any]
    """Данные ресурса."""


# Объединённый тип для контента в результатах
MCPContent = MCPTextContent | MCPImageContent | MCPEmbeddedResource


class MCPCallToolResult(BaseModel):
    """Результат вызова инструмента tools/call.
    
    Содержит контент результата и флаг ошибки.
    """
    
    model_config = ConfigDict(populate_by_name=True)
    
    content: list[dict[str, Any]] = Field(default_factory=list)
    """Список элементов контента результата."""
    
    is_error: bool = Field(default=False, alias="isError")
    """True если инструмент вернул ошибку."""
    
    def get_text_content(self) -> str:
        """Извлечь текстовый контент из результата.
        
        Returns:
            Объединённый текст из всех текстовых элементов.
        """
        texts: list[str] = []
        for item in self.content:
            if item.get("type") == "text":
                texts.append(item.get("text", ""))
        return "\n".join(texts)


# ===== MCP Server Configuration =====


class MCPServerConfig(BaseModel):
    """Конфигурация MCP сервера из параметров session/new.
    
    Описывает как запустить и подключиться к MCP серверу.
    Поддерживает три типа транспорта: stdio, http, sse.
    """
    
    model_config = ConfigDict(populate_by_name=True)
    
    name: str
    """Уникальное имя сервера (идентификатор)."""
    
    type: str = "stdio"
    """Тип транспорта: stdio, http, sse."""
    
    # Stdio transport параметры
    command: str | None = None
    """Команда для запуска сервера (для stdio)."""
    
    args: list[str] = Field(default_factory=list)
    """Аргументы командной строки (для stdio)."""
    
    env: list[dict[str, str]] = Field(default_factory=list)
    """Переменные окружения как список {name: value}."""
    
    # HTTP/SSE transport параметры
    url: str | None = None
    """URL MCP сервера (для http/sse)."""
    
    headers: list[dict[str, str]] = Field(default_factory=list)
    """HTTP headers для запросов (для http/sse)."""
    
    # Retry configuration
    max_retries: int = 5
    """Максимальное количество попыток переподключения."""
    
    initial_delay: float = 1.0
    """Начальная задержка между попытками (секунды)."""
    
    max_delay: float = 30.0
    """Максимальная задержка между попытками (секунды)."""
    
    backoff_multiplier: float = 2.0
    """Множитель для exponential backoff."""
    
    def model_post_init(self, __context) -> None:
        """Валидация конфигурации после инициализации."""
        # Stdio требует command
        if self.type == "stdio" and not self.command:
            raise ValueError(
                "MCPServerConfig: type='stdio' requires 'command' field"
            )
        
        # HTTP/SSE требует url
        if self.type in ("http", "sse") and not self.url:
            raise ValueError(
                f"MCPServerConfig: type='{self.type}' requires 'url' field"
            )
    
    def get_env_dict(self) -> dict[str, str]:
        """Преобразовать список env в словарь.
        
        Returns:
            Словарь переменных окружения.
        """
        result: dict[str, str] = {}
        for item in self.env:
            # Формат может быть {"name": "KEY", "value": "VAL"} или {"KEY": "VAL"}
            if "name" in item and "value" in item:
                result[item["name"]] = item["value"]
            else:
                result.update(item)
        return result
    
    def get_connection_params(self) -> dict[str, Any]:
        """Получить параметры подключения в зависимости от типа транспорта.
        
        Returns:
            Словарь параметров для транспорта.
        
        Raises:
            ValueError: Если тип транспорта не поддерживается.
        """
        if self.type == "stdio":
            return {
                "command": self.command,
                "args": self.args,
                "env": self.get_env_dict(),
            }
        elif self.type in ("http", "sse"):
            return {
                "url": self.url,
                "headers": self.headers,
            }
        else:
            raise ValueError(f"Unsupported transport type: {self.type}")
    
    def get_retry_config(self) -> dict[str, float | int]:
        """Получить конфигурацию retry.
        
        Returns:
            Словарь с retry parameters.
        """
        return {
            "max_retries": self.max_retries,
            "initial_delay": self.initial_delay,
            "max_delay": self.max_delay,
            "backoff_multiplier": self.backoff_multiplier,
        }

"""Data Transfer Objects (DTOs) - контракты для обмена данными между слоями.

DTOs используются для:
- Передачи данных между Application и Presentation слоями
- Типизации параметров use cases
- Валидации входных данных

Content models (ImageContent, AudioContent и т.д.) импортируются из domain слоя,
так как они являются domain-концептами согласно ACP спецификации.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

# Импортируем domain модели для мультимодального контента
# Это domain-концепты, не DTO, но они используются в SendPromptRequest
from ..domain.content_blocks import (
    AudioContent,
    ImageContent,
    ResourceContent,
    ResourceLinkContent,
)

# Type aliases для callback функций
UpdateCallback = Callable[[dict[str, Any]], None]
FsReadCallback = Callable[[str], str | Awaitable[str]]
FsWriteCallback = Callable[[str, str], None | Awaitable[None]]
TerminalCreateCallback = Callable[[str], str | Awaitable[str]]
TerminalOutputCallback = Callable[[str], dict[str, Any] | Awaitable[dict[str, Any]]]
TerminalWaitResult = tuple[int | None, str | None]
TerminalWaitCallback = Callable[[str], TerminalWaitResult | Awaitable[TerminalWaitResult]]
TerminalReleaseCallback = Callable[[str], None | Awaitable[None]]
TerminalKillCallback = Callable[[str], bool | Awaitable[bool]]


@dataclass
class CreateSessionRequest:
    """Request DTO для создания новой сессии.

    Содержит параметры необходимые для создания сессии
    на стороне Application слоя.
    """

    server_host: str
    """Адрес ACP сервера."""

    server_port: int
    """Порт ACP сервера."""

    cwd: str
    """Абсолютный путь рабочей директории сессии (обязательный параметр ACP протокола)."""

    client_capabilities: dict[str, Any] | None = None
    """Возможности клиента (если None, используются default)."""

    auth_method: str | None = None
    """Метод аутентификации (если требуется)."""

    auth_credentials: dict[str, Any] | None = None
    """Учетные данные для аутентификации."""

    mcp_servers: list[dict[str, Any]] | None = None
    """Список MCP-серверов для `session/new` (если None, используется пустой список)."""


@dataclass
class CreateSessionResponse:
    """Response DTO для результата создания сессии.

    Содержит данные созданной сессии для возврата в Presentation слой.
    """

    session_id: str
    """Уникальный ID созданной сессии."""

    server_capabilities: dict[str, Any]
    """Возможности сервера, полученные при initialize."""

    is_authenticated: bool
    """Авторизован ли клиент на этой сессии."""


@dataclass
class LoadSessionRequest:
    """Request DTO для загрузки существующей сессии.

    Содержит параметры необходимые для загрузки сессии
    из хранилища.
    """

    session_id: str
    """ID сессии для загрузки."""

    server_host: str
    """Адрес ACP сервера."""

    server_port: int
    """Порт ACP сервера."""

    cwd: str | None = None
    """Абсолютный путь рабочей директории для `session/load` (если None, берется текущий)."""

    mcp_servers: list[dict[str, Any]] | None = None
    """Список MCP-серверов для `session/load` (если None, используется пустой список)."""


@dataclass
class LoadSessionResponse:
    """Response DTO для результата загрузки сессии.

    Содержит загруженную сессию и историю для воспроизведения.
    """

    session_id: str
    """ID загруженной сессии."""

    server_capabilities: dict[str, Any]
    """Возможности сервера."""

    is_authenticated: bool
    """Авторизован ли клиент."""

    replay_updates: list[dict[str, Any]]
    """История обновлений для воспроизведения в UI."""


@dataclass
class SendPromptRequest:
    """Request DTO для отправки prompt в сессию.

    Содержит параметры prompt и callbacks для обработки событий.
    Поддерживает мультимодальный контент согласно ACP спецификации.

    Content models (ImageContent, AudioContent и т.д.) являются domain-концептами
    и импортируются из domain слоя.
    """

    session_id: str
    """ID сессии."""

    prompt_text: str
    """Текст prompt."""

    images: list[ImageContent] | None = None
    """Список изображений для отправки (требует promptCapabilities.image)."""

    audio: list[AudioContent] | None = None
    """Список аудио для отправки (требует promptCapabilities.audio)."""

    resources: list[ResourceContent] | None = None
    """Список embedded resources (требует promptCapabilities.embeddedContext)."""

    resource_links: list[ResourceLinkContent] | None = None
    """Список ссылок на ресурсы (поддерживается всегда)."""

    callbacks: PromptCallbacks | None = None
    """Callbacks для обработки событий во время выполнения."""


@dataclass
class PromptCallbacks:
    """Callbacks для обработки событий во время выполнения prompt.

    Содержит функции обработки различных событий,
    которые возникают во время выполнения prompt.
    """

    on_update: UpdateCallback | None = None
    """Callback при получении обновления сессии."""

    on_fs_read: FsReadCallback | None = None
    """Callback при чтении файла."""

    on_fs_write: FsWriteCallback | None = None
    """Callback при записи файла."""

    on_terminal_create: TerminalCreateCallback | None = None
    """Callback при создании терминала."""

    on_terminal_output: TerminalOutputCallback | None = None
    """Callback при получении вывода терминала."""

    on_terminal_wait_for_exit: TerminalWaitCallback | None = None
    """Callback при ожидании выхода терминала."""

    on_terminal_release: TerminalReleaseCallback | None = None
    """Callback при освобождении терминала."""

    on_terminal_kill: TerminalKillCallback | None = None
    """Callback при завершении терминала."""


@dataclass
class SendPromptResponse:
    """Response DTO для результата отправки prompt.

    Содержит результат выполнения prompt и финальное состояние.
    """

    session_id: str
    """ID сессии."""

    prompt_result: dict[str, Any]
    """Результат выполнения prompt."""

    updates: list[dict[str, Any]]
    """Обновления, полученные во время выполнения."""


@dataclass
class InitializeResponse:
    """Response DTO для результата инициализации.

    Содержит информацию о сервере и его возможностях.
    """

    server_capabilities: dict[str, Any]
    """Возможности сервера."""

    available_auth_methods: list[str]
    """Доступные методы аутентификации."""

    protocol_version: str
    """Версия протокола ACP."""


@dataclass
class ListSessionsResponse:
    """Response DTO для получения списка сессий.

    Содержит список доступных сессий.
    """

    sessions: list[dict[str, Any]]
    """Список сессий с метаданными."""

"""SessionNewCommandHandler - обработчик метода session/new.

Создает новую сессию с указанной working directory и MCP серверами.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from ...messages import ACPMessage
from ...storage import SessionStorage
from ..handlers import session
from ..session_factory import SessionFactory
from ..state import ClientRuntimeCapabilities, ProtocolOutcome, SessionState

logger = structlog.get_logger()


class SessionNewCommandHandler:
    """Обработчик метода session/new.

    Отвечает за:
    - Валидацию параметров (cwd, mcpServers)
    - Создание новой сессии через SessionFactory
    - Инициализацию MCP серверов
    - Сохранение сессии в storage

    Attributes:
        method_name: Имя обрабатываемого метода.
    """

    method_name = "session/new"

    def __init__(
        self,
        storage: SessionStorage,
        config_specs: dict[str, dict[str, Any]],
        auth_methods: list[dict[str, Any]],
        require_auth: bool,
        authenticated: bool,
        runtime_capabilities: ClientRuntimeCapabilities | None = None,
        command_registry: Any | None = None,
        on_session_created: Callable[[SessionState, dict[str, Any]], Awaitable[None]]
        | None = None,
    ) -> None:
        """Инициализирует обработчик.

        Args:
            storage: Хранилище сессий.
            config_specs: Спецификации конфигурационных опций.
            auth_methods: Список методов аутентификации.
            require_auth: Требуется ли аутентификация.
            authenticated: Текущее состояние аутентификации.
            runtime_capabilities: Runtime-возможности клиента.
            command_registry: Реестр slash-команд для available_commands.
            on_session_created: Callback, вызываемый после создания сессии
                для выполнения side effects (MCP setup и т.д.).
        """
        self._storage = storage
        self._config_specs = config_specs
        self._auth_methods = auth_methods
        self._require_auth = require_auth
        self._authenticated = authenticated
        self._runtime_capabilities = runtime_capabilities
        self._command_registry = command_registry
        self._on_session_created = on_session_created

    async def handle(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает метод session/new.

        Args:
            message: Входящее JSON-RPC сообщение.

        Returns:
            ProtocolOutcome с результатом создания сессии.
        """
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

        # Если создание прошло успешно, сохраняем в storage
        if response_msg.result is not None:
            session_id = response_msg.result.get("sessionId")
            if isinstance(session_id, str):
                config_values = {
                    config_id: str(spec["default"])
                    for config_id, spec in self._config_specs.items()
                }
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

                # Выполняем side effects через callback
                if self._on_session_created:
                    await self._on_session_created(session_state, params)

                await self._storage.save_session(session_state)

                logger.info(
                    "session_created",
                    session_id=session_id,
                    cwd=params.get("cwd"),
                )

        return ProtocolOutcome(response=response_msg)

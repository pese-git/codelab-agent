"""SessionLoadCommandHandler - обработчик метода session/load.

Загружает существующую сессию и восстанавливает её контекст.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from ...messages import ACPMessage
from ...storage import SessionStorage
from ..handlers import session
from ..pending_registry import PendingRequestRegistry
from ..state import ClientRuntimeCapabilities, ProtocolOutcome, SessionState

logger = structlog.get_logger()


class SessionLoadCommandHandler:
    """Обработчик метода session/load.

    Отвечает за:
    - Загрузку сессии из storage
    - Обновление runtime-возможностей клиента
    - Инициализацию MCP серверов
    - Обработку orphaned permission requests

    Attributes:
        method_name: Имя обрабатываемого метода.
    """

    method_name = "session/load"

    def __init__(
        self,
        storage: SessionStorage,
        config_specs: dict[str, dict[str, Any]],
        auth_methods: list[dict[str, Any]],
        require_auth: bool,
        authenticated: bool,
        runtime_capabilities: ClientRuntimeCapabilities | None = None,
        pending_registry: PendingRequestRegistry | None = None,
        on_session_loaded: Callable[[SessionState, dict[str, Any]], Awaitable[None]]
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
            pending_registry: Реестр pending permission requests.
            on_session_loaded: Callback для side effects (MCP setup и т.д.).
        """
        self._storage = storage
        self._config_specs = config_specs
        self._auth_methods = auth_methods
        self._require_auth = require_auth
        self._authenticated = authenticated
        self._runtime_capabilities = runtime_capabilities
        self._pending_registry = pending_registry or PendingRequestRegistry()
        self._on_session_loaded = on_session_loaded

    async def handle(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает метод session/load.

        Args:
            message: Входящее JSON-RPC сообщение.

        Returns:
            ProtocolOutcome с результатом загрузки сессии.
        """
        params = message.params or {}
        session_id = params.get("sessionId")

        if isinstance(session_id, str):
            session_obj = await self._storage.load_session(session_id)
            if session_obj is not None:
                session_obj.runtime_capabilities = self._runtime_capabilities

                # Выполняем side effects через callback
                if self._on_session_loaded:
                    await self._on_session_loaded(session_obj, params)

                # Обработка orphaned permission requests
                if (
                    session_obj.active_turn
                    and session_obj.active_turn.permission_request_id
                ):
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

"""SessionLoadCommandHandler - обработчик метода session/load.

Загружает существующую сессию и восстанавливает её контекст.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from codelab.server.storage.document import ClientRuntimeCapabilities

from ...domain.session import Session as DomainSession
from ...mapping.session_mapper import SessionMapper
from ...messages import ACPMessage
from ...storage import SessionRepository
from ..handlers import session
from ..pending_registry import PendingRequestRegistry
from ..state import ProtocolOutcome

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
        repository: SessionRepository,
        config_specs: dict[str, dict[str, Any]],
        auth_methods: list[dict[str, Any]],
        require_auth: bool,
        authenticated: bool,
        runtime_capabilities: ClientRuntimeCapabilities | None = None,
        pending_registry: PendingRequestRegistry | None = None,
        on_session_loaded: Callable[[DomainSession, dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        """Инициализирует обработчик.

        Args:
            repository: Доменный порт хранилища сессий.
            config_specs: Спецификации конфигурационных опций.
            auth_methods: Список методов аутентификации.
            require_auth: Требуется ли аутентификация.
            authenticated: Текущее состояние аутентификации.
            runtime_capabilities: Runtime-возможности клиента.
            pending_registry: Реестр pending permission requests.
            on_session_loaded: Callback для side effects (MCP setup и т.д.).
        """
        self._repository = repository
        self._config_specs = config_specs
        self._auth_methods = auth_methods
        self._require_auth = require_auth
        self._authenticated = authenticated
        self._runtime_capabilities = runtime_capabilities
        # `is None`, а не `or`: у реестра есть `__len__`, поэтому пустой экземпляр
        # ложен — идиома `x or Default()` молча подменяла переданный из DI реестр
        # новым, и писатель с читателем работали бы с разными объектами.
        self._pending_registry = (
            pending_registry if pending_registry is not None else PendingRequestRegistry()
        )
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
        session_obj: DomainSession | None = None

        if isinstance(session_id, str):
            # Носитель — доменный агрегат от загрузки до записи: круга
            # `to_protocol`/`to_domain` здесь больше нет (ADR-006, фаза D шаг 5).
            session_obj = await self._repository.load_session(session_id)
            if session_obj is not None:
                session_obj.apply_client_context(
                    cwd=session_obj.config.cwd,
                    mcp_servers=session_obj.config.mcp_servers,
                    runtime_capabilities=SessionMapper.capabilities_to_domain(self._runtime_capabilities),
                )

                # Side effects (MCP-setup) работают тем же агрегатом: их правки
                # `available_commands` уезжают на диск вместе с ним.
                if self._on_session_loaded:
                    await self._on_session_loaded(session_obj, params)

                # Обработка orphaned permission requests
                if session_obj.active_turn and session_obj.active_turn.permission_request_id:
                    perm_req_id = session_obj.active_turn.permission_request_id
                    if not self._pending_registry.has(perm_req_id):
                        logger.warning(
                            "session_loaded_with_orphaned_permission_request",
                            session_id=session_id,
                            permission_request_id=perm_req_id,
                        )
                        session_obj.clear_active_turn()
                        # Отдельное сохранение здесь больше не нужно: транзакция
                        # сохраняет объект целиком в конце (P2-42).

        outcome = await session.session_load(
            message.id,
            params,
            self._require_auth,
            self._authenticated,
            self._config_specs,
            self._auth_methods,
            session=session_obj,
        )

        # Решения обработчика обязаны попасть на диск. Раньше сохранения не было
        # вовсе, и `session/load` молча терял актуальный `cwd`, отмену незавершённых
        # вызовов и ответы модели на отложенный хвост батча (P2-42, измерено).
        succeeded = outcome.response is not None and outcome.response.error is None
        if session_obj is not None and succeeded:
            await self._repository.save_session(session_obj)
            # info, а не debug: это запись на диск на границе транзакции, и по логу
            # должно быть видно, что решения обработчика сохранены. На прогоне
            # 2026-07-30 событие было debug — и прогон не смог подтвердить правку.
            logger.info(
                "session_saved_after_load",
                session_id=session_id,
                cwd=session_obj.config.cwd,
            )

        return outcome

"""AuthenticateCommandHandler - обработчик метода authenticate.

Обрабатывает аутентификацию клиента с использованием
зарегистрированных методов аутентификации.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

from ...messages import ACPMessage
from ..handlers import auth
from ..state import ProtocolOutcome

logger = structlog.get_logger()


class AuthenticateCommandHandler:
    """Обработчик метода authenticate.

    Отвечает за:
    - Проверку credentials клиента
    - Валидацию метода аутентификации
    - Обновление состояния аутентификации

    Attributes:
        method_name: Имя обрабатываемого метода.
    """

    method_name = "authenticate"

    def __init__(
        self,
        require_auth: bool,
        auth_api_key: str | None,
        auth_methods: list[dict[str, Any]],
        on_authenticated: Callable[[bool], None] | None = None,
    ) -> None:
        """Инициализирует обработчик.

        Args:
            require_auth: Требуется ли аутентификация.
            auth_api_key: API ключ для аутентификации.
            auth_methods: Список поддерживаемых методов аутентификации.
            on_authenticated: Callback, вызываемый после аутентификации
                с результатом (True/False).
        """
        self._require_auth = require_auth
        self._auth_api_key = auth_api_key
        self._auth_methods = auth_methods
        self._on_authenticated = on_authenticated

    async def handle(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает метод authenticate.

        Args:
            message: Входящее JSON-RPC сообщение.

        Returns:
            ProtocolOutcome с результатом аутентификации.
        """
        params = message.params or {}
        response, authenticated = auth.authenticate(
            message.id,
            params,
            self._require_auth,
            self._auth_api_key,
            self._auth_methods,
        )

        if self._on_authenticated:
            self._on_authenticated(authenticated)

        logger.debug(
            "authenticate_completed",
            authenticated=authenticated,
            method_id=params.get("methodId"),
        )

        return ProtocolOutcome(response=response)

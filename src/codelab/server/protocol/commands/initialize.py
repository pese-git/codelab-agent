"""InitializeCommandHandler - обработчик метода initialize.

Обрабатывает handshake с клиентом: согласование версии протокола,
обмен capabilities, объявление методов аутентификации.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

from codelab.server.storage.document import ClientRuntimeCapabilities

from ...messages import ACPMessage
from ..handlers import auth
from ..state import ProtocolOutcome

logger = structlog.get_logger()


class InitializeCommandHandler:
    """Обработчик метода initialize.

    Отвечает за:
    - Согласование версии протокола
    - Обмен capabilities между клиентом и агентом
    - Объявление поддерживаемых методов аутентификации
    - Сохранение runtime-возможностей клиента

    Attributes:
        method_name: Имя обрабатываемого метода.
    """

    method_name = "initialize"

    def __init__(
        self,
        supported_protocol_versions: tuple[int, ...],
        require_auth: bool,
        auth_methods: list[dict[str, Any]],
        mcp_http_enabled: bool = True,
        mcp_sse_enabled: bool = True,
        on_capabilities_negotiated: Callable[[ClientRuntimeCapabilities], None] | None = None,
    ) -> None:
        """Инициализирует обработчик.

        Args:
            supported_protocol_versions: Поддерживаемые версии протокола.
            require_auth: Требуется ли аутентификация.
            auth_methods: Список поддерживаемых методов аутентификации.
            mcp_http_enabled: Поддерживается ли MCP HTTP transport.
            mcp_sse_enabled: Поддерживается ли MCP SSE transport.
            on_capabilities_negotiated: Callback, вызываемый после согласования
                capabilities клиента.
        """
        self._supported_protocol_versions = supported_protocol_versions
        self._require_auth = require_auth
        self._auth_methods = auth_methods
        self._mcp_http_enabled = mcp_http_enabled
        self._mcp_sse_enabled = mcp_sse_enabled
        self._on_capabilities_negotiated = on_capabilities_negotiated

    async def handle(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает метод initialize.

        Args:
            message: Входящее JSON-RPC сообщение.

        Returns:
            ProtocolOutcome с ответом на initialize.
        """
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

        # Сохраняем согласованные runtime-возможности клиента
        client_capabilities = params.get("clientCapabilities")
        if isinstance(client_capabilities, dict):
            parsed_capabilities = auth.parse_client_runtime_capabilities(client_capabilities)
            # Согласование логируется на `info`: это feature-gate, решающий, существуют
            # ли для модели `fs/*` и `terminal/*` вообще (`ToolFilter`). Без записи смена
            # набора у клиента выглядела бы как «модель перестала пользоваться
            # инструментами», и разбор живого прогона не отличил бы одно от другого —
            # за прогон на 800 строк про capabilities не было ни одной записи.
            logger.info(
                "client_capabilities_negotiated",
                fs_read=parsed_capabilities.fs_read,
                fs_write=parsed_capabilities.fs_write,
                terminal=parsed_capabilities.terminal,
            )
            if self._on_capabilities_negotiated:
                self._on_capabilities_negotiated(parsed_capabilities)
        else:
            # Клиент не прислал `clientCapabilities` — tool-runtime недоступен целиком.
            # Молчать здесь нельзя: наружу это выглядит как «инструменты не работают».
            logger.warning("client_capabilities_absent")

        logger.debug(
            "initialize_handshake_completed",
            protocol_version=response.result.get("protocolVersion") if response.result else None,
        )

        return ProtocolOutcome(response=response)

"""Тесты для PermissionResponder."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.client.application.permission_handler import (
    CancelledPermissionOutcome,
    SelectedPermissionOutcome,
)
from codelab.client.infrastructure.services.acp_transport import PermissionResponder

_PERMISSION_MESSAGE: dict[str, Any] = {
    "jsonrpc": "2.0",
    "id": "perm-1",
    "method": "session/request_permission",
    "params": {
        "sessionId": "sess-1",
        "toolCall": {"toolCallId": "tc-1", "kind": "read", "title": "Read file"},
        "options": [{"optionId": "allow_once", "kind": "allow_once", "name": "Allow once"}],
    },
}


class TestSetters:
    """Установка handler/callback."""

    def test_set_callback_stores_and_logs(self) -> None:
        responder = PermissionResponder(send=AsyncMock())
        responder._logger = MagicMock()  # noqa: SLF001

        def my_callback(request_id: str | int, tool_call: object, options: list[object]) -> None:
            pass

        responder.set_callback(my_callback)

        assert responder.callback is my_callback
        responder._logger.info.assert_called_once()  # noqa: SLF001
        call_args = responder._logger.info.call_args  # noqa: SLF001
        assert "permission_callback_set" in call_args[0]
        assert call_args[1]["callback_name"] == "my_callback"

    def test_set_handler_stores(self) -> None:
        handler = AsyncMock()
        responder = PermissionResponder(send=AsyncMock())
        responder.set_handler(handler)
        assert responder.handler is handler


class TestHandle:
    """Обработка session/request_permission."""

    @pytest.mark.asyncio
    async def test_without_handler_sends_cancel(self) -> None:
        """Без handler отправляется cancel response, чтобы сервер не завис."""
        send = AsyncMock()
        responder = PermissionResponder(send=send)

        await responder.handle(_PERMISSION_MESSAGE)

        send.assert_awaited_once()
        payload = send.call_args[0][0]
        assert payload["id"] == "perm-1"
        assert payload["result"]["outcome"] == "cancelled"

    @pytest.mark.asyncio
    async def test_callback_passed_to_handler(self) -> None:
        """Установленный callback передаётся в handler.handle_request."""
        handler = AsyncMock()
        handler.handle_request.return_value = CancelledPermissionOutcome(outcome="cancelled")
        responder = PermissionResponder(send=AsyncMock(), handler=handler)
        callback = MagicMock()
        responder.set_callback(callback)

        await responder.handle(_PERMISSION_MESSAGE)

        handler.handle_request.assert_awaited_once()
        assert handler.handle_request.call_args[1]["callback"] is callback

    @pytest.mark.asyncio
    async def test_without_callback_passes_none(self) -> None:
        """Если callback не установлен, handler получает None."""
        handler = AsyncMock()
        handler.handle_request.return_value = SelectedPermissionOutcome(
            outcome="selected", optionId="allow_once"
        )
        responder = PermissionResponder(send=AsyncMock(), handler=handler)

        await responder.handle(_PERMISSION_MESSAGE)

        handler.handle_request.assert_awaited_once()
        assert handler.handle_request.call_args[1]["callback"] is None

    @pytest.mark.asyncio
    async def test_handler_exception_sends_error(self) -> None:
        """Исключение в handler приводит к отправке error response."""
        send = AsyncMock()
        handler = AsyncMock()
        handler.handle_request = AsyncMock(side_effect=ValueError("bad"))
        responder = PermissionResponder(send=send, handler=handler)

        await responder.handle(_PERMISSION_MESSAGE)

        send.assert_awaited_once()
        payload = send.call_args[0][0]
        assert payload["error"]["code"] == -32603

    @pytest.mark.asyncio
    async def test_send_error_is_logged(self) -> None:
        """Ошибка отправки error response логируется, а не роняет обработчик."""
        handler = AsyncMock()
        handler.handle_request = AsyncMock(side_effect=ValueError("bad"))
        responder = PermissionResponder(
            send=AsyncMock(side_effect=ConnectionError("send fail")),
            handler=handler,
        )
        responder._logger = MagicMock()  # noqa: SLF001

        await responder.handle(_PERMISSION_MESSAGE)

        error_events = [
            call.args[0] for call in responder._logger.error.call_args_list if call.args
        ]
        assert "failed_to_send_error_response" in error_events

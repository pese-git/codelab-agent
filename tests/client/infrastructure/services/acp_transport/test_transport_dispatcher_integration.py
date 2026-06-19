"""Тесты для интеграции ClientRpcDispatcher с ACPTransportService."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from codelab.client.infrastructure.services.acp_transport.client_rpc_dispatcher import (
    ClientRpcDispatcher,
)
from codelab.client.infrastructure.services.acp_transport_service import (
    ACPTransportService,
)
from codelab.client.infrastructure.services.routing_queues import RoutingQueues


class MockRpcHandler:
    """Mock RPC handler for testing."""

    def __init__(self, method: str, result: dict[str, Any] | None = None) -> None:
        self._method = method
        self._result = result or {}
        self.handle_calls: list[tuple[str | int, dict[str, Any]]] = []

    def can_handle(self, method: str) -> bool:
        return method == self._method

    async def handle(
        self, rpc_id: str | int, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        self.handle_calls.append((rpc_id, params))
        return self._result


class TestACPTransportServiceWithDispatcher:
    """Тесты интеграции ACPTransportService с ClientRpcDispatcher."""

    @pytest.fixture
    def mock_transport(self) -> AsyncMock:
        transport = AsyncMock()
        transport.is_connected.return_value = True
        transport.send_str = AsyncMock()
        return transport

    @pytest.fixture
    def mock_handler(self) -> MockRpcHandler:
        return MockRpcHandler("fs/read_text_file", {"content": "file content"})

    @pytest.fixture
    def dispatcher(self, mock_handler: MockRpcHandler) -> ClientRpcDispatcher:
        return ClientRpcDispatcher([mock_handler])

    @pytest.fixture
    def service_with_dispatcher(
        self, mock_transport: AsyncMock, dispatcher: ClientRpcDispatcher
    ) -> ACPTransportService:
        service = ACPTransportService(mock_transport, rpc_dispatcher=dispatcher)
        return service

    @pytest.fixture
    def service_without_dispatcher(
        self, mock_transport: AsyncMock
    ) -> ACPTransportService:
        return ACPTransportService(mock_transport)

    def test_constructor_accepts_dispatcher(
        self, mock_transport: AsyncMock, dispatcher: ClientRpcDispatcher
    ) -> None:
        service = ACPTransportService(mock_transport, rpc_dispatcher=dispatcher)
        assert service._rpc_dispatcher is dispatcher

    def test_constructor_works_without_dispatcher(
        self, mock_transport: AsyncMock
    ) -> None:
        service = ACPTransportService(mock_transport)
        assert service._rpc_dispatcher is None

    async def test_handle_notification_uses_dispatcher(
        self,
        service_with_dispatcher: ACPTransportService,
        mock_handler: MockRpcHandler,
        mock_transport: AsyncMock,
    ) -> None:
        service_with_dispatcher._queues = RoutingQueues()

        notification_data = {
            "jsonrpc": "2.0",
            "id": "rpc-1",
            "method": "fs/read_text_file",
            "params": {"path": "test.txt"},
        }

        await service_with_dispatcher._handle_notification_or_client_rpc(
            method="session/prompt",
            request_id="req-1",
            notification_data=notification_data,
            on_update=None,
            on_fs_read=None,
            on_fs_write=None,
            on_terminal_create=None,
            on_terminal_output=None,
            on_terminal_wait=None,
            on_terminal_release=None,
            on_terminal_kill=None,
        )

        assert len(mock_handler.handle_calls) == 1
        assert mock_handler.handle_calls[0] == ("rpc-1", {"path": "test.txt"})
        mock_transport.send_str.assert_called_once()

    async def test_handle_dispatcher_error_response(
        self,
        mock_transport: AsyncMock,
    ) -> None:
        error_result = {"error": {"code": -32602, "message": "Missing path"}}
        error_handler = MockRpcHandler("fs/read_text_file", error_result)
        dispatcher = ClientRpcDispatcher([error_handler])
        service = ACPTransportService(mock_transport, rpc_dispatcher=dispatcher)
        service._queues = RoutingQueues()

        notification_data = {
            "jsonrpc": "2.0",
            "id": "rpc-1",
            "method": "fs/read_text_file",
            "params": {},
        }

        await service._handle_notification_or_client_rpc(
            method="session/prompt",
            request_id="req-1",
            notification_data=notification_data,
            on_update=None,
            on_fs_read=None,
            on_fs_write=None,
            on_terminal_create=None,
            on_terminal_output=None,
            on_terminal_wait=None,
            on_terminal_release=None,
            on_terminal_kill=None,
        )

        mock_transport.send_str.assert_called_once()
        sent_data = mock_transport.send_str.call_args[0][0]
        import json
        parsed = json.loads(sent_data)
        assert "error" in parsed
        assert parsed["error"]["code"] == -32602

    async def test_handle_without_dispatcher_uses_callbacks(
        self,
        service_without_dispatcher: ACPTransportService,
        mock_transport: AsyncMock,
    ) -> None:
        service_without_dispatcher._queues = RoutingQueues()
        callback_called = False

        async def on_fs_read(path: str) -> str:
            nonlocal callback_called
            callback_called = True
            return "callback content"

        notification_data = {
            "jsonrpc": "2.0",
            "id": "rpc-1",
            "method": "fs/read_text_file",
            "params": {"path": "test.txt"},
        }

        await service_without_dispatcher._handle_notification_or_client_rpc(
            method="session/prompt",
            request_id="req-1",
            notification_data=notification_data,
            on_update=None,
            on_fs_read=on_fs_read,
            on_fs_write=None,
            on_terminal_create=None,
            on_terminal_output=None,
            on_terminal_wait=None,
            on_terminal_release=None,
            on_terminal_kill=None,
        )

        assert callback_called is True
        mock_transport.send_str.assert_called_once()

    async def test_dispatcher_session_update_still_uses_callback(
        self,
        service_with_dispatcher: ACPTransportService,
        mock_transport: AsyncMock,
    ) -> None:
        service_with_dispatcher._queues = RoutingQueues()
        update_received = False

        def on_update(data: dict[str, Any]) -> None:
            nonlocal update_received
            update_received = True

        notification_data = {
            "jsonrpc": "2.0",
            "id": "notif-1",
            "method": "session/update",
            "params": {"update": {"sessionUpdate": "agent_message_chunk"}},
        }

        await service_with_dispatcher._handle_notification_or_client_rpc(
            method="session/prompt",
            request_id="req-1",
            notification_data=notification_data,
            on_update=on_update,
            on_fs_read=None,
            on_fs_write=None,
            on_terminal_create=None,
            on_terminal_output=None,
            on_terminal_wait=None,
            on_terminal_release=None,
            on_terminal_kill=None,
        )

        assert update_received is True

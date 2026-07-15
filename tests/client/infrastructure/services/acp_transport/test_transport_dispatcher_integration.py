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
from codelab.client.infrastructure.transport import WebSocketTransport


class MockRpcHandler:
    """Mock RPC handler for testing."""

    def __init__(self, method: str, result: dict[str, Any] | None = None) -> None:
        self._method = method
        self._result = result or {}
        self.handle_calls: list[tuple[str | int, dict[str, Any]]] = []

    def can_handle(self, method: str) -> bool:
        return method == self._method

    async def handle(self, rpc_id: str | int, params: dict[str, Any]) -> dict[str, Any] | None:
        self.handle_calls.append((rpc_id, params))
        return self._result


class TestACPTransportServiceWithDispatcher:
    """Тесты интеграции ACPTransportService с ClientRpcDispatcher."""

    @pytest.fixture
    def mock_transport(self) -> AsyncMock:
        transport = AsyncMock(spec=WebSocketTransport)
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
    def service_without_dispatcher(self, mock_transport: AsyncMock) -> ACPTransportService:
        return ACPTransportService(mock_transport)

    def test_constructor_accepts_dispatcher(
        self, mock_transport: AsyncMock, dispatcher: ClientRpcDispatcher
    ) -> None:
        service = ACPTransportService(mock_transport, rpc_dispatcher=dispatcher)
        assert service._rpc_dispatcher is dispatcher

    def test_constructor_works_without_dispatcher(self, mock_transport: AsyncMock) -> None:
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

        await service_with_dispatcher._coordinator._handle_notification_or_client_rpc(
            method="session/prompt",
            request_id="req-1",
            notification_data=notification_data,
            on_update=None,
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

        await service._coordinator._handle_notification_or_client_rpc(
            method="session/prompt",
            request_id="req-1",
            notification_data=notification_data,
            on_update=None,
        )

        mock_transport.send_str.assert_called_once()
        sent_data = mock_transport.send_str.call_args[0][0]
        import json

        parsed = json.loads(sent_data)
        assert "error" in parsed
        assert parsed["error"]["code"] == -32602

    async def test_handle_without_dispatcher_sends_empty_response(
        self,
        service_without_dispatcher: ACPTransportService,
        mock_transport: AsyncMock,
    ) -> None:
        """Без dispatcher client-RPC получает пустой ответ (сервер не зависает)."""
        service_without_dispatcher._queues = RoutingQueues()

        notification_data = {
            "jsonrpc": "2.0",
            "id": "rpc-1",
            "method": "fs/read_text_file",
            "params": {"path": "test.txt"},
        }

        await service_without_dispatcher._coordinator._handle_notification_or_client_rpc(
            method="session/prompt",
            request_id="req-1",
            notification_data=notification_data,
            on_update=None,
        )

        mock_transport.send_str.assert_called_once()
        import json

        parsed = json.loads(mock_transport.send_str.call_args[0][0])
        assert parsed["id"] == "rpc-1"
        assert parsed["result"] == {}

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

        await service_with_dispatcher._coordinator._handle_notification_or_client_rpc(
            method="session/prompt",
            request_id="req-1",
            notification_data=notification_data,
            on_update=on_update,
        )

        assert update_received is True

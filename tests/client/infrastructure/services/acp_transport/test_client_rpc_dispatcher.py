"""Тесты для ClientRpcDispatcher."""

from __future__ import annotations

from typing import Any

import pytest

from codelab.client.infrastructure.services.acp_transport.client_rpc_dispatcher import (
    ClientRpcDispatcher,
)


class MockRpcHandler:
    """Mock реализация RpcHandler для тестов."""

    def __init__(
        self,
        method: str,
        result: dict[str, Any] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._method = method
        self._result = result or {}
        self._raises = raises
        self.handle_calls: list[tuple[str | int, dict[str, Any]]] = []

    def can_handle(self, method: str) -> bool:
        return method == self._method

    async def handle(
        self, rpc_id: str | int, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        self.handle_calls.append((rpc_id, params))
        if self._raises is not None:
            raise self._raises
        return self._result


class TestClientRpcDispatcher:
    """Тесты для ClientRpcDispatcher."""

    @pytest.fixture
    def mock_handler(self) -> MockRpcHandler:
        return MockRpcHandler("test/method", {"result": "success"})

    @pytest.fixture
    def dispatcher(self, mock_handler: MockRpcHandler) -> ClientRpcDispatcher:
        return ClientRpcDispatcher([mock_handler])

    def test_dispatcher_accepts_handler_list(self, mock_handler: MockRpcHandler) -> None:
        dispatcher = ClientRpcDispatcher([mock_handler])
        assert dispatcher._handlers == [mock_handler]

    def test_dispatcher_accepts_empty_list(self) -> None:
        dispatcher = ClientRpcDispatcher([])
        assert dispatcher._handlers == []

    async def test_dispatch_finds_handler(self, dispatcher: ClientRpcDispatcher) -> None:
        result = await dispatcher.dispatch("test/method", "rpc-1", {"key": "value"})

        assert result == {"result": "success"}

    async def test_dispatch_returns_empty_dict_for_none_result(self) -> None:
        handler = MockRpcHandler("test/method", result=None)
        dispatcher = ClientRpcDispatcher([handler])

        result = await dispatcher.dispatch("test/method", "rpc-1", {})

        assert result == {}

    async def test_dispatch_unknown_method(self, dispatcher: ClientRpcDispatcher) -> None:
        result = await dispatcher.dispatch("unknown/method", "rpc-1", {})

        assert result == {"error": {"code": -32601, "message": "Method not found: unknown/method"}}

    async def test_dispatch_handler_exception(self) -> None:
        handler = MockRpcHandler("test/method", raises=ValueError("Handler error"))
        dispatcher = ClientRpcDispatcher([handler])

        result = await dispatcher.dispatch("test/method", "rpc-1", {})

        assert result == {"error": {"code": -32603, "message": "Handler error"}}

    async def test_dispatch_handler_returns_error(self) -> None:
        error_result = {"error": {"code": -32602, "message": "Invalid params"}}
        handler = MockRpcHandler("test/method", result=error_result)
        dispatcher = ClientRpcDispatcher([handler])

        result = await dispatcher.dispatch("test/method", "rpc-1", {})

        assert result == error_result

    async def test_dispatch_first_matching_handler_wins(self) -> None:
        handler1 = MockRpcHandler("test/method", {"handler": "first"})
        handler2 = MockRpcHandler("test/method", {"handler": "second"})
        dispatcher = ClientRpcDispatcher([handler1, handler2])

        result = await dispatcher.dispatch("test/method", "rpc-1", {})

        assert result == {"handler": "first"}
        assert len(handler1.handle_calls) == 1
        assert len(handler2.handle_calls) == 0

    async def test_dispatch_passes_correct_params(
        self, dispatcher: ClientRpcDispatcher, mock_handler: MockRpcHandler
    ) -> None:
        params = {"path": "test.txt", "content": "hello"}

        await dispatcher.dispatch("test/method", "rpc-42", params)

        assert mock_handler.handle_calls == [("rpc-42", params)]

    async def test_dispatch_with_multiple_handlers(self) -> None:
        handler1 = MockRpcHandler("method/one", {"handler": "one"})
        handler2 = MockRpcHandler("method/two", {"handler": "two"})
        handler3 = MockRpcHandler("method/three", {"handler": "three"})
        dispatcher = ClientRpcDispatcher([handler1, handler2, handler3])

        result = await dispatcher.dispatch("method/two", "rpc-1", {})

        assert result == {"handler": "two"}
        assert len(handler2.handle_calls) == 1

    async def test_dispatch_empty_handlers_list(self) -> None:
        dispatcher = ClientRpcDispatcher([])

        result = await dispatcher.dispatch("any/method", "rpc-1", {})

        assert result == {"error": {"code": -32601, "message": "Method not found: any/method"}}

    async def test_dispatch_with_string_rpc_id(
        self, dispatcher: ClientRpcDispatcher, mock_handler: MockRpcHandler
    ) -> None:
        result = await dispatcher.dispatch("test/method", "string-id-123", {})

        assert result == {"result": "success"}
        assert mock_handler.handle_calls[0][0] == "string-id-123"

    async def test_dispatch_with_int_rpc_id(
        self, dispatcher: ClientRpcDispatcher, mock_handler: MockRpcHandler
    ) -> None:
        result = await dispatcher.dispatch("test/method", 42, {})

        assert result == {"result": "success"}
        assert mock_handler.handle_calls[0][0] == 42

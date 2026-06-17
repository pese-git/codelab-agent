"""Тесты для непокрытых методов MCPClient.

Покрывают:
- Вызов инструмента (call_tool) и ошибки транспорта
- Ошибки инициализации (initialize)
- Ошибки подключения (connect) и повторное подключение
- Асинхронный контекстный менеджер (__aenter__/__aexit__)
- Обработку запроса roots/list от сервера
- Очистку capabilities и tools при disconnect
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codelab.server.mcp.client import (
    MCPClient,
    MCPClientError,
    MCPClientState,
    MCPInitializeError,
    MCPToolCallError,
)
from codelab.server.mcp.models import MCPCapabilities, MCPRoot, MCPServerConfig
from codelab.server.mcp.transport import HttpTransportError, StdioTransportError


class TestMCPClientCallTool:
    """Тесты метода call_tool."""

    @pytest.fixture
    def ready_client(self) -> MCPClient:
        """Создаёт готовый к работе MCPClient с mock-транспортом."""
        config = MCPServerConfig(name="test", type="stdio", command="mcp-server")
        client = MCPClient(config)
        client._state = MCPClientState.READY
        client._transport = AsyncMock()
        client._capabilities = MCPCapabilities(tools={})
        return client

    @pytest.mark.asyncio
    async def test_call_tool_success(self, ready_client: MCPClient) -> None:
        """Успешный вызов инструмента возвращает распарсенный результат."""
        transport = ready_client._transport
        transport.send_request = AsyncMock(
            return_value={
                "content": [{"type": "text", "text": "done"}],
                "isError": False,
            }
        )

        result = await ready_client.call_tool("test_tool", {"arg": 1})

        assert result.is_error is False
        assert result.get_text_content() == "done"
        transport.send_request.assert_called_once()
        call_kwargs = transport.send_request.call_args.kwargs
        assert call_kwargs["method"] == "tools/call"
        assert call_kwargs["timeout"] == 60.0

    @pytest.mark.asyncio
    async def test_call_tool_is_error_logs_warning(
        self, ready_client: MCPClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """При is_error=True результат возвращается и логируется предупреждение."""
        transport = ready_client._transport
        transport.send_request = AsyncMock(
            return_value={
                "content": [{"type": "text", "text": "boom"}],
                "isError": True,
            }
        )

        with caplog.at_level(logging.WARNING):
            result = await ready_client.call_tool("bad_tool")

        assert result.is_error is True
        assert result.get_text_content() == "boom"
        assert "bad_tool returned error" in caplog.text

    @pytest.mark.asyncio
    async def test_call_tool_not_ready(self, ready_client: MCPClient) -> None:
        """call_tool выбрасывает MCPClientError если клиент не READY."""
        ready_client._state = MCPClientState.CREATED

        with pytest.raises(MCPClientError, match="Cannot call tool in state"):
            await ready_client.call_tool("test_tool")

    @pytest.mark.asyncio
    async def test_call_tool_no_transport(self, ready_client: MCPClient) -> None:
        """call_tool выбрасывает MCPClientError если нет транспорта."""
        ready_client._transport = None

        with pytest.raises(MCPClientError, match="Transport not available"):
            await ready_client.call_tool("test_tool")

    @pytest.mark.asyncio
    async def test_call_tool_stdio_transport_error(
        self, ready_client: MCPClient
    ) -> None:
        """StdioTransportError при вызове инструмента превращается в MCPToolCallError."""
        ready_client._transport.send_request = AsyncMock(
            side_effect=StdioTransportError("lost")
        )

        with pytest.raises(MCPToolCallError, match="Tool call test_tool failed"):
            await ready_client.call_tool("test_tool")

    @pytest.mark.asyncio
    async def test_call_tool_http_transport_error(
        self, ready_client: MCPClient
    ) -> None:
        """HttpTransportError при вызове инструмента превращается в MCPToolCallError."""
        ready_client._transport.send_request = AsyncMock(
            side_effect=HttpTransportError("timeout")
        )

        with pytest.raises(MCPToolCallError, match="Tool call test_tool failed"):
            await ready_client.call_tool("test_tool")


class TestMCPClientInitializeErrors:
    """Тесты ошибочных веток метода initialize."""

    @pytest.fixture
    def connecting_client(self) -> MCPClient:
        """Создаёт MCPClient в состоянии CONNECTING с mock-транспортом."""
        config = MCPServerConfig(name="test", type="stdio", command="mcp-server")
        client = MCPClient(config)
        client._state = MCPClientState.CONNECTING
        client._transport = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_initialize_not_connecting(self) -> None:
        """initialize выбрасывает MCPClientError если состояние не CONNECTING."""
        config = MCPServerConfig(name="test", type="stdio", command="mcp-server")
        client = MCPClient(config)
        client._state = MCPClientState.READY

        with pytest.raises(MCPClientError, match="Cannot initialize in state"):
            await client.initialize()

    @pytest.mark.asyncio
    async def test_initialize_no_transport(self) -> None:
        """initialize выбрасывает MCPClientError если транспорт не создан."""
        config = MCPServerConfig(name="test", type="stdio", command="mcp-server")
        client = MCPClient(config)
        client._state = MCPClientState.CONNECTING
        client._transport = None

        with pytest.raises(MCPClientError, match="Transport not initialized"):
            await client.initialize()

    @pytest.mark.asyncio
    async def test_initialize_transport_error_sets_failed(
        self, connecting_client: MCPClient
    ) -> None:
        """Ошибка транспорта при initialize переводит клиент в состояние FAILED."""
        connecting_client._transport.send_request = AsyncMock(
            side_effect=StdioTransportError("broken pipe")
        )

        with pytest.raises(MCPInitializeError, match="Initialize failed for test"):
            await connecting_client.initialize()

        assert connecting_client._state == MCPClientState.FAILED

    @pytest.mark.asyncio
    async def test_initialize_generic_exception_sets_failed(
        self, connecting_client: MCPClient
    ) -> None:
        """Общее исключение при initialize переводит клиент в состояние FAILED."""
        connecting_client._transport.send_request = AsyncMock(
            side_effect=ValueError("bad response")
        )

        with pytest.raises(MCPInitializeError, match="Initialize error for test"):
            await connecting_client.initialize()

        assert connecting_client._state == MCPClientState.FAILED


class TestMCPClientConnectErrors:
    """Тесты ошибочных веток метода connect."""

    @pytest.mark.asyncio
    async def test_connect_wrong_state_ready(self) -> None:
        """connect выбрасывает MCPClientError если клиент уже READY."""
        config = MCPServerConfig(name="test", type="stdio", command="mcp-server")
        client = MCPClient(config)
        client._state = MCPClientState.READY

        with pytest.raises(MCPClientError, match="Cannot connect in state"):
            await client.connect()

    @pytest.mark.asyncio
    async def test_connect_reconnect_from_closed(self) -> None:
        """connect позволяет повторно подключиться из состояния CLOSED."""
        config = MCPServerConfig(name="test", type="stdio", command="mcp-server")
        client = MCPClient(config)
        client._state = MCPClientState.CLOSED

        with patch("codelab.server.mcp.client.TransportFactory") as mock_factory:
            mock_transport = AsyncMock()
            mock_factory.create.return_value = mock_transport

            await client.connect()

            mock_factory.create.assert_called_once_with(config)
            mock_transport.connect.assert_called_once()
            assert client._state == MCPClientState.CONNECTING

    @pytest.mark.asyncio
    async def test_connect_transport_error_sets_failed(self) -> None:
        """Ошибка транспорта при connect переводит клиент в состояние FAILED."""
        config = MCPServerConfig(name="test", type="stdio", command="mcp-server")
        client = MCPClient(config)

        with patch("codelab.server.mcp.client.TransportFactory") as mock_factory:
            mock_factory.create = MagicMock(
                side_effect=StdioTransportError("spawn failed")
            )

            with pytest.raises(
                MCPClientError, match="Failed to connect to MCP server"
            ):
                await client.connect()

            assert client._state == MCPClientState.FAILED


class TestMCPClientAsyncContextManager:
    """Тесты асинхронного контекстного менеджера."""

    @pytest.mark.asyncio
    async def test_aenter_calls_connect_and_initialize(self) -> None:
        """__aenter__ вызывает connect и initialize, переводя клиент в READY."""
        config = MCPServerConfig(name="test", type="stdio", command="mcp-server")
        client = MCPClient(config)

        async def fake_connect() -> None:
            client._state = MCPClientState.CONNECTING

        async def fake_initialize() -> MCPCapabilities:
            client._state = MCPClientState.READY
            return MCPCapabilities(tools={})

        with patch.object(client, "connect", side_effect=fake_connect) as mock_connect:
            with patch.object(
                client, "initialize", side_effect=fake_initialize
            ) as mock_initialize:
                async with client as entered:
                    assert entered is client
                    assert client._state == MCPClientState.READY

        mock_connect.assert_called_once()
        mock_initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_aexit_calls_disconnect(self) -> None:
        """__aexit__ вызывает disconnect при выходе из контекста."""
        config = MCPServerConfig(name="test", type="stdio", command="mcp-server")
        client = MCPClient(config)

        with patch.object(client, "connect") as mock_connect:
            with patch.object(client, "initialize") as mock_initialize:
                with patch.object(client, "disconnect") as mock_disconnect:
                    async with client:
                        pass

        mock_disconnect.assert_called_once()
        mock_connect.assert_called_once()
        mock_initialize.assert_called_once()


class TestMCPClientRootsListRequest:
    """Тесты обработки входящего запроса roots/list от сервера."""

    @pytest.fixture
    def client(self) -> MCPClient:
        """Создаёт MCPClient с тестовой конфигурацией."""
        config = MCPServerConfig(name="test", type="stdio", command="mcp-server")
        return MCPClient(config)

    @pytest.mark.asyncio
    async def test_handle_roots_list_request_returns_roots(
        self, client: MCPClient
    ) -> None:
        """Запрос roots/list возвращает установленные roots."""
        client._roots = [
            MCPRoot(uri="file:///project", name="Project"),
            MCPRoot(uri="file:///tmp"),
        ]

        result = await client._handle_roots_list_request({})

        assert result == {
            "roots": [
                {"uri": "file:///project", "name": "Project"},
                {"uri": "file:///tmp", "name": None},
            ]
        }

    @pytest.mark.asyncio
    async def test_handle_roots_list_request_empty(self, client: MCPClient) -> None:
        """Запрос roots/list возвращает пустой список если roots не заданы."""
        result = await client._handle_roots_list_request({})

        assert result == {"roots": []}


class TestMCPClientDisconnectCleanup:
    """Тесты очистки состояния при disconnect."""

    @pytest.mark.asyncio
    async def test_disconnect_clears_capabilities_and_tools(self) -> None:
        """disconnect сбрасывает capabilities и tools."""
        config = MCPServerConfig(name="test", type="stdio", command="mcp-server")
        client = MCPClient(config)
        client._state = MCPClientState.READY
        client._transport = AsyncMock()
        client._capabilities = MCPCapabilities(tools={})
        client._tools = [MagicMock()]

        await client.disconnect()

        assert client._state == MCPClientState.CLOSED
        assert client._capabilities is None
        assert client._tools == []
        assert client._transport is None

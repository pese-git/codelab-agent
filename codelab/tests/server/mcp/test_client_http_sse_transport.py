"""Тесты HTTP/SSE transport wiring в MCPClient.

Покрывают:
- MCPClient.connect() выбирает транспорт по config.type
- HTTP transport подключение
- SSE transport подключение
- Fallback на stdio при отсутствии url
- Ошибки при невалидном type
- mcpCapabilities через конфигурацию ACPProtocol
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codelab.server.mcp.client import MCPClient, MCPClientError, MCPClientState
from codelab.server.mcp.models import MCPServerConfig
from codelab.server.protocol.core import ACPProtocol
from codelab.server.protocol.handlers import auth
from codelab.shared.messages import ACPMessage


class TestMCPClientTransportSelection:
    """Тесты выбора транспорта в MCPClient.connect()."""

    @pytest.mark.asyncio
    async def test_stdio_transport_selected_for_stdio_type(self) -> None:
        """Stdio transport выбирается для type='stdio'."""
        config = MCPServerConfig(
            name="test-server",
            type="stdio",
            command="python",
            args=["-m", "test_server"],
        )
        client = MCPClient(config)

        with patch("codelab.server.mcp.client.StdioTransport") as mock_stdio:
            mock_transport = AsyncMock()
            mock_stdio.return_value = mock_transport

            await client.connect()

            mock_stdio.assert_called_once()
            mock_transport.start.assert_called_once()
            assert client._state == MCPClientState.CONNECTING

    @pytest.mark.asyncio
    async def test_http_transport_selected_for_http_type(self) -> None:
        """HTTP transport выбирается для type='http'."""
        config = MCPServerConfig(
            name="test-server",
            type="http",
            url="http://localhost:8080",
        )
        client = MCPClient(config)

        with patch("codelab.server.mcp.client.HttpTransport") as mock_http:
            mock_transport = AsyncMock()
            mock_http.return_value = mock_transport

            await client.connect()

            mock_http.assert_called_once_with(
                url="http://localhost:8080",
                headers=[],
            )
            mock_transport.connect.assert_called_once()
            assert client._state == MCPClientState.CONNECTING

    @pytest.mark.asyncio
    async def test_sse_transport_selected_for_sse_type(self) -> None:
        """SSE transport выбирается для type='sse'."""
        config = MCPServerConfig(
            name="test-server",
            type="sse",
            url="http://localhost:8080/sse",
        )
        client = MCPClient(config)

        with patch("codelab.server.mcp.client.SseTransport") as mock_sse:
            mock_transport = AsyncMock()
            mock_sse.return_value = mock_transport

            await client.connect()

            mock_sse.assert_called_once_with(
                url="http://localhost:8080/sse",
                headers=[],
            )
            mock_transport.connect.assert_called_once()
            assert client._state == MCPClientState.CONNECTING

    @pytest.mark.asyncio
    async def test_error_for_unsupported_type(self) -> None:
        """Ошибка для неподдерживаемого типа транспорта."""
        config = MCPServerConfig(
            name="test-server",
            type="http",
            url="http://localhost:8080",
        )
        # Обходим валидацию model_post_init
        config.type = "invalid"

        client = MCPClient(config)

        with pytest.raises(MCPClientError, match="Unsupported transport type"):
            await client.connect()

    @pytest.mark.asyncio
    async def test_http_transport_with_headers(self) -> None:
        """HTTP transport передаёт headers."""
        config = MCPServerConfig(
            name="test-server",
            type="http",
            url="http://localhost:8080",
            headers=[{"name": "Authorization", "value": "Bearer token"}],
        )
        client = MCPClient(config)

        with patch("codelab.server.mcp.client.HttpTransport") as mock_http:
            mock_transport = AsyncMock()
            mock_http.return_value = mock_transport

            await client.connect()

            mock_http.assert_called_once()
            call_kwargs = mock_http.call_args[1]
            assert call_kwargs["headers"] == [{"name": "Authorization", "value": "Bearer token"}]


class TestMCPClientDisconnect:
    """Тесты disconnect для разных транспортов."""

    @pytest.mark.asyncio
    async def test_stdio_disconnect_calls_close(self) -> None:
        """Stdio transport вызывает close() при disconnect."""
        from codelab.server.mcp.client import MCPClient, MCPClientState
        from codelab.server.mcp.models import MCPServerConfig

        config = MCPServerConfig(
            name="test-server",
            type="stdio",
            command="python",
            args=["-m", "test_server"],
        )
        client = MCPClient(config)

        # Создаём mock без метода disconnect (как у StdioTransport)
        mock_transport = MagicMock()
        mock_transport.close = AsyncMock()
        # Удаляем disconnect, чтобы hasattr вернул False
        del mock_transport.disconnect
        client._transport = mock_transport
        client._state = MCPClientState.READY

        await client.disconnect()

        mock_transport.close.assert_called_once()
        assert client._state == MCPClientState.CLOSED

    @pytest.mark.asyncio
    async def test_http_disconnect_calls_disconnect(self) -> None:
        """HTTP transport вызывает disconnect() при disconnect."""
        from codelab.server.mcp.transport import HttpTransport

        config = MCPServerConfig(
            name="test-server",
            type="http",
            url="http://localhost:8080",
        )
        client = MCPClient(config)

        with patch("codelab.server.mcp.client.HttpTransport") as mock_http:
            mock_transport = AsyncMock()
            mock_transport.__class__ = HttpTransport
            mock_http.return_value = mock_transport

            await client.connect()
            await client.disconnect()

            mock_transport.disconnect.assert_called_once()
            assert client._state == MCPClientState.CLOSED

    @pytest.mark.asyncio
    async def test_sse_disconnect_calls_disconnect(self) -> None:
        """SSE transport вызывает disconnect() при disconnect."""
        from codelab.server.mcp.transport import SseTransport

        config = MCPServerConfig(
            name="test-server",
            type="sse",
            url="http://localhost:8080/sse",
        )
        client = MCPClient(config)

        with patch("codelab.server.mcp.client.SseTransport") as mock_sse:
            mock_transport = AsyncMock()
            mock_transport.__class__ = SseTransport
            mock_sse.return_value = mock_transport

            await client.connect()
            await client.disconnect()

            mock_transport.disconnect.assert_called_once()
            assert client._state == MCPClientState.CLOSED


class TestMCPCapabilitiesConfig:
    """Тесты mcpCapabilities через конфигурацию ACPProtocol."""

    @pytest.mark.asyncio
    async def test_default_capabilities_enabled(self) -> None:
        """По умолчанию HTTP и SSE capabilities включены."""
        protocol = ACPProtocol()

        response = await protocol.handle(
            ACPMessage.request(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            )
        )

        assert response.response is not None
        result = response.response.result
        assert result is not None
        assert result["agentCapabilities"]["mcpCapabilities"]["http"] is True
        assert result["agentCapabilities"]["mcpCapabilities"]["sse"] is True

    @pytest.mark.asyncio
    async def test_http_capability_disabled(self) -> None:
        """HTTP capability можно отключить через конфигурацию."""
        protocol = ACPProtocol(mcp_http_enabled=False)

        response = await protocol.handle(
            ACPMessage.request(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            )
        )

        assert response.response is not None
        result = response.response.result
        assert result is not None
        assert result["agentCapabilities"]["mcpCapabilities"]["http"] is False
        assert result["agentCapabilities"]["mcpCapabilities"]["sse"] is True

    @pytest.mark.asyncio
    async def test_sse_capability_disabled(self) -> None:
        """SSE capability можно отключить через конфигурацию."""
        protocol = ACPProtocol(mcp_sse_enabled=False)

        response = await protocol.handle(
            ACPMessage.request(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            )
        )

        assert response.response is not None
        result = response.response.result
        assert result is not None
        assert result["agentCapabilities"]["mcpCapabilities"]["http"] is True
        assert result["agentCapabilities"]["mcpCapabilities"]["sse"] is False

    @pytest.mark.asyncio
    async def test_both_capabilities_disabled(self) -> None:
        """Оба capability можно отключить через конфигурацию."""
        protocol = ACPProtocol(mcp_http_enabled=False, mcp_sse_enabled=False)

        response = await protocol.handle(
            ACPMessage.request(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            )
        )

        assert response.response is not None
        result = response.response.result
        assert result is not None
        assert result["agentCapabilities"]["mcpCapabilities"]["http"] is False
        assert result["agentCapabilities"]["mcpCapabilities"]["sse"] is False


class TestAuthInitializeCapabilities:
    """Тесты auth.initialize() с mcp capabilities."""

    def test_auth_initialize_with_default_capabilities(self) -> None:
        """auth.initialize() возвращает capabilities=True по умолчанию."""
        response = auth.initialize(
            request_id="req_1",
            params={
                "protocolVersion": 1,
                "clientCapabilities": {},
            },
            supported_protocol_versions=(1,),
            require_auth=False,
            auth_methods=[],
        )

        assert response.result is not None
        assert response.result["agentCapabilities"]["mcpCapabilities"]["http"] is True
        assert response.result["agentCapabilities"]["mcpCapabilities"]["sse"] is True

    def test_auth_initialize_with_http_disabled(self) -> None:
        """auth.initialize() возвращает http=False при mcp_http_enabled=False."""
        response = auth.initialize(
            request_id="req_1",
            params={
                "protocolVersion": 1,
                "clientCapabilities": {},
            },
            supported_protocol_versions=(1,),
            require_auth=False,
            auth_methods=[],
            mcp_http_enabled=False,
        )

        assert response.result is not None
        assert response.result["agentCapabilities"]["mcpCapabilities"]["http"] is False
        assert response.result["agentCapabilities"]["mcpCapabilities"]["sse"] is True

    def test_auth_initialize_with_sse_disabled(self) -> None:
        """auth.initialize() возвращает sse=False при mcp_sse_enabled=False."""
        response = auth.initialize(
            request_id="req_1",
            params={
                "protocolVersion": 1,
                "clientCapabilities": {},
            },
            supported_protocol_versions=(1,),
            require_auth=False,
            auth_methods=[],
            mcp_sse_enabled=False,
        )

        assert response.result is not None
        assert response.result["agentCapabilities"]["mcpCapabilities"]["http"] is True
        assert response.result["agentCapabilities"]["mcpCapabilities"]["sse"] is False

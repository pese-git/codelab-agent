"""Тесты HTTP/SSE transport wiring в MCPClient.

Покрывают:
- MCPClient.connect() использует TransportFactory
- Единый интерфейс close() для всех транспортов
- mcpCapabilities через конфигурацию ACPProtocol
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from codelab.server.mcp.client import MCPClient, MCPClientError, MCPClientState
from codelab.server.mcp.models import MCPServerConfig
from codelab.server.protocol.core import ACPProtocol
from codelab.server.protocol.handlers import auth
from codelab.shared.messages import ACPMessage


class TestMCPClientTransportFactory:
    """Тесты использования TransportFactory в MCPClient.connect()."""

    @pytest.mark.asyncio
    async def test_connect_uses_transport_factory(self) -> None:
        """MCPClient.connect() использует TransportFactory для создания транспорта."""
        config = MCPServerConfig(
            name="test-server",
            type="stdio",
            command="python",
            args=["-m", "test_server"],
        )
        client = MCPClient(config)

        with patch("codelab.server.mcp.client.TransportFactory") as mock_factory:
            mock_transport = AsyncMock()
            mock_factory.create.return_value = mock_transport

            await client.connect()

            mock_factory.create.assert_called_once_with(config)
            mock_transport.connect.assert_called_once()
            assert client._state == MCPClientState.CONNECTING

    @pytest.mark.asyncio
    async def test_connect_http_transport(self) -> None:
        """HTTP транспорт создаётся через factory."""
        config = MCPServerConfig(
            name="test-server",
            type="http",
            url="http://localhost:8080",
        )
        client = MCPClient(config)

        with patch("codelab.server.mcp.client.TransportFactory") as mock_factory:
            mock_transport = AsyncMock()
            mock_factory.create.return_value = mock_transport

            await client.connect()

            mock_factory.create.assert_called_once_with(config)
            mock_transport.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_sse_transport(self) -> None:
        """SSE транспорт создаётся через factory."""
        config = MCPServerConfig(
            name="test-server",
            type="sse",
            url="http://localhost:8080/sse",
        )
        client = MCPClient(config)

        with patch("codelab.server.mcp.client.TransportFactory") as mock_factory:
            mock_transport = AsyncMock()
            mock_factory.create.return_value = mock_transport

            await client.connect()

            mock_factory.create.assert_called_once_with(config)
            mock_transport.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_factory_error_propagated(self) -> None:
        """Ошибки от factory пробрасываются как MCPClientError."""
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


class TestMCPClientDisconnect:
    """Тесты disconnect для всех транспортов."""

    @pytest.mark.asyncio
    async def test_disconnect_calls_close_on_transport(self) -> None:
        """disconnect() вызывает close() на транспорте."""
        config = MCPServerConfig(
            name="test-server",
            type="stdio",
            command="python",
            args=["-m", "test_server"],
        )
        client = MCPClient(config)

        # Создаём mock с единым интерфейсом close()
        mock_transport = AsyncMock()
        mock_transport.close = AsyncMock()
        client._transport = mock_transport
        client._state = MCPClientState.READY

        await client.disconnect()

        mock_transport.close.assert_called_once()
        assert client._state == MCPClientState.CLOSED

    @pytest.mark.asyncio
    async def test_disconnect_http_transport_calls_close(self) -> None:
        """HTTP transport вызывает close() при disconnect."""
        config = MCPServerConfig(
            name="test-server",
            type="http",
            url="http://localhost:8080",
        )
        client = MCPClient(config)

        with patch("codelab.server.mcp.client.TransportFactory") as mock_factory:
            mock_transport = AsyncMock()
            mock_factory.create.return_value = mock_transport

            await client.connect()
            await client.disconnect()

            mock_transport.close.assert_called_once()
            assert client._state == MCPClientState.CLOSED

    @pytest.mark.asyncio
    async def test_disconnect_sse_transport_calls_close(self) -> None:
        """SSE transport вызывает close() при disconnect."""
        config = MCPServerConfig(
            name="test-server",
            type="sse",
            url="http://localhost:8080/sse",
        )
        client = MCPClient(config)

        with patch("codelab.server.mcp.client.TransportFactory") as mock_factory:
            mock_transport = AsyncMock()
            mock_factory.create.return_value = mock_transport

            await client.connect()
            await client.disconnect()

            mock_transport.close.assert_called_once()
            assert client._state == MCPClientState.CLOSED

    @pytest.mark.asyncio
    async def test_disconnect_already_closed(self) -> None:
        """disconnect() не делает ничего если уже закрыт."""
        config = MCPServerConfig(
            name="test-server",
            type="stdio",
            command="python",
        )
        client = MCPClient(config)
        client._state = MCPClientState.CLOSED

        # Не должно вызвать ошибок
        await client.disconnect()

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

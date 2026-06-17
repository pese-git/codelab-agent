"""Тесты TransportFactory для создания MCP транспортов.

Покрывают:
- Создание StdioTransport из конфигурации
- Создание HttpTransport из конфигурации
- Создание SseTransport из конфигурации
- Обработка ошибок при невалидной конфигурации
- Единый интерфейс MCPTransport
"""

from __future__ import annotations

import pytest

from codelab.server.mcp.models import MCPServerConfig
from codelab.server.mcp.transport import HttpTransport, SseTransport, StdioTransport
from codelab.server.mcp.transport_factory import MCPTransport, TransportFactory


class TestTransportFactoryCreate:
    """Тесты метода create() фабрики транспортов."""

    def test_create_stdio_transport(self) -> None:
        """Создаёт StdioTransport для type='stdio'."""
        config = MCPServerConfig(
            name="test-server",
            type="stdio",
            command="python",
            args=["-m", "test_server"],
        )

        transport = TransportFactory.create(config)

        assert isinstance(transport, StdioTransport)
        assert isinstance(transport, MCPTransport)

    def test_create_stdio_transport_with_env(self) -> None:
        """StdioTransport получает env из конфигурации."""
        config = MCPServerConfig(
            name="test-server",
            type="stdio",
            command="node",
            args=["server.js"],
            env=[{"name": "NODE_ENV", "value": "production"}],
        )

        transport = TransportFactory.create(config)

        assert isinstance(transport, StdioTransport)
        # Проверяем, что env передан (через приватный атрибут)
        assert transport._env == {"NODE_ENV": "production"}

    def test_create_http_transport(self) -> None:
        """Создаёт HttpTransport для type='http'."""
        config = MCPServerConfig(
            name="test-server",
            type="http",
            url="http://localhost:8080",
        )

        transport = TransportFactory.create(config)

        assert isinstance(transport, HttpTransport)
        assert isinstance(transport, MCPTransport)

    def test_create_http_transport_with_headers(self) -> None:
        """HttpTransport получает headers из конфигурации."""
        config = MCPServerConfig(
            name="test-server",
            type="http",
            url="http://localhost:8080",
            headers=[{"name": "Authorization", "value": "Bearer token"}],
        )

        transport = TransportFactory.create(config)

        assert isinstance(transport, HttpTransport)
        # Headers конвертируются в dict формат
        assert transport._headers == {"Authorization": "Bearer token"}

    def test_create_sse_transport(self) -> None:
        """Создаёт SseTransport для type='sse'."""
        config = MCPServerConfig(
            name="test-server",
            type="sse",
            url="http://localhost:8080/sse",
        )

        transport = TransportFactory.create(config)

        assert isinstance(transport, SseTransport)
        assert isinstance(transport, MCPTransport)

    def test_create_sse_transport_with_headers(self) -> None:
        """SseTransport получает headers из конфигурации."""
        config = MCPServerConfig(
            name="test-server",
            type="sse",
            url="http://localhost:8080/sse",
            headers=[{"name": "X-Custom", "value": "value"}],
        )

        transport = TransportFactory.create(config)

        assert isinstance(transport, SseTransport)
        # Headers конвертируются в dict формат
        assert transport._headers == {"X-Custom": "value"}


class TestTransportFactoryErrors:
    """Тесты обработки ошибок в TransportFactory."""

    def test_create_stdio_without_command_raises_error(self) -> None:
        """Ошибка при создании stdio транспорта без command."""
        config = MCPServerConfig(
            name="test-server",
            type="stdio",
            command="python",  # Валидация требует command
        )
        # Обходим валидацию
        config.command = None

        with pytest.raises(ValueError, match="requires 'command'"):
            TransportFactory.create(config)

    def test_create_http_without_url_raises_error(self) -> None:
        """Ошибка при создании http транспорта без url."""
        config = MCPServerConfig(
            name="test-server",
            type="http",
            url="http://localhost:8080",  # Валидация требует url
        )
        # Обходим валидацию
        config.url = None

        with pytest.raises(ValueError, match="requires 'url'"):
            TransportFactory.create(config)

    def test_create_sse_without_url_raises_error(self) -> None:
        """Ошибка при создании sse транспорта без url."""
        config = MCPServerConfig(
            name="test-server",
            type="sse",
            url="http://localhost:8080/sse",  # Валидация требует url
        )
        # Обходим валидацию
        config.url = None

        with pytest.raises(ValueError, match="requires 'url'"):
            TransportFactory.create(config)

    def test_create_unsupported_type_raises_error(self) -> None:
        """Ошибка при неподдерживаемом типе транспорта."""
        config = MCPServerConfig(
            name="test-server",
            type="http",
            url="http://localhost:8080",
        )
        # Обходим валидацию
        config.type = "invalid"

        with pytest.raises(ValueError, match="Unsupported transport type"):
            TransportFactory.create(config)


class TestMCPTransportProtocol:
    """Тесты протокола MCPTransport."""

    def test_stdio_transport_implements_protocol(self) -> None:
        """StdioTransport реализует MCPTransport."""
        transport = StdioTransport(command="test")

        assert isinstance(transport, MCPTransport)
        assert hasattr(transport, "is_connected")
        assert hasattr(transport, "connect")
        assert hasattr(transport, "send_request")
        assert hasattr(transport, "send_notification")
        assert hasattr(transport, "close")

    def test_http_transport_implements_protocol(self) -> None:
        """HttpTransport реализует MCPTransport."""
        transport = HttpTransport(url="http://localhost:8080")

        assert isinstance(transport, MCPTransport)
        assert hasattr(transport, "is_connected")
        assert hasattr(transport, "connect")
        assert hasattr(transport, "send_request")
        assert hasattr(transport, "send_notification")
        assert hasattr(transport, "close")

    def test_sse_transport_implements_protocol(self) -> None:
        """SseTransport реализует MCPTransport."""
        transport = SseTransport(url="http://localhost:8080/sse")

        assert isinstance(transport, MCPTransport)
        assert hasattr(transport, "is_connected")
        assert hasattr(transport, "connect")
        assert hasattr(transport, "send_request")
        assert hasattr(transport, "send_notification")
        assert hasattr(transport, "close")

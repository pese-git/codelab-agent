"""Тесты для MCP Roots функциональности.

Покрывают:
- Модель MCPRoot
- Модель MCPClientCapabilities
- Установку roots в MCPClient
- Отправку capabilities.roots при initialize
- Отправку notifications/roots/list_changed при изменении roots
- Установку roots через MCPManager
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.mcp.client import MCPClient, MCPClientState
from codelab.server.mcp.manager import MCPManager
from codelab.server.mcp.models import (
    MCPClientCapabilities,
    MCPRoot,
    MCPServerConfig,
)


class TestMCPRoot:
    """Тесты модели MCPRoot."""

    def test_create_root_with_uri_only(self) -> None:
        """Создание root только с URI."""
        root = MCPRoot(uri="file:///home/user/project")
        assert root.uri == "file:///home/user/project"
        assert root.name is None

    def test_create_root_with_name(self) -> None:
        """Создание root с именем."""
        root = MCPRoot(
            uri="file:///home/user/project",
            name="My Project",
        )
        assert root.uri == "file:///home/user/project"
        assert root.name == "My Project"

    def test_root_serialization(self) -> None:
        """Сериализация root в dict."""
        root = MCPRoot(uri="file:///tmp", name="Temp")
        data = root.model_dump()
        assert data == {"uri": "file:///tmp", "name": "Temp"}

    def test_root_serialization_without_name(self) -> None:
        """Сериализация root без имени."""
        root = MCPRoot(uri="file:///tmp")
        data = root.model_dump()
        assert data == {"uri": "file:///tmp", "name": None}


class TestMCPClientCapabilities:
    """Тесты модели MCPClientCapabilities."""

    def test_create_empty_capabilities(self) -> None:
        """Создание пустых capabilities."""
        caps = MCPClientCapabilities()
        assert caps.roots is None
        assert caps.sampling is None
        assert caps.elicitation is None

    def test_create_with_roots(self) -> None:
        """Создание capabilities с roots support."""
        caps = MCPClientCapabilities(roots={"listChanged": True})
        assert caps.roots == {"listChanged": True}

    def test_capabilities_serialization(self) -> None:
        """Сериализация capabilities."""
        caps = MCPClientCapabilities(roots={"listChanged": True})
        data = caps.model_dump(exclude_none=True)
        assert data == {"roots": {"listChanged": True}}


class TestMCPClientRoots:
    """Тесты установки roots в MCPClient."""

    @pytest.fixture
    def mock_transport(self) -> MagicMock:
        """Создаёт mock транспорт."""
        transport = MagicMock()
        transport.connect = AsyncMock()
        transport.send_request = AsyncMock()
        transport.send_notification = AsyncMock()
        transport.close = AsyncMock()
        transport.register_notification_handler = MagicMock()
        return transport

    @pytest.fixture
    def client(self) -> MCPClient:
        """Создаёт MCPClient с тестовой конфигурацией."""
        config = MCPServerConfig(
            name="test-server",
            type="stdio",
            command="test",
        )
        return MCPClient(config)

    @pytest.mark.asyncio
    async def test_set_roots_before_initialize(
        self, client: MCPClient, mock_transport: MagicMock
    ) -> None:
        """Установка roots до инициализации."""
        client._transport = mock_transport
        client._state = MCPClientState.CONNECTING

        roots = [MCPRoot(uri="file:///project", name="Project")]
        await client.set_roots(roots)

        assert len(client.roots) == 1
        assert client.roots[0].uri == "file:///project"
        # Notification не должна отправляться до инициализации
        mock_transport.send_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_roots_after_initialize_sends_notification(
        self, client: MCPClient, mock_transport: MagicMock
    ) -> None:
        """Установка roots после инициализации отправляет notification."""
        client._transport = mock_transport
        client._state = MCPClientState.READY

        # Устанавливаем roots
        roots = [MCPRoot(uri="file:///project")]
        await client.set_roots(roots)

        # Должна быть отправлена notification
        mock_transport.send_notification.assert_called_once_with(
            method="notifications/roots/list_changed"
        )

    @pytest.mark.asyncio
    async def test_set_roots_no_notification_if_unchanged(
        self, client: MCPClient, mock_transport: MagicMock
    ) -> None:
        """Notification не отправляется если roots не изменились."""
        client._transport = mock_transport
        client._state = MCPClientState.READY

        # Устанавливаем roots первый раз
        roots = [MCPRoot(uri="file:///project")]
        await client.set_roots(roots)

        # Сбрасываем mock
        mock_transport.send_notification.reset_mock()

        # Устанавливаем те же roots
        await client.set_roots(roots)

        # Notification не должна отправляться
        mock_transport.send_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_initialize_sends_roots_capability(
        self, client: MCPClient, mock_transport: MagicMock
    ) -> None:
        """Initialize отправляет capabilities.roots если есть roots."""
        client._transport = mock_transport
        client._state = MCPClientState.CONNECTING

        # Устанавливаем roots до инициализации
        roots = [MCPRoot(uri="file:///project")]
        await client.set_roots(roots)

        # Mock response от сервера
        mock_transport.send_request.return_value = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "test", "version": "1.0"},
        }

        # Выполняем инициализацию
        await client.initialize()

        # Проверяем, что capabilities.roots был отправлен
        call_args = mock_transport.send_request.call_args
        params = call_args.kwargs["params"]
        assert "capabilities" in params
        assert "roots" in params["capabilities"]
        assert params["capabilities"]["roots"] == {"listChanged": True}


class TestMCPManagerRoots:
    """Тесты установки roots через MCPManager."""

    @pytest.fixture
    def manager(self) -> MCPManager:
        """Создаёт MCPManager."""
        return MCPManager(session_id="test-session")

    @pytest.mark.asyncio
    async def test_set_roots_for_all_servers(self, manager: MCPManager) -> None:
        """set_roots устанавливает roots для всех серверов."""
        # Создаём mock клиенты
        client1 = MagicMock(spec=MCPClient)
        client1.state = MCPClientState.READY
        client1.set_roots = AsyncMock()

        client2 = MagicMock(spec=MCPClient)
        client2.state = MCPClientState.READY
        client2.set_roots = AsyncMock()

        manager._clients = {"server1": client1, "server2": client2}

        # Устанавливаем roots
        roots = [MCPRoot(uri="file:///project")]
        await manager.set_roots(roots)

        # Проверяем, что set_roots был вызван для обоих клиентов
        client1.set_roots.assert_called_once_with(roots)
        client2.set_roots.assert_called_once_with(roots)

    @pytest.mark.asyncio
    async def test_set_roots_skips_not_ready_servers(
        self, manager: MCPManager
    ) -> None:
        """set_roots пропускает серверы, которые не готовы."""
        # Создаём mock клиенты с разными состояниями
        ready_client = MagicMock(spec=MCPClient)
        ready_client.state = MCPClientState.READY
        ready_client.set_roots = AsyncMock()

        connecting_client = MagicMock(spec=MCPClient)
        connecting_client.state = MCPClientState.CONNECTING
        connecting_client.set_roots = AsyncMock()

        manager._clients = {
            "ready": ready_client,
            "connecting": connecting_client,
        }

        # Устанавливаем roots
        roots = [MCPRoot(uri="file:///project")]
        await manager.set_roots(roots)

        # Проверяем, что set_roots был вызван только для ready клиента
        ready_client.set_roots.assert_called_once_with(roots)
        connecting_client.set_roots.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_roots_handles_errors(self, manager: MCPManager) -> None:
        """set_roots обрабатывает ошибки от отдельных серверов."""
        # Создаём mock клиенты
        good_client = MagicMock(spec=MCPClient)
        good_client.state = MCPClientState.READY
        good_client.set_roots = AsyncMock()

        bad_client = MagicMock(spec=MCPClient)
        bad_client.state = MCPClientState.READY
        bad_client.set_roots = AsyncMock(
            side_effect=Exception("Connection failed")
        )

        manager._clients = {"good": good_client, "bad": bad_client}

        # Устанавливаем roots - не должно вызвать исключение
        roots = [MCPRoot(uri="file:///project")]
        await manager.set_roots(roots)

        # Проверяем, что set_roots был вызван для обоих
        good_client.set_roots.assert_called_once_with(roots)
        bad_client.set_roots.assert_called_once_with(roots)

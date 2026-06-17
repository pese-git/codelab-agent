"""Тесты для непокрытых веток MCPClient.

Покрывают guard-ветки и ошибки list_tools, list_resources,
list_resource_templates, read_resource, list_prompts, get_prompt,
а также обработку notifications.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codelab.server.mcp.client import MCPClient, MCPClientError, MCPClientState
from codelab.server.mcp.models import MCPServerConfig
from codelab.server.mcp.transport import StdioTransportError


@pytest.fixture
def ready_client() -> MCPClient:
    """Готовый к работе MCPClient с mock-транспортом."""
    config = MCPServerConfig(name="test", type="stdio", command="mcp-server")
    client = MCPClient(config)
    client._state = MCPClientState.READY
    client._transport = AsyncMock()
    client._capabilities = MagicMock()
    client._capabilities.tools = {}
    client._capabilities.resources = {}
    client._capabilities.prompts = {}
    return client


class TestMCPClientListToolsGuards:
    """Тесты list_tools."""

    @pytest.mark.asyncio
    async def test_list_tools_not_ready(self) -> None:
        """list_tools выбрасывает ошибку если клиент не READY."""
        config = MCPServerConfig(name="test", type="stdio", command="cmd")
        client = MCPClient(config)
        client._state = MCPClientState.CREATED

        with pytest.raises(MCPClientError, match="Cannot list tools in state"):
            await client.list_tools()

    @pytest.mark.asyncio
    async def test_list_tools_no_transport(self, ready_client: MCPClient) -> None:
        """list_tools выбрасывает ошибку если транспорт отсутствует."""
        ready_client._transport = None

        with pytest.raises(MCPClientError, match="Transport not available"):
            await ready_client.list_tools()

    @pytest.mark.asyncio
    async def test_list_tools_transport_error(self, ready_client: MCPClient) -> None:
        """StdioTransportError превращается в MCPClientError."""
        ready_client._transport.send_request = AsyncMock(
            side_effect=StdioTransportError("broken")
        )

        with pytest.raises(MCPClientError, match="Failed to list tools"):
            await ready_client.list_tools()


class TestMCPClientListResourcesGuards:
    """Тесты list_resources."""

    @pytest.mark.asyncio
    async def test_list_resources_not_ready(self) -> None:
        """list_resources выбрасывает ошибку если клиент не READY."""
        config = MCPServerConfig(name="test", type="stdio", command="cmd")
        client = MCPClient(config)
        client._state = MCPClientState.CREATED

        with pytest.raises(MCPClientError, match="Cannot list resources in state"):
            await client.list_resources()

    @pytest.mark.asyncio
    async def test_list_resources_no_transport(self, ready_client: MCPClient) -> None:
        """list_resources выбрасывает ошибку если транспорт отсутствует."""
        ready_client._transport = None

        with pytest.raises(MCPClientError, match="Transport not available"):
            await ready_client.list_resources()

    @pytest.mark.asyncio
    async def test_list_resources_transport_error(self, ready_client: MCPClient) -> None:
        """StdioTransportError превращается в MCPClientError."""
        ready_client._transport.send_request = AsyncMock(
            side_effect=StdioTransportError("broken")
        )

        with pytest.raises(MCPClientError, match="Failed to list resources"):
            await ready_client.list_resources()


class TestMCPClientListResourceTemplatesGuards:
    """Тесты list_resource_templates."""

    @pytest.mark.asyncio
    async def test_list_resource_templates_not_ready(self) -> None:
        """list_resource_templates выбрасывает ошибку если клиент не READY."""
        config = MCPServerConfig(name="test", type="stdio", command="cmd")
        client = MCPClient(config)
        client._state = MCPClientState.CREATED

        with pytest.raises(MCPClientError, match="Cannot list resource templates in state"):
            await client.list_resource_templates()

    @pytest.mark.asyncio
    async def test_list_resource_templates_no_transport(self, ready_client: MCPClient) -> None:
        """list_resource_templates выбрасывает ошибку если транспорт отсутствует."""
        ready_client._transport = None

        with pytest.raises(MCPClientError, match="Transport not available"):
            await ready_client.list_resource_templates()

    @pytest.mark.asyncio
    async def test_list_resource_templates_transport_error(
        self, ready_client: MCPClient
    ) -> None:
        """StdioTransportError превращается в MCPClientError."""
        ready_client._transport.send_request = AsyncMock(
            side_effect=StdioTransportError("broken")
        )

        with pytest.raises(MCPClientError, match="Failed to list resource templates"):
            await ready_client.list_resource_templates()


class TestMCPClientReadResourceGuards:
    """Тесты read_resource."""

    @pytest.mark.asyncio
    async def test_read_resource_no_transport(self, ready_client: MCPClient) -> None:
        """read_resource выбрасывает ошибку если транспорт отсутствует."""
        ready_client._transport = None

        with pytest.raises(MCPClientError, match="Transport not available"):
            await ready_client.read_resource("file:///tmp/test.txt")

    @pytest.mark.asyncio
    async def test_read_resource_transport_error(self, ready_client: MCPClient) -> None:
        """StdioTransportError превращается в MCPClientError."""
        ready_client._transport.send_request = AsyncMock(
            side_effect=StdioTransportError("broken")
        )

        with pytest.raises(MCPClientError, match="Failed to read resource"):
            await ready_client.read_resource("file:///tmp/test.txt")


class TestMCPClientListPromptsGuards:
    """Тесты list_prompts."""

    @pytest.mark.asyncio
    async def test_list_prompts_not_ready(self) -> None:
        """list_prompts выбрасывает ошибку если клиент не READY."""
        config = MCPServerConfig(name="test", type="stdio", command="cmd")
        client = MCPClient(config)
        client._state = MCPClientState.CREATED

        with pytest.raises(MCPClientError, match="Cannot list prompts in state"):
            await client.list_prompts()

    @pytest.mark.asyncio
    async def test_list_prompts_no_transport(self, ready_client: MCPClient) -> None:
        """list_prompts выбрасывает ошибку если транспорт отсутствует."""
        ready_client._transport = None

        with pytest.raises(MCPClientError, match="Transport not available"):
            await ready_client.list_prompts()

    @pytest.mark.asyncio
    async def test_list_prompts_transport_error(self, ready_client: MCPClient) -> None:
        """StdioTransportError превращается в MCPClientError."""
        ready_client._transport.send_request = AsyncMock(
            side_effect=StdioTransportError("broken")
        )

        with pytest.raises(MCPClientError, match="Failed to list prompts"):
            await ready_client.list_prompts()


class TestMCPClientGetPromptGuards:
    """Тесты get_prompt."""

    @pytest.mark.asyncio
    async def test_get_prompt_no_transport(self, ready_client: MCPClient) -> None:
        """get_prompt выбрасывает ошибку если транспорт отсутствует."""
        ready_client._transport = None

        with pytest.raises(MCPClientError, match="Transport not available"):
            await ready_client.get_prompt("test_prompt")

    @pytest.mark.asyncio
    async def test_get_prompt_transport_error(self, ready_client: MCPClient) -> None:
        """StdioTransportError превращается в MCPClientError."""
        ready_client._transport.send_request = AsyncMock(
            side_effect=StdioTransportError("broken")
        )

        with pytest.raises(MCPClientError, match="Failed to get prompt"):
            await ready_client.get_prompt("test_prompt")


class TestMCPClientNotificationHandling:
    """Тесты обработки notifications."""

    @pytest.mark.asyncio
    async def test_register_handler_logs(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """register_handler логирует регистрацию обработчика."""
        config = MCPServerConfig(name="test", type="stdio", command="cmd")
        client = MCPClient(config)

        with caplog.at_level("DEBUG"):
            client.register_handler("notifications/progress", lambda x: None)

        assert "Registered notification handler" in caplog.text

    @pytest.mark.asyncio
    async def test_on_transport_notification_delegates(
        self,
    ) -> None:
        """_on_transport_notification кладёт notification в очередь."""
        config = MCPServerConfig(name="test", type="stdio", command="cmd")
        client = MCPClient(config)

        await client._on_transport_notification({"method": "test", "params": {}})

        assert client._notification_queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_process_notifications_timeout_continues(self) -> None:
        """TimeoutError в цикле notifications приводит к continue."""
        config = MCPServerConfig(name="test", type="stdio", command="cmd")
        client = MCPClient(config)
        client._state = MCPClientState.READY

        with patch.object(
            asyncio, "wait_for", side_effect=[TimeoutError(), asyncio.CancelledError()]
        ):
            with pytest.raises(asyncio.CancelledError):
                await client._process_notifications()

    @pytest.mark.asyncio
    async def test_process_notifications_generic_error_logged(self) -> None:
        """Общее исключение в цикле notifications логируется."""
        config = MCPServerConfig(name="test", type="stdio", command="cmd")
        client = MCPClient(config)
        client._state = MCPClientState.READY

        with patch.object(
            asyncio, "wait_for", side_effect=[ValueError("boom"), asyncio.CancelledError()]
        ):
            with pytest.raises(asyncio.CancelledError):
                await client._process_notifications()

    @pytest.mark.asyncio
    async def test_process_notifications_progress_callback(self) -> None:
        """Цикл notifications вызывает progress callback."""
        config = MCPServerConfig(name="test", type="stdio", command="cmd")
        client = MCPClient(config)
        client._state = MCPClientState.READY

        callback = MagicMock()
        client.register_progress_callback(callback)

        notification = {
            "method": "notifications/progress",
            "params": {
                "progressToken": "token_1",
                "progress": 5,
                "total": 10,
            },
        }

        with patch.object(
            asyncio,
            "wait_for",
            side_effect=[notification, asyncio.CancelledError()],
        ):
            with pytest.raises(asyncio.CancelledError):
                await client._process_notifications()

        callback.assert_called_once()

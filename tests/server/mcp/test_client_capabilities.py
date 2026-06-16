"""Тесты для MCPClient capabilities проверки.

Проверяют что пустой dict {} в capabilities интерпретируется как
поддержка функции, а None — как отсутствие поддержки.
Согласно MCP спецификации:
- tools: null — не поддерживает
- tools: {} — поддерживает (без дополнительных опций)
- tools: {listChanged: true} — поддерживает с опциями
"""

from unittest.mock import AsyncMock

import pytest

from codelab.server.mcp.client import MCPClient, MCPClientState
from codelab.server.mcp.models import MCPCapabilities, MCPServerConfig


class TestMCPClientCapabilitiesCheck:
    """Тесты проверки capabilities для tools/resources/prompts."""

    @pytest.mark.asyncio
    async def test_list_tools_with_empty_capabilities(self):
        """tools: {} означает что tools поддерживается."""
        config = MCPServerConfig(name="test", type="stdio", command="mcp-server")
        client = MCPClient(config)
        client._state = MCPClientState.READY

        mock_transport = AsyncMock()
        mock_transport.send_request = AsyncMock(return_value={
            "tools": [
                {
                    "name": "test_tool",
                    "description": "A test tool",
                    "inputSchema": {"type": "object", "properties": {}},
                },
            ]
        })
        client._transport = mock_transport
        # Пустой dict — tools поддерживается
        client._capabilities = MCPCapabilities(tools={})

        tools = await client.list_tools()

        # Должен запросить tools и вернуть результат
        assert len(tools) == 1
        assert tools[0].name == "test_tool"
        mock_transport.send_request.assert_called_once_with(
            method="tools/list",
            timeout=30.0,
        )

    @pytest.mark.asyncio
    async def test_list_tools_with_null_capabilities(self):
        """tools: null означает что tools не поддерживается."""
        config = MCPServerConfig(name="test", type="stdio", command="mcp-server")
        client = MCPClient(config)
        client._state = MCPClientState.READY

        mock_transport = AsyncMock()
        client._transport = mock_transport
        # None — tools не поддерживается
        client._capabilities = MCPCapabilities(tools=None)

        tools = await client.list_tools()

        # Должен вернуть пустой список без запроса
        assert tools == []
        mock_transport.send_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_tools_with_list_changed_capability(self):
        """tools: {listChanged: true} означает что tools поддерживается."""
        config = MCPServerConfig(name="test", type="stdio", command="mcp-server")
        client = MCPClient(config)
        client._state = MCPClientState.READY

        mock_transport = AsyncMock()
        mock_transport.send_request = AsyncMock(return_value={"tools": []})
        client._transport = mock_transport
        # С опцией listChanged
        client._capabilities = MCPCapabilities(tools={"listChanged": True})

        tools = await client.list_tools()

        # Должен запросить tools
        assert tools == []
        mock_transport.send_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_resources_with_empty_capabilities(self):
        """resources: {} означает что resources поддерживается."""
        config = MCPServerConfig(name="test", type="stdio", command="mcp-server")
        client = MCPClient(config)
        client._state = MCPClientState.READY

        mock_transport = AsyncMock()
        mock_transport.send_request = AsyncMock(return_value={
            "resources": [
                {
                    "uri": "file:///tmp/test.txt",
                    "name": "test.txt",
                    "mimeType": "text/plain",
                },
            ]
        })
        client._transport = mock_transport
        client._capabilities = MCPCapabilities(resources={})

        resources = await client.list_resources()

        assert len(resources) == 1
        mock_transport.send_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_resources_with_null_capabilities(self):
        """resources: null означает что resources не поддерживается."""
        config = MCPServerConfig(name="test", type="stdio", command="mcp-server")
        client = MCPClient(config)
        client._state = MCPClientState.READY

        mock_transport = AsyncMock()
        client._transport = mock_transport
        client._capabilities = MCPCapabilities(resources=None)

        resources = await client.list_resources()

        assert resources == []
        mock_transport.send_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_prompts_with_empty_capabilities(self):
        """prompts: {} означает что prompts поддерживается."""
        config = MCPServerConfig(name="test", type="stdio", command="mcp-server")
        client = MCPClient(config)
        client._state = MCPClientState.READY

        mock_transport = AsyncMock()
        mock_transport.send_request = AsyncMock(return_value={
            "prompts": [
                {
                    "name": "test_prompt",
                    "description": "A test prompt",
                },
            ]
        })
        client._transport = mock_transport
        client._capabilities = MCPCapabilities(prompts={})

        prompts = await client.list_prompts()

        assert len(prompts) == 1
        mock_transport.send_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_prompts_with_null_capabilities(self):
        """prompts: null означает что prompts не поддерживается."""
        config = MCPServerConfig(name="test", type="stdio", command="mcp-server")
        client = MCPClient(config)
        client._state = MCPClientState.READY

        mock_transport = AsyncMock()
        client._transport = mock_transport
        client._capabilities = MCPCapabilities(prompts=None)

        prompts = await client.list_prompts()

        assert prompts == []
        mock_transport.send_request.assert_not_called()

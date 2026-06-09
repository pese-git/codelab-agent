"""Тесты для ToolFilter."""


import pytest

from codelab.server.agent.tool_filter import ToolFilter
from codelab.server.protocol.state import ClientRuntimeCapabilities
from codelab.server.tools.base import ToolDefinition


@pytest.fixture
def tool_filter():
    return ToolFilter()


@pytest.fixture
def all_tools():
    return [
        ToolDefinition(
            name="fs/read_text_file",
            description="Read",
            parameters={},
            kind="filesystem",
        ),
        ToolDefinition(
            name="fs/write_text_file",
            description="Write",
            parameters={},
            kind="filesystem",
        ),
        ToolDefinition(
            name="terminal/create",
            description="Terminal",
            parameters={},
            kind="terminal",
        ),
        ToolDefinition(
            name="update_plan",
            description="Plan",
            parameters={},
            kind="plan",
        ),
        ToolDefinition(
            name="think",
            description="Think",
            parameters={},
            kind="think",
        ),
    ]


class TestToolFilterCapabilities:
    """2.5 — фильтрация с различными capabilities."""

    def test_with_full_capabilities(self, tool_filter, all_tools):
        caps = ClientRuntimeCapabilities(
            fs_read=True,
            fs_write=True,
            terminal=True,
        )
        filtered = tool_filter.filter(all_tools, capabilities=caps)
        names = {t.name for t in filtered}
        assert "fs/read_text_file" in names
        assert "fs/write_text_file" in names
        assert "terminal/create" in names
        assert "update_plan" in names
        assert "think" in names

    def test_with_partial_capabilities(self, tool_filter, all_tools):
        caps = ClientRuntimeCapabilities(
            fs_read=True,
            fs_write=False,
            terminal=False,
        )
        filtered = tool_filter.filter(all_tools, capabilities=caps)
        names = {t.name for t in filtered}
        assert "fs/read_text_file" in names
        assert "fs/write_text_file" not in names
        assert "terminal/create" not in names
        assert "update_plan" in names  # server-side

    def test_with_no_capabilities(self, tool_filter, all_tools):
        caps = ClientRuntimeCapabilities(
            fs_read=False,
            fs_write=False,
            terminal=False,
        )
        filtered = tool_filter.filter(all_tools, capabilities=caps)
        names = {t.name for t in filtered}
        # Только server-side
        assert "update_plan" in names
        assert "think" in names
        assert "fs/read_text_file" not in names


class TestMCPTools:
    """2.6 — MCP tools включаются всегда."""

    def test_mcp_tools_always_included(self, tool_filter, all_tools):
        caps = ClientRuntimeCapabilities(
            fs_read=False,
            fs_write=False,
            terminal=False,
        )
        mcp_tools = [
            ToolDefinition(
                name="mcp:fs:read_file",
                description="MCP Read",
                parameters={},
                kind="mcp",
            ),
        ]
        filtered = tool_filter.filter(all_tools, capabilities=caps, mcp_tools=mcp_tools)
        names = {t.name for t in filtered}
        assert "mcp:fs:read_file" in names

    def test_mcp_tools_with_full_capabilities(self, tool_filter, all_tools):
        caps = ClientRuntimeCapabilities(
            fs_read=True,
            fs_write=True,
            terminal=True,
        )
        mcp_tools = [
            ToolDefinition(
                name="mcp:github:search",
                description="MCP Search",
                parameters={},
                kind="mcp",
            ),
        ]
        filtered = tool_filter.filter(all_tools, capabilities=caps, mcp_tools=mcp_tools)
        names = {t.name for t in filtered}
        assert "mcp:github:search" in names


class TestNoneCapabilities:
    """2.7 — capabilities is None → только серверные + MCP."""

    def test_none_capabilities_server_tools_only(self, tool_filter, all_tools):
        filtered = tool_filter.filter(all_tools, capabilities=None)
        names = {t.name for t in filtered}
        assert "update_plan" in names
        assert "think" in names
        assert "fs/read_text_file" not in names
        assert "terminal/create" not in names

    def test_none_capabilities_with_mcp(self, tool_filter, all_tools):
        mcp_tools = [
            ToolDefinition(name="mcp:fs:read", description="MCP", parameters={}, kind="mcp"),
        ]
        filtered = tool_filter.filter(all_tools, capabilities=None, mcp_tools=mcp_tools)
        names = {t.name for t in filtered}
        assert "update_plan" in names
        assert "think" in names
        assert "mcp:fs:read" in names

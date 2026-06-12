"""Тесты для ToolFilter.

Проверяют фильтрацию инструментов по client capabilities
с использованием префикса имени + kind (масштабируемо).
"""

import pytest

from codelab.server.agent.tool_filter import ToolFilter
from codelab.server.protocol.state import ClientRuntimeCapabilities
from codelab.server.tools.base import ToolDefinition


def _tool(name: str, kind: str) -> ToolDefinition:
    return ToolDefinition(name=name, description=name, parameters={}, kind=kind)


@pytest.fixture
def tool_filter() -> ToolFilter:
    return ToolFilter()


@pytest.fixture
def standard_tools() -> list[ToolDefinition]:
    """Стандартные инструменты с корректными kind значениями."""
    return [
        _tool("fs/read_text_file", "read"),
        _tool("fs/write_text_file", "edit"),
        _tool("terminal/create", "execute"),
        _tool("terminal/wait_for_exit", "read"),
        _tool("terminal/release", "delete"),
        _tool("update_plan", "plan"),
        _tool("think", "think"),
    ]


class TestToolFilterCapabilities:
    """Фильтрация с различными capabilities."""

    def test_with_full_capabilities(self, tool_filter, standard_tools):
        caps = ClientRuntimeCapabilities(fs_read=True, fs_write=True, terminal=True)
        filtered = tool_filter.filter(standard_tools, capabilities=caps)
        names = {t.name for t in filtered}
        assert "fs/read_text_file" in names
        assert "fs/write_text_file" in names
        assert "terminal/create" in names
        assert "terminal/wait_for_exit" in names
        assert "terminal/release" in names
        assert "update_plan" in names
        assert "think" in names

    def test_fs_read_only(self, tool_filter, standard_tools):
        caps = ClientRuntimeCapabilities(fs_read=True, fs_write=False, terminal=False)
        filtered = tool_filter.filter(standard_tools, capabilities=caps)
        names = {t.name for t in filtered}
        assert "fs/read_text_file" in names
        assert "fs/write_text_file" not in names
        assert "terminal/create" not in names
        assert "terminal/wait_for_exit" not in names
        assert "terminal/release" not in names
        assert "update_plan" in names

    def test_fs_write_only(self, tool_filter, standard_tools):
        caps = ClientRuntimeCapabilities(fs_read=False, fs_write=True, terminal=False)
        filtered = tool_filter.filter(standard_tools, capabilities=caps)
        names = {t.name for t in filtered}
        assert "fs/read_text_file" not in names
        assert "fs/write_text_file" in names
        assert "update_plan" in names

    def test_terminal_only(self, tool_filter, standard_tools):
        caps = ClientRuntimeCapabilities(fs_read=False, fs_write=False, terminal=True)
        filtered = tool_filter.filter(standard_tools, capabilities=caps)
        names = {t.name for t in filtered}
        assert "fs/read_text_file" not in names
        assert "fs/write_text_file" not in names
        assert "terminal/create" in names
        assert "terminal/wait_for_exit" in names
        assert "terminal/release" in names
        assert "update_plan" in names

    def test_no_capabilities(self, tool_filter, standard_tools):
        caps = ClientRuntimeCapabilities(fs_read=False, fs_write=False, terminal=False)
        filtered = tool_filter.filter(standard_tools, capabilities=caps)
        names = {t.name for t in filtered}
        assert "update_plan" in names
        assert "think" in names
        assert "fs/read_text_file" not in names
        assert "fs/write_text_file" not in names
        assert "terminal/create" not in names


class TestScalableFsTools:
    """Новые fs/* инструменты фильтруются по kind без изменения кода."""

    def test_fs_grep_treated_as_read(self, tool_filter):
        """fs/grep с kind='search' → требует fs_read."""
        tools = [_tool("fs/grep", "search")]
        caps_read = ClientRuntimeCapabilities(fs_read=True, fs_write=False, terminal=False)
        caps_write = ClientRuntimeCapabilities(fs_read=False, fs_write=True, terminal=False)

        assert "fs/grep" in {t.name for t in tool_filter.filter(tools, capabilities=caps_read)}
        assert "fs/grep" not in {t.name for t in tool_filter.filter(tools, capabilities=caps_write)}

    def test_fs_patch_treated_as_read(self, tool_filter):
        """fs/patch с kind='edit' → требует fs_write."""
        tools = [_tool("fs/patch", "edit")]
        caps_read = ClientRuntimeCapabilities(fs_read=True, fs_write=False, terminal=False)
        caps_write = ClientRuntimeCapabilities(fs_read=False, fs_write=True, terminal=False)

        assert "fs/patch" not in {t.name for t in tool_filter.filter(tools, capabilities=caps_read)}
        assert "fs/patch" in {t.name for t in tool_filter.filter(tools, capabilities=caps_write)}

    def test_fs_search_treated_as_read(self, tool_filter):
        """fs/search с kind='search' → требует fs_read (default)."""
        tools = [_tool("fs/search", "search")]
        caps = ClientRuntimeCapabilities(fs_read=True, fs_write=False, terminal=False)
        assert "fs/search" in {t.name for t in tool_filter.filter(tools, capabilities=caps)}

    def test_fs_delete_treated_as_read(self, tool_filter):
        """fs/delete с kind='delete' → требует fs_read (default)."""
        tools = [_tool("fs/delete_file", "delete")]
        caps = ClientRuntimeCapabilities(fs_read=True, fs_write=False, terminal=False)
        assert "fs/delete_file" in {t.name for t in tool_filter.filter(tools, capabilities=caps)}

    def test_fs_move_treated_as_read(self, tool_filter):
        """fs/move с kind='move' → требует fs_read (default)."""
        tools = [_tool("fs/move_file", "move")]
        caps = ClientRuntimeCapabilities(fs_read=True, fs_write=False, terminal=False)
        assert "fs/move_file" in {t.name for t in tool_filter.filter(tools, capabilities=caps)}

    def test_fs_list_treated_as_read(self, tool_filter):
        """fs/list_directory с kind='read' → требует fs_read."""
        tools = [_tool("fs/list_directory", "read")]
        caps = ClientRuntimeCapabilities(fs_read=True, fs_write=False, terminal=False)
        assert "fs/list_directory" in {t.name for t in tool_filter.filter(tools, capabilities=caps)}


class TestScalableTerminalTools:
    """Любые terminal/* инструменты фильтруются по префиксу."""

    def test_any_terminal_kind_requires_terminal_capability(self, tool_filter):
        """terminal/* с любым kind → требует capabilities.terminal."""
        tools = [
            _tool("terminal/exec", "execute"),
            _tool("terminal/kill", "delete"),
            _tool("terminal/info", "read"),
        ]
        caps = ClientRuntimeCapabilities(fs_read=False, fs_write=False, terminal=True)
        filtered = tool_filter.filter(tools, capabilities=caps)
        names = {t.name for t in filtered}
        assert "terminal/exec" in names
        assert "terminal/kill" in names
        assert "terminal/info" in names

    def test_terminal_without_capability(self, tool_filter):
        """terminal/* без capabilities.terminal → исключены."""
        tools = [_tool("terminal/create", "execute")]
        caps = ClientRuntimeCapabilities(fs_read=False, fs_write=False, terminal=False)
        filtered = tool_filter.filter(tools, capabilities=caps)
        assert len(filtered) == 0


class TestMCPTools:
    """MCP tools включаются всегда."""

    def test_mcp_tools_always_included(self, tool_filter, standard_tools):
        caps = ClientRuntimeCapabilities(fs_read=False, fs_write=False, terminal=False)
        mcp_tools = [_tool("mcp:fs:read_file", "mcp")]
        filtered = tool_filter.filter(standard_tools, capabilities=caps, mcp_tools=mcp_tools)
        assert "mcp:fs:read_file" in {t.name for t in filtered}

    def test_mcp_tools_with_full_capabilities(self, tool_filter, standard_tools):
        caps = ClientRuntimeCapabilities(fs_read=True, fs_write=True, terminal=True)
        mcp_tools = [_tool("mcp:github:search", "mcp")]
        filtered = tool_filter.filter(standard_tools, capabilities=caps, mcp_tools=mcp_tools)
        assert "mcp:github:search" in {t.name for t in filtered}

    def test_mcp_tools_without_capabilities(self, tool_filter):
        """MCP tools включаются даже когда capabilities=None."""
        mcp_tools = [_tool("mcp:db:query", "mcp")]
        filtered = tool_filter.filter([], capabilities=None, mcp_tools=mcp_tools)
        assert "mcp:db:query" in {t.name for t in filtered}


class TestNoneCapabilities:
    """capabilities is None → только серверные + MCP."""

    def test_none_capabilities_server_tools_only(self, tool_filter, standard_tools):
        filtered = tool_filter.filter(standard_tools, capabilities=None)
        names = {t.name for t in filtered}
        assert "update_plan" in names
        assert "think" in names
        assert "fs/read_text_file" not in names
        assert "terminal/create" not in names

    def test_none_capabilities_with_mcp(self, tool_filter, standard_tools):
        mcp_tools = [_tool("mcp:fs:read", "mcp")]
        filtered = tool_filter.filter(standard_tools, capabilities=None, mcp_tools=mcp_tools)
        names = {t.name for t in filtered}
        assert "update_plan" in names
        assert "think" in names
        assert "mcp:fs:read" in names


class TestUnknownPrefix:
    """Инструменты с неизвестным префиксом исключаются."""

    def test_unknown_prefix_excluded(self, tool_filter):
        tools = [_tool("custom/tool", "execute")]
        caps = ClientRuntimeCapabilities(fs_read=True, fs_write=True, terminal=True)
        filtered = tool_filter.filter(tools, capabilities=caps)
        assert len(filtered) == 0

    def test_empty_tools_list(self, tool_filter):
        caps = ClientRuntimeCapabilities(fs_read=True, fs_write=True, terminal=True)
        filtered = tool_filter.filter([], capabilities=caps)
        assert filtered == []

    def test_no_mcp_tools_no_capabilities(self, tool_filter):
        filtered = tool_filter.filter([], capabilities=None, mcp_tools=None)
        assert filtered == []

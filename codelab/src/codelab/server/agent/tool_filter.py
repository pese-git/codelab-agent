"""ToolFilter — фильтрация инструментов по client capabilities + MCP.

Рефакторинг из AgentOrchestrator._filter_tools_by_capabilities().
MCP инструменты всегда включаются (выполняются на сервере).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codelab.server.tools.base import ToolDefinition

if TYPE_CHECKING:
    from codelab.server.protocol.state import ClientRuntimeCapabilities


# Инструменты с этими kind — серверные, не требуют client capabilities.
_SERVER_SIDE_TOOL_KINDS: frozenset[str] = frozenset({"think", "plan"})


class ToolFilter:
    """Фильтрует инструменты по capabilities клиента и MCP.

    Правила:
    - Серверные инструменты (think, plan) всегда доступны
    - MCP инструменты всегда доступны (выполняются на сервере)
    - Без capabilities клиента — только серверные + MCP
    - С capabilities — фильтрация по fs_read, fs_write, terminal
    """

    def filter(
        self,
        tools: list[ToolDefinition],
        capabilities: ClientRuntimeCapabilities | None = None,
        mcp_tools: list[ToolDefinition] | None = None,
    ) -> list[ToolDefinition]:
        """Отфильтровать инструменты.

        Args:
            tools: Все зарегистрированные инструменты.
            capabilities: Capabilities клиента из initialize request.
            mcp_tools: MCP инструменты (всегда включаются).

        Returns:
            Отфильтрованный список инструментов.
        """
        filtered: list[ToolDefinition] = []

        for tool in tools:
            # Серверные инструменты всегда доступны
            if tool.kind in _SERVER_SIDE_TOOL_KINDS:
                filtered.append(tool)
                continue

            # Без capabilities — только серверные доступны
            if capabilities is None:
                continue

            # Инструменты файловой системы и терминал
            is_fs_read = (
                tool.name == "fs/read_text_file"
                and capabilities.fs_read
            )
            is_fs_write = (
                tool.name == "fs/write_text_file"
                and capabilities.fs_write
            )
            is_terminal = (
                tool.name.startswith("terminal/")
                and capabilities.terminal
            )
            if is_fs_read or is_fs_write or is_terminal:
                filtered.append(tool)

        # MCP инструменты всегда включаются
        if mcp_tools:
            filtered.extend(mcp_tools)

        return filtered

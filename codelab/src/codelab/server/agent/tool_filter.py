"""ToolFilter — фильтрация инструментов по client capabilities + MCP.

MCP инструменты всегда включаются (выполняются на сервере).
Серверные инструменты (think, plan) всегда доступны.
Клиентские инструменты фильтруются по префиксу имени + kind.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codelab.server.tools.base import ToolDefinition

if TYPE_CHECKING:
    from codelab.server.protocol.state import ClientRuntimeCapabilities


# Инструменты с этими kind — серверные, не требуют client capabilities.
_SERVER_SIDE_TOOL_KINDS: frozenset[str] = frozenset({"think", "plan"})

# Префиксы имён для клиентских инструментов.
_FS_PREFIX = "fs/"
_TERMINAL_PREFIX = "terminal/"


class ToolFilter:
    """Фильтрует инструменты по capabilities клиента и MCP.

    Соответствует ACP spec: doc/Agent Client Protocol/protocol/02-Initialization.md

    Client capabilities (из initialize request):
    - fs.readTextFile  → fs/read_text_file доступен
    - fs.writeTextFile → fs/write_text_file доступен
    - terminal         → все terminal/* методы доступны

    Правила фильтрации:
    - Серверные инструменты (think, plan) всегда доступны
    - MCP инструменты всегда доступны (выполняются на сервере)
    - Без capabilities клиента — только серверные + MCP
    - С capabilities — фильтрация по префиксу + kind:
      - fs/* + kind="read"  → требует capabilities.fs_read
      - fs/* + kind="edit"  → требует capabilities.fs_write
      - terminal/* (любой)  → требует capabilities.terminal

    Масштабируемость:
    kind-based маппинг позволяет добавлять новые fs/* инструменты
    (grep, search, patch, delete, move и т.д.) без изменения кода фильтра.
    Это расширяет spec для будущих инструментов, соответствуя духу
    протокола о capabilities как feature-gate.
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

            # Фильтрация по префиксу + kind (масштабируемо)
            if self._is_supported(tool, capabilities):
                filtered.append(tool)

        # MCP инструменты всегда включаются
        if mcp_tools:
            filtered.extend(mcp_tools)

        return filtered

    def _is_supported(
        self,
        tool: ToolDefinition,
        capabilities: ClientRuntimeCapabilities,
    ) -> bool:
        """Проверить поддерживается ли инструмент клиентом.

        Использует префикс имени + kind для определения required capability.
        Это позволяет добавлять новые инструменты без изменения кода фильтра.

        Args:
            tool: Определение инструмента.
            capabilities: Capabilities клиента.

        Returns:
            True если инструмент поддерживается.
        """
        # Файловые инструменты: fs/* + kind определяет capability
        if tool.name.startswith(_FS_PREFIX):
            return self._fs_tool_supported(tool, capabilities)

        # Терминальные инструменты: terminal/* (любой kind)
        if tool.name.startswith(_TERMINAL_PREFIX):
            return capabilities.terminal

        # Неизвестный префикс — не поддерживается без явной capability
        return False

    def _fs_tool_supported(
        self,
        tool: ToolDefinition,
        capabilities: ClientRuntimeCapabilities,
    ) -> bool:
        """Проверить поддерживается ли fs/* инструмент.

        ACP spec определяет только два fs capability:
        - fs.readTextFile  → fs/read_text_file (kind="read")
        - fs.writeTextFile → fs/write_text_file (kind="edit")

        Для дополнительных fs/* инструментов используется маппинг kind → capability:
        - "edit"  → fs_write (запись/изменение файлов)
        - другие  → fs_read  (по умолчанию: read, search, grep, patch, delete, move)

        Это соответствует духу spec: capabilities как feature-gate для
        категорий операций, а не для конкретных имён инструментов.
        """
        if tool.kind == "edit":
            return capabilities.fs_write
        # kind="read" или любой другой (search, delete, move, etc.)
        # treat as read capability by default
        return capabilities.fs_read

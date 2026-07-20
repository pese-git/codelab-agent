"""Чистый разбор данных tool call в описание изменения файла.

Без Textual и I/O — извлекает file_path/old/new из разнородных форм tool call
(dict или объект, разные ключи параметров) для предпросмотра изменений.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Инструменты, для которых показывается предпросмотр изменения файла.
FILE_CHANGE_TOOLS = frozenset({"write_file", "file_edit", "create_file", "edit_file", "patch_file"})


@dataclass(frozen=True)
class FileChange:
    """Извлечённые из tool call данные для FileChangePreview."""

    file_path: str
    old_content: str
    new_content: str


def _tool_call_id(tool_call: Any) -> Any:
    if isinstance(tool_call, dict):
        return tool_call.get("toolCallId") or tool_call.get("id")
    return getattr(tool_call, "toolCallId", None) or getattr(tool_call, "id", None)


def parse_tool_call_file_change(
    tool_calls: list[Any],
    tool_call_id: str,
) -> FileChange | None:
    """Находит tool call по id и извлекает описание изменения файла.

    Args:
        tool_calls: Список tool calls (dict или объекты) из ChatViewModel.
        tool_call_id: ID искомого tool call.

    Returns:
        FileChange или None, если tool call не найден.
    """
    data: Any = None
    for tool_call in tool_calls:
        if _tool_call_id(tool_call) == tool_call_id:
            data = tool_call
            break

    if data is None:
        return None

    if isinstance(data, dict):
        params = data.get("parameters") or data.get("rawInput") or {}
    else:
        params = getattr(data, "parameters", {}) or {}

    file_path = params.get("path") or params.get("file_path") or params.get("filePath") or "unknown"
    old_content = params.get("old_content") or params.get("oldContent") or ""
    new_content = (
        params.get("content") or params.get("new_content") or params.get("newContent") or ""
    )
    return FileChange(file_path=file_path, old_content=old_content, new_content=new_content)

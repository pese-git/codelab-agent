"""Mapper между domain ToolExecutionResult и ACP content format."""

from __future__ import annotations

from typing import Any

from codelab.server.domain.tool_call import ToolResult
from codelab.server.domain.value_objects import FileLocation
from codelab.server.tools.base import ToolExecutionResult


class ToolResultMapper:
    """Конвертер между domain ToolExecutionResult и ACP content."""

    @staticmethod
    def to_acp_content(result: ToolExecutionResult) -> list[dict[str, Any]]:
        """Конвертировать domain ToolExecutionResult в ACP content blocks."""
        blocks: list[dict[str, Any]] = []
        if result.output:
            blocks.append({"type": "text", "text": result.output})
        if result.metadata and result.metadata.get("diff"):
            blocks.append({
                "type": "diff",
                "path": result.metadata.get("path", ""),
                "diff": result.metadata["diff"],
            })
        return blocks

    @staticmethod
    def from_tool_result(result: ToolExecutionResult) -> ToolResult:
        """Конвертировать ToolExecutionResult в domain ToolResult."""
        return ToolResult(
            locations=list(result.locations),
            raw_output=dict(result.raw_output),
        )

    @staticmethod
    def locations_to_dicts(locations: list[FileLocation]) -> list[dict[str, Any]]:
        """Конвертировать FileLocation в dict format для ACP."""
        return [
            {"path": loc.path, "line": loc.line}
            for loc in locations
        ]

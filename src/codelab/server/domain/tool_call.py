"""Domain model для ToolCall и ToolResult."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .value_objects import FileLocation, ToolCallStatus


@dataclass(frozen=True)
class ToolResult:
    """Domain model для результата выполнения tool call."""

    locations: list[FileLocation] = field(default_factory=list)
    raw_output: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCall:
    """Domain entity — внутреннее представление tool call.

    НЕ является ACP Protocol Model. Для wire format использовать ToolCallState.
    Конвертация через ToolCallMapper.
    """

    id: str
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    status: ToolCallStatus = ToolCallStatus.PENDING
    result: ToolResult | None = None
    locations: list[FileLocation] = field(default_factory=list)
    raw_output: dict[str, Any] = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return self.status in (ToolCallStatus.COMPLETED, ToolCallStatus.FAILED)

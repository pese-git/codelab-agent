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
    # Контент результата для wire (write-фаза D4-b/b3, ADR-006):
    # `content` — payload tool_call_update; `result_content` — извлечённый контент для клиента.
    content: list[dict[str, Any]] = field(default_factory=list)
    result_content: list[dict[str, Any]] = field(default_factory=list)


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
    # Состояние сессии, переехавшее из wire-DTO по семантике (write-фаза D4-b/b3, ADR-006):
    # `kind` — ACP-вид, ключ permission-политики; `title` — display, персистится для replay;
    # `tool_call_id_from_llm` — опаковый корреляционный id для связки с историей.
    kind: str = "other"
    title: str | None = None
    tool_call_id_from_llm: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in (ToolCallStatus.COMPLETED, ToolCallStatus.FAILED)

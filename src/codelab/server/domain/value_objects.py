"""Domain value objects и enums.

Содержит неизменяемые объекты и перечисления для domain layer сервера.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import NewType

SessionId = NewType("SessionId", str)


@dataclass(frozen=True)
class FileLocation:
    """Domain model для file location."""

    path: str
    line: int | None = None

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("path must not be empty")


class ToolCallStatus(enum.StrEnum):
    """Domain enum для статуса tool call.

    Значения совпадают с ACP `ToolCallStatus` (wire), потому что маппер отдаёт
    `.value` напрямую. Прежний доменный `RUNNING = "running"` был артефактом: в
    ACP это `in_progress`, и любое его попадание в wire дало бы невалидный
    статус. `CANCELLED` и `IN_PROGRESS` обязательны — без них
    `ToolCallMapper.to_domain` понижал их до `PENDING` (потеря round-trip).
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class MessageRole(enum.StrEnum):
    """Domain enum для роли сообщения."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class PlanPriority(enum.StrEnum):
    """Domain enum для приоритета плана."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PlanStatus(enum.StrEnum):
    """Domain enum для статуса шага плана."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

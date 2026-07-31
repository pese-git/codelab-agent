"""Domain value objects и enums.

Содержит неизменяемые объекты и перечисления для domain layer сервера.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
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


# Матрица допустимых переходов статуса tool call — единственный источник (фаза D
# ADR-006). Прежде она существовала в трёх копиях (`ToolCallHandler`,
# `prompt.tool_call_state`, неявно в `ToolCall.is_terminal`), причём одна из них
# не логировала отказ — и молчаливый пропуск однажды рассинхронизировал состояние
# с wire-историей. `ToolCallStatus` — `StrEnum`, поэтому таблица одинаково
# отвечает на доменный член и на wire-строку.
ALLOWED_TOOL_CALL_TRANSITIONS: Mapping[ToolCallStatus, frozenset[ToolCallStatus]] = {
    ToolCallStatus.PENDING: frozenset(
        {ToolCallStatus.IN_PROGRESS, ToolCallStatus.CANCELLED, ToolCallStatus.FAILED}
    ),
    ToolCallStatus.IN_PROGRESS: frozenset(
        {ToolCallStatus.COMPLETED, ToolCallStatus.CANCELLED, ToolCallStatus.FAILED}
    ),
    ToolCallStatus.COMPLETED: frozenset(),
    ToolCallStatus.CANCELLED: frozenset(),
    ToolCallStatus.FAILED: frozenset(),
}

TERMINAL_TOOL_CALL_STATUSES: frozenset[ToolCallStatus] = frozenset(
    status for status, next_states in ALLOWED_TOOL_CALL_TRANSITIONS.items() if not next_states
)


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

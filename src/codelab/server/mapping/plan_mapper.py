"""Mapper между domain PlanEntry и ACP plan format."""

from __future__ import annotations

from typing import Any

from codelab.server.domain.plan import PlanEntry
from codelab.server.domain.value_objects import PlanPriority, PlanStatus


class PlanMapper:
    """Конвертер между domain PlanEntry и ACP plan format."""

    @staticmethod
    def to_acp(entries: list[PlanEntry]) -> list[dict[str, Any]]:
        """Конвертировать domain PlanEntry в ACP format."""
        return [
            {
                "content": entry.content,
                "priority": entry.priority.value,
                "status": entry.status.value,
            }
            for entry in entries
        ]

    @staticmethod
    def from_acp(blocks: list[dict[str, Any]]) -> list[PlanEntry]:
        """Конвертировать ACP format в domain PlanEntry."""
        result: list[PlanEntry] = []
        for block in blocks:
            try:
                priority = PlanPriority(block.get("priority", "medium"))
            except ValueError:
                priority = PlanPriority.MEDIUM
            try:
                status = PlanStatus(block.get("status", "pending"))
            except ValueError:
                status = PlanStatus.PENDING
            result.append(
                PlanEntry(
                    content=block.get("content", ""),
                    priority=priority,
                    status=status,
                )
            )
        return result

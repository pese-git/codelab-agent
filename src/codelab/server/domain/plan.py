"""Domain model для шага плана."""

from __future__ import annotations

from dataclasses import dataclass

from .value_objects import PlanPriority, PlanStatus


@dataclass(frozen=True)
class PlanEntry:
    """Domain model для шага плана.

    Соответствует ACP спецификации (11-Agent Plan):
    - content вместо description
    - priority вместо step_number
    - status с значениями PENDING, IN_PROGRESS, COMPLETED
    """

    content: str
    priority: PlanPriority = PlanPriority.MEDIUM
    status: PlanStatus = PlanStatus.PENDING

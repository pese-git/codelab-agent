"""Mapper между domain PlanEntry и ACP plan format."""

from __future__ import annotations

from typing import Any

import structlog
from pydantic import BaseModel

from codelab.server.domain.plan import PlanEntry
from codelab.server.domain.value_objects import PlanPriority, PlanStatus

logger = structlog.get_logger()

_ACP_PRIORITIES = frozenset(item.value for item in PlanPriority)
_ACP_STATUSES = frozenset(item.value for item in PlanStatus)


class PlanMapper:
    """Единственный шов Plan↔ACP (фаза B ADR-006).

    ACP 11-Agent Plan требует у каждой записи все три поля
    (``content``/``priority``/``status``), поэтому любая форма плана —
    доменная, wire-DTO или сырой dict — приводится к ней здесь, а не
    сериализуется по месту.
    """

    @staticmethod
    def to_acp(entries: list[PlanEntry]) -> list[dict[str, Any]]:
        """Конвертировать domain PlanEntry в ACP format."""
        return [_domain_entry_to_acp(entry) for entry in entries]

    @staticmethod
    def entries_to_acp(entries: list[Any]) -> list[dict[str, Any]]:
        """Привести смешанный план к ACP format.

        Принимает доменные `PlanEntry`, wire-модели (`PlanStep`) и сырые dict:
        `SessionState.latest_plan` шире доменного типа, а на переключении
        резидента (фаза D) в тот же путь придут доменные записи.
        """
        acp_entries: list[dict[str, Any]] = []
        for entry in entries:
            if isinstance(entry, PlanEntry):
                acp_entries.append(_domain_entry_to_acp(entry))
            elif isinstance(entry, BaseModel):
                acp_entries.append(_normalize_acp_fields(entry.model_dump(exclude_none=True)))
            elif isinstance(entry, dict):
                acp_entries.append(_normalize_acp_fields(entry))
            else:
                logger.warning(
                    "plan_entry_dropped_unknown_type",
                    entry_type=type(entry).__name__,
                )
        return acp_entries

    @staticmethod
    def from_acp(blocks: list[dict[str, Any]]) -> list[PlanEntry]:
        """Конвертировать ACP format в domain PlanEntry.

        Невалидные значения заменяются дефолтами (загрузка старой сессии не
        должна падать), но замена логируется: молчаливый откат уже стоил
        нескольких незамеченных расхождений wire↔состояние.
        """
        result: list[PlanEntry] = []
        for block in blocks:
            raw_priority = block.get("priority", PlanPriority.MEDIUM.value)
            try:
                priority = PlanPriority(raw_priority)
            except ValueError:
                logger.warning("plan_entry_priority_coerced", raw_priority=raw_priority)
                priority = PlanPriority.MEDIUM
            raw_status = block.get("status", PlanStatus.PENDING.value)
            try:
                status = PlanStatus(raw_status)
            except ValueError:
                logger.warning("plan_entry_status_coerced", raw_status=raw_status)
                status = PlanStatus.PENDING
            result.append(
                PlanEntry(
                    content=block.get("content", ""),
                    priority=priority,
                    status=status,
                )
            )
        return result


def _domain_entry_to_acp(entry: PlanEntry) -> dict[str, Any]:
    """Доменная запись → ACP-запись (все три поля обязательны по ACP)."""
    return {
        "content": entry.content,
        "priority": entry.priority.value,
        "status": entry.status.value,
    }


def _normalize_acp_fields(entry: dict[str, Any]) -> dict[str, Any]:
    """Достроить dict-запись до обязательных полей ACP.

    `description` принимается как источник ``content``: так выглядят
    pre-P2-26 записи (`PlanStep`), а ACP такую форму запрещает.
    """
    content = entry.get("content") or entry.get("description") or entry.get("title") or ""
    raw_priority = entry.get("priority")
    priority = raw_priority if raw_priority in _ACP_PRIORITIES else PlanPriority.MEDIUM.value
    raw_status = entry.get("status")
    status = raw_status if raw_status in _ACP_STATUSES else PlanStatus.PENDING.value
    return {"content": content, "priority": priority, "status": status}

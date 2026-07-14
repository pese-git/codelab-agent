"""Нормализация raw-значений prompt-turn к каноническим формам ACP.

Leaf-слой без зависимостей от других prompt-модулей: разрывает цикл между
directives и tool-call логикой (обе используют эти нормализаторы).
"""
from __future__ import annotations

from typing import Any


def normalize_stop_reason(stop_reason: str, supported_stop_reasons: set[str] | None = None) -> str:
    """Нормализует stopReason к поддерживаемому значению ACP.

    Пример использования:
        reason = normalize_stop_reason("max_tokens")
    """

    if supported_stop_reasons is None:
        supported_stop_reasons = {
            "end_turn",
            "max_tokens",
            "max_turn_requests",
            "refusal",
            "cancelled",
        }

    if stop_reason in supported_stop_reasons:
        return stop_reason
    return "end_turn"


def resolve_tool_title(kind: str) -> str:
    """Возвращает человекочитаемый title для tool-call по kind.

    Пример использования:
        title = resolve_tool_title("execute")
    """

    titles = {
        "read": "Tool read operation",
        "edit": "Tool edit operation",
        "delete": "Tool delete operation",
        "move": "Tool move operation",
        "execute": "Tool execution",
        "search": "Tool search operation",
        "think": "Tool reasoning step",
        "fetch": "Tool fetch operation",
        "switch_mode": "Tool mode switch",
        "other": "Tool operation",
    }
    return titles.get(kind, "Tool operation")


def normalize_tool_kind(candidate: str, supported_tool_kinds: set[str] | None = None) -> str | None:
    """Нормализует tool kind к поддерживаемому множеству ACP.

    Пример использования:
        kind = normalize_tool_kind("write")
    """

    if supported_tool_kinds is None:
        supported_tool_kinds = {
            "read",
            "edit",
            "delete",
            "move",
            "search",
            "execute",
            "think",
            "fetch",
            "switch_mode",
            "other",
        }

    normalized = "edit" if candidate == "write" else candidate
    if normalized in supported_tool_kinds:
        return normalized
    return None


def normalize_plan_entries(raw_entries: Any) -> list[dict[str, str]] | None:
    """Нормализует structured `planEntries` из `_meta.promptDirectives`.

    Пример использования:
        entries = normalize_plan_entries(raw_entries)
    """

    if not isinstance(raw_entries, list) or not raw_entries:
        return None

    normalized_entries: list[dict[str, str]] = []
    allowed_priorities = {"low", "medium", "high"}
    allowed_statuses = {"pending", "in_progress", "completed", "cancelled"}
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        content = entry.get("content")
        if not isinstance(content, str) or not content.strip():
            continue

        raw_priority = entry.get("priority")
        priority = raw_priority if isinstance(raw_priority, str) else "medium"
        if priority not in allowed_priorities:
            priority = "medium"

        raw_status = entry.get("status")
        status = raw_status if isinstance(raw_status, str) else "pending"
        if status not in allowed_statuses:
            status = "pending"

        normalized_entries.append(
            {
                "content": content.strip(),
                "priority": priority,
                "status": status,
            }
        )

    return normalized_entries or None

"""Поверхность turn-пути над мутациями tool call доменного агрегата.

Создание записи и смена статуса делегируются `ToolCallRegistry` (фаза D шаг 3
ADR-006): счётчик, форма записи и матрица переходов принадлежат домену. Модуль
остаётся ради поверхности вызывающих — им нужны только `title`/`kind`/`status`.
"""

from __future__ import annotations

from typing import Any

from ....domain.session import Session
from ....domain.value_objects import ToolCallStatus


def create_tool_call(
    session: Session, *, title: str, kind: str, status: str = "pending"
) -> str:
    """Создает запись нового tool call в состоянии сессии.

    `status` нужен вызывающим, у которых вызов начинает работу в тот же момент,
    когда создаётся: client-RPC уходит клиенту вместе с нотификацией о создании,
    и `pending` для него — состояние, которого не бывает.

    Пример использования:
        tool_call_id = create_tool_call(state, title="Demo", kind="other")
    """

    tool_call = session.tool_calls.create(
        "",
        {},
        title=title,
        kind=kind,
        status=ToolCallStatus(status),
    )
    return tool_call.id


def update_tool_call_status(
    session: Session,
    tool_call_id: str,
    status: str,
    *,
    content: list[dict[str, Any]] | None = None,
) -> None:
    """Обновляет статус tool call с проверкой допустимых переходов.

    Пример использования:
        update_tool_call_status(state, "call_001", "in_progress")
    """

    session.tool_calls.update_status(tool_call_id, ToolCallStatus(status), content=content)

"""Поверхность turn-пути над мутациями tool call доменного агрегата.

Создание записи и смена статуса делегируются `ToolCallRegistry` (фаза D шаг 3
ADR-006): счётчик, форма записи и матрица переходов принадлежат домену. Модуль
остаётся ради поверхности вызывающих — им нужны только `title`/`kind`/`status`.
"""

from __future__ import annotations

from typing import Any

from ....domain.session import Session
from ....domain.value_objects import ToolCallStatus
from ..event_history_writer import EventHistoryWriter


def create_tool_call(
    session: Session, *, title: str, kind: str, status: str = "pending"
) -> str:
    """Создает запись нового tool call в состоянии сессии и в журнале.

    `status` нужен вызывающим, у которых вызов начинает работу в тот же момент,
    когда создаётся: client-RPC уходит клиенту вместе с нотификацией о создании,
    и `pending` для него — состояние, которого не бывает.

    Создание и событие журнала неразделимы (шаг 4g ADR-008), как ответ модели и
    его запись в `ToolCallHandler.answer_tool_call`. С 4g реестр вызовов —
    проекция журнала, и вызов, созданный без события, исчезает на следующей же
    команде: в памяти он виден, а команда загружает свежий агрегат с диска. Так
    и вышло — 33 теста упали ровно на этом, пока писали только вызывающие.

    Имени инструмента и аргументов у этих вызовов нет: это вызовы client-RPC и
    директив, инструмент реестра за ними не стоит.

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
    EventHistoryWriter().save_tool_call(
        session,
        tool_call_id=tool_call.id,
        title=title,
        kind=kind,
        status=status,
    )
    return tool_call.id


def update_tool_call_status(
    session: Session,
    tool_call_id: str,
    status: str,
    *,
    content: list[dict[str, Any]] | None = None,
) -> bool:
    """Обновляет статус tool call с проверкой допустимых переходов и пишет событие.

    Событие пишется только при принятом переходе (шаг 4g ADR-008): статус —
    проекция журнала, и запись об отклонённом переходе сделала бы проекцию
    описанием того, чего не было. Обратное — переход без события — теряет
    статус на следующей команде: так вызов терминала оставался `pending`, и
    завершение упиралось в запрет `pending → completed`.
    """

    changed = session.tool_calls.update_status(
        tool_call_id, ToolCallStatus(status), content=content
    )
    if changed:
        EventHistoryWriter().save_tool_call_update(
            session,
            tool_call_id=tool_call_id,
            status=status,
            content=content,
        )
    return changed

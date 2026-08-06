"""Запись событий журнала сессии (write-половина turn-пути).

Писатель принимает вызовы turn-пути и превращает их в **доменные события**
(`domain/journal.py`); форму записи знает проекция (`mapping/journal_mapper.py`).
Прежнее решение ADR-006 — «элементы `events_history` суть готовые ACP-нотификации,
поэтому модуль навсегда остаётся wire-границей» — **отменено** шагом 3a ADR-008:
журнал стал доменным, ACP — его проекцией. Wire-форма записи шагом 3a не
изменилась, поэтому документ читается и пишется как раньше.

Раньше запись и воспроизведение жили в одном `ReplayManager`, хотя наборы
методов не пересекались: писатели обслуживают prompt-turn и resume,
читатели — `session/load` (расщепление двуликих фасадов, фаза C ADR-006).
Читающая половина — `SessionReplayer`, и теперь обе половины ходят через одну
проекцию.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from codelab.server.mapping.journal_mapper import JournalMapper
from codelab.server.storage.document import SessionDocument

from ...domain.journal import (
    AgentMessageRecorded,
    JournalEntry,
    PlanRecorded,
    SessionEvent,
    SessionInfoRecorded,
    ToolCallStarted,
    ToolCallStatusChanged,
    UserMessageRecorded,
)
from ...domain.session import Session as DomainSession

logger = structlog.get_logger()


class EventHistoryWriter:
    """Пишет `session/update` в `events_history` сессии.

    Пример использования:
        >>> writer = EventHistoryWriter()
        >>> writer.save_agent_message_chunk(session, {"type": "text", "text": "..."})
        >>> writer.save_tool_call(session, "call_001", "Read file", "read", "pending")
    """

    def save_user_message_chunk(
        self,
        session: DomainSession,
        content: dict[str, Any],
    ) -> None:
        """Сохраняет user_message_chunk в events_history.

        Пишется по одному событию на блок промпта: реплей отдаёт клиенту блоки
        в исходном порядке, поэтому склейка недопустима.

        Args:
            session: Состояние сессии
            content: Content block промпта (text/resource/image)
        """
        self._append(session, UserMessageRecorded(content=content))

    def save_agent_message_chunk(
        self,
        session: DomainSession,
        content: dict[str, Any],
    ) -> None:
        """Сохраняет agent_message_chunk в events_history.

        Args:
            session: Состояние сессии
            content: Content block (например, {"type": "text", "text": "..."})
        """
        self._append(session, AgentMessageRecorded(content=content))

    def save_tool_call(
        self,
        session: DomainSession,
        tool_call_id: str,
        title: str,
        kind: str,
        status: str,
        *,
        content: list[dict[str, Any]] | None = None,
    ) -> None:
        """Сохраняет tool_call в events_history.

        Args:
            session: Состояние сессии
            tool_call_id: ID tool call
            title: Заголовок для UI
            kind: Категория tool (read, edit, execute, etc.)
            status: Начальный статус (обычно "pending")
            content: Опциональный контент tool call
        """
        self._append(
            session,
            ToolCallStarted(
                tool_call_id=tool_call_id,
                title=title,
                kind=kind,
                status=status,
                content=content,
            ),
        )

    def save_tool_call_update(
        self,
        session: SessionDocument | DomainSession,
        tool_call_id: str,
        status: str,
        *,
        content: list[dict[str, Any]] | None = None,
    ) -> None:
        """Сохраняет tool_call_update в events_history.

        Единственный метод писателя, принимающий обе модели: turn-путь и транзакции
        фазы D пишут доменным агрегатом, а wire-ветка остаётся ради последнего
        не переведённого писателя — отмены вызовов при переключении сессии
        (`handlers.session`). Снимается вместе с ним.

        Args:
            session: Состояние сессии (wire-DTO или доменный агрегат)
            tool_call_id: ID tool call
            status: Новый статус (in_progress, completed, failed, cancelled)
            content: Опциональный контент результата
        """
        self._append(
            session,
            ToolCallStatusChanged(
                tool_call_id=tool_call_id,
                status=status,
                content=content,
            ),
        )

    def save_plan(
        self,
        session: DomainSession,
        entries: list[dict[str, Any]],
    ) -> None:
        """Сохраняет plan update в events_history.

        Args:
            session: Состояние сессии
            entries: Список шагов плана
        """
        self._append(session, PlanRecorded(entries=entries))

    def save_session_info_update(
        self,
        session: DomainSession,
        *,
        title: str | None,
        updated_at: str | None,
    ) -> None:
        """Сохраняет session_info_update в events_history.

        Единственное событие журнала, которое НЕ реплеится: по ACP это патч-канал
        метаданных, а не conversation. Хранится для полноты журнала turn'а.
        Шагом 3a решение выражено конструкцией — у `SessionInfoRecorded` нет
        реплей-формы, вместо прежнего перечисления видов в читателе.

        Args:
            session: Состояние сессии
            title: Заголовок сессии (None — очистка по ACP)
            updated_at: ISO 8601 метка последней активности
        """
        self._append(session, SessionInfoRecorded(title=title, updated_at=updated_at))

    def _append(
        self,
        session: SessionDocument | DomainSession,
        event: SessionEvent,
    ) -> None:
        """Дописывает событие в журнал сессии, отметив время записи.

        Метка времени — свойство записи журнала, не факта диалога, поэтому её
        ставит писатель, а не вызывающий.
        """
        entry = JournalEntry(event=event, timestamp=datetime.now(UTC))
        wire = JournalMapper.to_wire(entry)
        events, session_id = _journal_of(session)
        events.append(wire)

        logger.debug(
            "event appended to session journal",
            session_id=session_id,
            event_type=type(event).__name__,
            update_type=wire["update"].get("sessionUpdate"),
        )


def _journal_of(
    session: SessionDocument | DomainSession,
) -> tuple[list[dict[str, Any]], str]:
    """Журнал событий и id сессии — из wire-DTO либо доменного агрегата.

    Развилка носителя временна и живёт ровно до конца фазы D ADR-006: в обеих
    моделях это один и тот же список записей журнала, а форму записи знает
    проекция. Снять развилку = оставить доменную ветку, когда последний писатель
    уедет с `SessionDocument`.
    """
    if isinstance(session, SessionDocument):
        return session.events_history, session.session_id
    return session.runtime.events_history, str(session.id)

"""Запись `session/update` в `events_history` (write-половина turn-пути).

Владеет ФОРМОЙ события истории: `{"type": "session_update", "update": {...},
"timestamp": ...}`. Элементы `events_history` — готовые ACP-нотификации, поэтому
модуль остаётся на wire-границе навсегда (постоянная wire-граница, ADR-006).

Раньше запись и воспроизведение жили в одном `ReplayManager`, хотя наборы
методов не пересекались: писатели обслуживают prompt-turn и resume,
читатели — `session/load` (расщепление двуликих фасадов, фаза C ADR-006).
Читающая половина — `SessionReplayer`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from ..state import SessionState

logger = structlog.get_logger()


class EventHistoryWriter:
    """Пишет `session/update` в `events_history` сессии.

    Пример использования:
        >>> writer = EventHistoryWriter()
        >>> writer.save_agent_message_chunk(session, {"type": "text", "text": "..."})
        >>> writer.save_tool_call(session, "call_001", "Read file", "read", "pending")
    """

    def save_agent_message_chunk(
        self,
        session: SessionState,
        content: dict[str, Any],
    ) -> None:
        """Сохраняет agent_message_chunk в events_history.

        Args:
            session: Состояние сессии
            content: Content block (например, {"type": "text", "text": "..."})
        """
        self._append(
            session,
            {
                "sessionUpdate": "agent_message_chunk",
                "content": content,
            },
        )

    def save_tool_call(
        self,
        session: SessionState,
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
        update: dict[str, Any] = {
            "sessionUpdate": "tool_call",
            "toolCallId": tool_call_id,
            "title": title,
            "kind": kind,
            "status": status,
        }
        if content:
            update["content"] = content
        self._append(session, update)

    def save_tool_call_update(
        self,
        session: SessionState,
        tool_call_id: str,
        status: str,
        *,
        content: list[dict[str, Any]] | None = None,
    ) -> None:
        """Сохраняет tool_call_update в events_history.

        Args:
            session: Состояние сессии
            tool_call_id: ID tool call
            status: Новый статус (in_progress, completed, failed, cancelled)
            content: Опциональный контент результата
        """
        update: dict[str, Any] = {
            "sessionUpdate": "tool_call_update",
            "toolCallId": tool_call_id,
            "status": status,
        }
        if content:
            update["content"] = content
        self._append(session, update)

    def save_plan(
        self,
        session: SessionState,
        entries: list[dict[str, Any]],
    ) -> None:
        """Сохраняет plan update в events_history.

        Args:
            session: Состояние сессии
            entries: Список шагов плана
        """
        self._append(
            session,
            {
                "sessionUpdate": "plan",
                "entries": entries,
            },
        )

    def _append(
        self,
        session: SessionState,
        update: dict[str, Any],
    ) -> None:
        """Добавляет `session/update` в events_history со временной меткой."""
        event_entry = {
            "type": "session_update",
            "update": update,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        session.events_history.append(event_entry)

        logger.debug(
            "update saved to events_history",
            session_id=session.session_id,
            update_type=update.get("sessionUpdate"),
        )

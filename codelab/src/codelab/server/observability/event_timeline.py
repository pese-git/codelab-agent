"""EventTimeline — хронология событий сессии для observability.

Подписывается на AbstractEventBus для автоматической записи событий.
Используется в debug mode для инспекции полной истории событий.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codelab.server.agent.contracts.base import DomainEvent
    from codelab.server.agent.event_bus.abstract import AbstractEventBus

logger = logging.getLogger(__name__)


@dataclass
class TimelineEvent:
    """Одно событие в timeline сессии.

    Attributes:
        timestamp: Время события (time.time()).
        event_type: Имя типа события.
        session_id: ID сессии.
        details: Payload события (dict).
    """

    timestamp: float = field(default_factory=time.time)
    event_type: str = ""
    session_id: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, debug: bool = False) -> dict[str, Any]:
        """Сериализация в dict.

        Args:
            debug: Если True, включает полный payload.
        """
        result: dict[str, Any] = {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "session_id": self.session_id,
        }
        if debug:
            result["details"] = dict(self.details)
        else:
            result["detail_keys"] = list(self.details.keys())
        return result


class EventTimeline:
    """Хронология событий сессии.

    Подписывается на AbstractEventBus для автоматической записи
    lifecycle событий агентов.

    Attributes:
        debug: Если True, сохраняет полные payload'ы.
    """

    # События, на которые подписываемся автоматически
    AUTO_SUBSCRIBE_EVENTS = (
        "AgentRegistered",
        "AgentUnregistered",
        "AgentListChanged",
        "AgentResponse",
    )

    def __init__(self, debug: bool = False) -> None:
        self.debug = debug
        self._events: list[TimelineEvent] = []
        self._subscriptions: list[Any] = []  # Subscription objects
        self._exported_count: int = 0

    def record_event(
        self,
        event_type: str,
        session_id: str,
        details: dict[str, Any] | None = None,
    ) -> TimelineEvent:
        """Записать событие в timeline.

        Args:
            event_type: Имя типа события.
            session_id: ID сессии.
            details: Payload события.

        Returns:
            Созданный TimelineEvent.
        """
        event = TimelineEvent(
            event_type=event_type,
            session_id=session_id,
            details=details or {},
        )
        self._events.append(event)
        logger.debug("Timeline event: %s (session=%s)", event_type, session_id)
        return event

    def get_events(self, session_id: str | None = None) -> list[TimelineEvent]:
        """Получить события, опционально фильтруя по session_id.

        Args:
            session_id: Фильтр по сессии (None = все).

        Returns:
            Список TimelineEvent, отсортированный по времени.
        """
        if session_id is None:
            return list(self._events)
        return [e for e in self._events if e.session_id == session_id]

    def subscribe_to_bus(self, bus: AbstractEventBus) -> None:
        """Подписаться на события EventBus для автоматической записи.

        Args:
            bus: Экземпляр AbstractEventBus.
        """
        from codelab.server.agent.contracts.base import (
            AgentListChanged,
            AgentRegistered,
            AgentResponse,
            AgentUnregistered,
        )

        event_map = {
            "AgentRegistered": AgentRegistered,
            "AgentUnregistered": AgentUnregistered,
            "AgentListChanged": AgentListChanged,
            "AgentResponse": AgentResponse,
        }

        for event_name, event_type in event_map.items():

            async def handler(event: DomainEvent, name: str = event_name) -> None:
                details = self._extract_details(event)
                self.record_event(
                    event_type=name,
                    session_id=event.session_id,
                    details=details,
                )

            sub = bus.subscribe(event_type, handler)  # type: ignore[arg-type]
            self._subscriptions.append(sub)

    def _extract_details(self, event: DomainEvent) -> dict[str, Any]:
        """Извлечь детали из DomainEvent для timeline.

        В debug mode — все поля, в обычном — только summary.
        """
        if self.debug:
            # Полный payload
            return {
                k: v
                for k, v in event.__dict__.items()
                if not k.startswith("_")
            }
        else:
            # Минимальные детали
            return {"session_id": event.session_id}

    def clear(self) -> None:
        """Очистить все события.

        НЕ отписывается от шины (подписки сохраняются).
        """
        self._events.clear()
        self._exported_count = 0

    def mark_exported(self, count: int) -> None:
        """Отметить количество экспортированных событий.

        Вызывается экспортером после успешного экспорта.
        Отмечает первые N событий как экспортированные.

        Args:
            count: Количество экспортированных событий.
        """
        self._exported_count = min(count, len(self._events))

    def clear_exported(self) -> None:
        """Удалить экспортированные события.

        Удаляет только события, которые были экспортированы.
        Подписки на EventBus не затрагиваются.
        """
        if self._exported_count > 0:
            self._events = self._events[self._exported_count:]
            self._exported_count = 0

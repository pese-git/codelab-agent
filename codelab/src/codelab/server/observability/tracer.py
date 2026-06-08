"""Tracing для мультиагентной observability.

Реализует span hierarchy с context propagation:
- SpanContext — контекст одного span'а
- Tracer — управление span'ами (start/end/current)

Span hierarchy: strategy_execution → bus_request → llm_call → tool_execution
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SpanContext:
    """Контекст одного span'а в иерархии трейсов.

    Attributes:
        span_id: Уникальный идентификатор span'а.
        name: Имя span'а (например, "llm_call", "bus_request").
        parent_id: ID родительского span'а (None для root).
        attributes: Произвольные key-value атрибуты.
        start_time: Время создания (time.time()).
        end_time: Время завершения (None если активен).
        session_id: ID сессии для корреляции.
    """

    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    name: str = ""
    parent_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    session_id: str = ""

    @property
    def duration_ms(self) -> float | None:
        """Длительность span'а в миллисекундах."""
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000

    def to_dict(self, debug: bool = False) -> dict[str, Any]:
        """Сериализация в dict.

        Args:
            debug: Если True, включает все атрибуты.
        """
        result: dict[str, Any] = {
            "span_id": self.span_id,
            "name": self.name,
            "parent_id": self.parent_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "session_id": self.session_id,
        }
        if debug:
            result["attributes"] = dict(self.attributes)
        elif self.attributes:
            # В non-debug режиме — только summary
            result["attribute_count"] = len(self.attributes)
        return result


class Tracer:
    """Tracer для управления span hierarchy.

    Поддерживает вложенные span'ы через стек активных span'ов.
    При создании дочернего span'а автоматически устанавливает parent_id.

    Attributes:
        debug: Если True, сохраняет полные атрибуты span'ов.
    """

    def __init__(self, debug: bool = False) -> None:
        self.debug = debug
        self._active_spans: list[SpanContext] = []
        self._completed_spans: list[SpanContext] = []

    def start_span(
        self,
        name: str,
        parent: SpanContext | None = None,
        session_id: str = "",
    ) -> SpanContext:
        """Создать и активировать новый span.

        Args:
            name: Имя span'а.
            parent: Родительский контекст (или текущий активный span).
            session_id: ID сессии.

        Returns:
            Новый SpanContext.
        """
        # Определяем родителя
        if parent is not None:
            parent_id = parent.span_id
        elif self._active_spans:
            parent_id = self._active_spans[-1].span_id
        else:
            parent_id = None

        span = SpanContext(
            name=name,
            parent_id=parent_id,
            session_id=session_id,
        )
        self._active_spans.append(span)
        logger.debug("Span started: %s (%s)", name, span.span_id)
        return span

    def end_span(self, span: SpanContext, attributes: dict[str, Any] | None = None) -> None:
        """Завершить span и записать атрибуты.

        Args:
            span: SpanContext для завершения.
            attributes: Дополнительные атрибуты.
        """
        span.end_time = time.time()
        if attributes:
            span.attributes.update(attributes)

        # Удаляем из активных
        if span in self._active_spans:
            self._active_spans.remove(span)

        self._completed_spans.append(span)
        logger.debug(
            "Span ended: %s (%s) duration=%.1fms",
            span.name,
            span.span_id,
            span.duration_ms or 0,
        )

    def get_current_span(self) -> SpanContext | None:
        """Вернуть текущий активный span (верх стека)."""
        return self._active_spans[-1] if self._active_spans else None

    def get_completed_spans(self, session_id: str | None = None) -> list[SpanContext]:
        """Вернуть завершённые span'ы, опционально фильтруя по session_id."""
        if session_id is None:
            return list(self._completed_spans)
        return [s for s in self._completed_spans if s.session_id == session_id]

    def clear(self) -> None:
        """Очистить все span'ы."""
        self._active_spans.clear()
        self._completed_spans.clear()

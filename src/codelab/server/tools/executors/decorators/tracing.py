"""Tracing для tool executors.

Предоставляет lightweight distributed tracing: trace spans
с parent-child relationships, trace IDs, timing.
"""

from __future__ import annotations

import contextvars
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.tools.base import ToolExecutionResult

from .base import ToolExecutorDecorator, ToolExecutorProtocol

if TYPE_CHECKING:
    from codelab.server.protocol.state import SessionState

logger = structlog.get_logger()


class SpanStatus(Enum):
    OK = "ok"
    ERROR = "error"


@dataclass
class TraceSpan:
    """Span — единица трассировки выполнения инструмента."""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    tool_name: str
    session_id: str
    start_time_ms: float
    end_time_ms: float = 0.0
    duration_ms: float = 0.0
    status: SpanStatus = SpanStatus.OK
    error_message: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def finish(self, success: bool, error_message: str | None = None) -> None:
        self.end_time_ms = time.perf_counter() * 1000
        self.duration_ms = self.end_time_ms - self.start_time_ms
        self.status = SpanStatus.OK if success else SpanStatus.ERROR
        self.error_message = error_message

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "tool_name": self.tool_name,
            "session_id": self.session_id,
            "start_time_ms": round(self.start_time_ms, 2),
            "end_time_ms": round(self.end_time_ms, 2),
            "duration_ms": round(self.duration_ms, 2),
            "status": self.status.value,
        }
        if self.error_message:
            result["error_message"] = self.error_message
        if self.attributes:
            result["attributes"] = self.attributes
        return result


class TraceRecorder:
    """Хранилище trace spans.

    Thread-safe: использует lock для конкурентного доступа.
    """

    def __init__(self, max_spans: int = 10000) -> None:
        self._spans: list[TraceSpan] = []
        self._lock = threading.Lock()
        self._max_spans = max_spans

    def record(self, span: TraceSpan) -> None:
        with self._lock:
            if len(self._spans) >= self._max_spans:
                self._spans = self._spans[-self._max_spans // 2 :]
            self._spans.append(span)

    def get_spans_by_trace_id(self, trace_id: str) -> list[TraceSpan]:
        with self._lock:
            return [s for s in self._spans if s.trace_id == trace_id]

    def get_spans_by_session_id(self, session_id: str) -> list[TraceSpan]:
        with self._lock:
            return [s for s in self._spans if s.session_id == session_id]

    def get_recent_spans(self, limit: int = 100) -> list[TraceSpan]:
        with self._lock:
            return list(self._spans[-limit:])

    def get_all_spans(self) -> list[TraceSpan]:
        with self._lock:
            return list(self._spans)

    def reset(self) -> None:
        with self._lock:
            self._spans.clear()


_global_recorder = TraceRecorder()


def get_global_trace_recorder() -> TraceRecorder:
    return _global_recorder


def generate_trace_id() -> str:
    return uuid.uuid4().hex


def generate_span_id() -> str:
    return uuid.uuid4().hex[:16]


_current_span_context: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "trace_span_context", default=None,
)


class TracingDecorator(ToolExecutorDecorator):
    """Создаёт trace span для каждого выполнения инструмента.

    Генерирует trace_id (если нет parent context) и span_id.
    Записывает TraceSpan в TraceRecorder с timing и status.

    Example:
        >>> recorder = TraceRecorder()
        >>> executor = TracingDecorator(base_executor, recorder=recorder)
        >>> result = await executor.execute(session, arguments)
        >>> spans = recorder.get_recent_spans()
    """

    def __init__(
        self,
        wrapped: ToolExecutorProtocol,
        recorder: TraceRecorder | None = None,
    ) -> None:
        super().__init__(wrapped)
        self._recorder = recorder or get_global_trace_recorder()

    async def execute(
        self,
        session: SessionState,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        tool_name = arguments.get("tool_name", "unknown")

        parent_ctx = _current_span_context.get()
        trace_id = parent_ctx["trace_id"] if parent_ctx else generate_trace_id()
        parent_span_id = parent_ctx["span_id"] if parent_ctx else None
        span_id = generate_span_id()

        span = TraceSpan(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            tool_name=tool_name,
            session_id=session.session_id,
            start_time_ms=time.perf_counter() * 1000,
        )

        ctx_value = {"trace_id": trace_id, "span_id": span_id}
        token = _current_span_context.set(ctx_value)

        try:
            result = await self._wrapped.execute(session, arguments)
            span.finish(success=result.success, error_message=result.error)
            return result

        except Exception as exc:
            span.finish(success=False, error_message=str(exc))
            raise

        finally:
            _current_span_context.reset(token)
            self._recorder.record(span)

            logger.debug(
                "trace_span_finished",
                trace_id=trace_id,
                span_id=span_id,
                tool_name=tool_name,
                duration_ms=round(span.duration_ms, 2),
                status=span.status.value,
                session_id=session.session_id,
            )

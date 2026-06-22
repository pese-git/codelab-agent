"""Метрики для tool executors.

Предоставляет in-memory сбор метрик выполнения инструментов:
duration, success/failure counts, per-tool статистика.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.tools.base import ToolExecutionResult

from .base import ToolExecutorDecorator, ToolExecutorProtocol

if TYPE_CHECKING:
    from codelab.server.protocol.state import SessionState

logger = structlog.get_logger()


@dataclass
class ToolMetrics:
    """Метрики выполнения конкретного инструмента."""

    tool_name: str
    total_calls: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_duration_ms: float = 0.0
    min_duration_ms: float = field(default_factory=lambda: float("inf"))
    max_duration_ms: float = 0.0

    @property
    def avg_duration_ms(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_duration_ms / self.total_calls

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.success_count / self.total_calls

    def record(self, duration_ms: float, success: bool) -> None:
        self.total_calls += 1
        self.total_duration_ms += duration_ms
        if duration_ms < self.min_duration_ms:
            self.min_duration_ms = duration_ms
        if duration_ms > self.max_duration_ms:
            self.max_duration_ms = duration_ms
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "total_calls": self.total_calls,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": round(self.success_rate, 4),
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "min_duration_ms": round(self.min_duration_ms, 2) if self.total_calls > 0 else 0.0,
            "max_duration_ms": round(self.max_duration_ms, 2),
            "total_duration_ms": round(self.total_duration_ms, 2),
        }


class MetricsCollector:
    """Агрегатор метрик выполнения инструментов.

    Thread-safe: использует lock для конкурентного доступа.
    """

    def __init__(self) -> None:
        self._metrics: dict[str, ToolMetrics] = {}
        self._lock = threading.Lock()

    def record(self, tool_name: str, duration_ms: float, success: bool) -> None:
        with self._lock:
            if tool_name not in self._metrics:
                self._metrics[tool_name] = ToolMetrics(tool_name=tool_name)
            self._metrics[tool_name].record(duration_ms, success)

    def get_tool_metrics(self, tool_name: str) -> ToolMetrics | None:
        with self._lock:
            return self._metrics.get(tool_name)

    def get_all_metrics(self) -> dict[str, ToolMetrics]:
        with self._lock:
            return dict(self._metrics)

    def get_summary(self) -> dict[str, Any]:
        with self._lock:
            total_calls = sum(m.total_calls for m in self._metrics.values())
            total_success = sum(m.success_count for m in self._metrics.values())
            total_failure = sum(m.failure_count for m in self._metrics.values())
            total_duration = sum(m.total_duration_ms for m in self._metrics.values())

            return {
                "total_tools": len(self._metrics),
                "total_calls": total_calls,
                "total_success": total_success,
                "total_failure": total_failure,
                "overall_success_rate": (
                    round(total_success / total_calls, 4) if total_calls > 0 else 0.0
                ),
                "total_duration_ms": round(total_duration, 2),
                "tools": {name: m.to_dict() for name, m in self._metrics.items()},
            }

    def reset(self) -> None:
        with self._lock:
            self._metrics.clear()


_global_collector = MetricsCollector()


def get_global_metrics_collector() -> MetricsCollector:
    return _global_collector


class MetricsDecorator(ToolExecutorDecorator):
    """Собирает метрики выполнения инструмента.

    Замеряет duration, считает success/failure, агрегирует per-tool статистику.
    Результаты записываются в MetricsCollector.

    Example:
        >>> collector = MetricsCollector()
        >>> executor = MetricsDecorator(base_executor, collector=collector)
        >>> result = await executor.execute(session, arguments)
        >>> print(collector.get_summary())
    """

    def __init__(
        self,
        wrapped: ToolExecutorProtocol,
        collector: MetricsCollector | None = None,
    ) -> None:
        super().__init__(wrapped)
        self._collector = collector or get_global_metrics_collector()

    async def execute(
        self,
        session: SessionState,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        tool_name = arguments.get("tool_name", "unknown")
        start = time.perf_counter()

        try:
            result = await self._wrapped.execute(session, arguments)
            duration_ms = (time.perf_counter() - start) * 1000

            self._collector.record(tool_name, duration_ms, result.success)

            logger.debug(
                "tool_metrics_recorded",
                tool_name=tool_name,
                duration_ms=round(duration_ms, 2),
                success=result.success,
                session_id=session.session_id,
            )

            return result

        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            self._collector.record(tool_name, duration_ms, False)

            logger.debug(
                "tool_metrics_recorded",
                tool_name=tool_name,
                duration_ms=round(duration_ms, 2),
                success=False,
                session_id=session.session_id,
            )

            raise

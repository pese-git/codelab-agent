"""MetricsTracker — автоматический сбор метрик для мультиагентной observability.

Подписывается на AbstractEventBus для автосбора метрик.
Хранит метрики по сессиям для мониторинга и анализа.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codelab.server.agent.contracts.base import DomainEvent, TokenUsage
    from codelab.server.agent.event_bus.abstract import AbstractEventBus

logger = logging.getLogger(__name__)


@dataclass
class SessionMetrics:
    """Агрегированные метрики одной сессии.

    Attributes:
        session_id: ID сессии.
        bus_dispatch_count: Количество dispatch операций.
        bus_dispatch_total_ms: Суммарное время dispatch.
        llm_call_count: Количество LLM вызовов.
        llm_total_input_tokens: Всего входных токенов.
        llm_total_output_tokens: Всего выходных токенов.
        compression_count: Количество compressions.
        compression_total_ratio: Суммарный compression ratio.
        slicer_count: Количество slicing операций.
        slicer_total_original_tokens: Всего оригинальных токенов.
        slicer_total_sliced_tokens: Всего sliced токенов.
        strategy_execution_count: Количество выполнений стратегий.
        strategy_execution_total_ms: Суммарное время стратегий.
        agent_responses: Количество ответов от агентов.
        agent_errors: Количество ошибок агентов.
    """

    session_id: str = ""
    bus_dispatch_count: int = 0
    bus_dispatch_total_ms: float = 0.0
    llm_call_count: int = 0
    llm_total_input_tokens: int = 0
    llm_total_output_tokens: int = 0
    compression_count: int = 0
    compression_total_ratio: float = 0.0
    slicer_count: int = 0
    slicer_total_original_tokens: int = 0
    slicer_total_sliced_tokens: int = 0
    slicer_total_latency_ms: float = 0.0
    strategy_execution_count: int = 0
    strategy_execution_total_ms: float = 0.0
    agent_responses: int = 0
    agent_errors: int = 0

    # Debug mode — детальные записи
    dispatch_details: list[dict[str, Any]] = field(default_factory=list)
    llm_call_details: list[dict[str, Any]] = field(default_factory=list)
    agent_response_details: list[dict[str, Any]] = field(default_factory=list)

    @property
    def avg_bus_dispatch_ms(self) -> float:
        if self.bus_dispatch_count == 0:
            return 0.0
        return self.bus_dispatch_total_ms / self.bus_dispatch_count

    @property
    def avg_compression_ratio(self) -> float:
        if self.compression_count == 0:
            return 0.0
        return self.compression_total_ratio / self.compression_count


class MetricsTracker:
    """Автоматический сбор метрик мультиагентной системы.

    Подписывается на AbstractEventBus для автосбора.
    Хранит метрики по сессиям.

    Attributes:
        debug: Если True, сохраняет детальные записи.
    """

    def __init__(self, debug: bool = False) -> None:
        self.debug = debug
        self._sessions: dict[str, SessionMetrics] = {}
        self._subscriptions: list[Any] = []

    def _get_or_create(self, session_id: str) -> SessionMetrics:
        """Получить или создать SessionMetrics."""
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionMetrics(session_id=session_id)
        return self._sessions[session_id]

    def record_bus_dispatch(self, latency_ms: float, target_agent: str, session_id: str) -> None:
        """Записать метрику dispatch.

        Args:
            latency_ms: Время dispatch в мс.
            target_agent: Имя целевого агента.
            session_id: ID сессии.
        """
        metrics = self._get_or_create(session_id)
        metrics.bus_dispatch_count += 1
        metrics.bus_dispatch_total_ms += latency_ms

        if self.debug:
            metrics.dispatch_details.append({
                "target_agent": target_agent,
                "latency_ms": latency_ms,
                "timestamp": time.time(),
            })

    def record_llm_call(
        self,
        latency_ms: float,
        model: str,
        input_tokens: int,
        output_tokens: int,
        session_id: str,
    ) -> None:
        """Записать метрику LLM вызова."""
        metrics = self._get_or_create(session_id)
        metrics.llm_call_count += 1
        metrics.llm_total_input_tokens += input_tokens
        metrics.llm_total_output_tokens += output_tokens

        if self.debug:
            metrics.llm_call_details.append({
                "model": model,
                "latency_ms": latency_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "timestamp": time.time(),
            })

    def record_agent_response(
        self,
        agent_name: str,
        stop_reason: str,
        usage: TokenUsage,
        session_id: str,
    ) -> None:
        """Записать метрику ответа агента."""
        metrics = self._get_or_create(session_id)
        metrics.agent_responses += 1
        metrics.llm_total_input_tokens += usage.input_tokens
        metrics.llm_total_output_tokens += usage.output_tokens

        if stop_reason == "error":
            metrics.agent_errors += 1

        if self.debug:
            metrics.agent_response_details.append({
                "agent_name": agent_name,
                "stop_reason": stop_reason,
                "usage": {
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                },
                "timestamp": time.time(),
            })

    def record_compression(
        self,
        original_tokens: int,
        sliced_tokens: int,
        ratio: float,
        session_id: str,
    ) -> None:
        """Записать метрику compression."""
        metrics = self._get_or_create(session_id)
        metrics.compression_count += 1
        metrics.compression_total_ratio += ratio

    def record_slicer(
        self,
        original_tokens: int,
        sliced_tokens: int,
        latency_ms: float,
        was_skipped: bool,
        session_id: str,
    ) -> None:
        """Записать метрику token slicer."""
        metrics = self._get_or_create(session_id)
        metrics.slicer_count += 1
        metrics.slicer_total_original_tokens += original_tokens
        metrics.slicer_total_sliced_tokens += sliced_tokens
        metrics.slicer_total_latency_ms += latency_ms

    def record_strategy_execution(
        self,
        strategy: str,
        total_time_ms: float,
        session_id: str,
    ) -> None:
        """Записать метрику выполнения стратегии."""
        metrics = self._get_or_create(session_id)
        metrics.strategy_execution_count += 1
        metrics.strategy_execution_total_ms += total_time_ms

    def get_metrics(self, session_id: str) -> SessionMetrics:
        """Получить метрики сессии.

        Args:
            session_id: ID сессии.

        Returns:
            SessionMetrics (пустые если сессия не найдена).
        """
        return self._sessions.get(
            session_id, SessionMetrics(session_id=session_id)
        )

    def subscribe_to_bus(self, bus: AbstractEventBus) -> None:
        """Подписаться на EventBus для автосбора метрик."""
        from codelab.server.agent.contracts.base import (
            AgentResponse,
        )

        async def on_agent_response(event: DomainEvent) -> None:
            # AgentResponse имеет agent_name, stop_reason, usage
            if hasattr(event, "agent_name") and hasattr(event, "usage"):
                self.record_agent_response(
                    agent_name=str(event.agent_name),  # type: ignore[attr-defined]
                    stop_reason=str(event.stop_reason),  # type: ignore[attr-defined]
                    usage=event.usage,  # type: ignore
                    session_id=event.session_id,
                )

        sub = bus.subscribe(AgentResponse, on_agent_response)  # type: ignore[arg-type]
        self._subscriptions.append(sub)

    def clear(self) -> None:
        """Очистить все метрики и отписаться от шины."""
        self._sessions.clear()
        self._subscriptions.clear()

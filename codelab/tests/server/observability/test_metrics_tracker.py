"""Тесты для MetricsTracker."""


import pytest

from codelab.server.agent.contracts.base import (
    AgentResponse,
    TokenUsage,
)
from codelab.server.agent.event_bus.bus import AgentEventBus
from codelab.server.observability.metrics_tracker import MetricsTracker, SessionMetrics


class TestMetricsTrackerManual:
    """3.10 — тесты записи и получения метрик."""

    @pytest.fixture
    def tracker(self):
        return MetricsTracker()

    def test_record_bus_dispatch(self, tracker):
        tracker.record_bus_dispatch(50.0, "coder", "s1")
        metrics = tracker.get_metrics("s1")
        assert metrics.bus_dispatch_count == 1
        assert metrics.bus_dispatch_total_ms == 50.0

    def test_record_bus_dispatch_multiple(self, tracker):
        tracker.record_bus_dispatch(50.0, "coder", "s1")
        tracker.record_bus_dispatch(30.0, "reviewer", "s1")
        metrics = tracker.get_metrics("s1")
        assert metrics.bus_dispatch_count == 2
        assert metrics.bus_dispatch_total_ms == 80.0
        assert metrics.avg_bus_dispatch_ms == 40.0

    def test_record_llm_call(self, tracker):
        tracker.record_llm_call(
            latency_ms=200.0,
            model="gpt-4",
            input_tokens=100,
            output_tokens=50,
            session_id="s1",
        )
        metrics = tracker.get_metrics("s1")
        assert metrics.llm_call_count == 1
        assert metrics.llm_total_input_tokens == 100
        assert metrics.llm_total_output_tokens == 50

    def test_record_agent_response(self, tracker):
        usage = TokenUsage(10, 20, 30)
        tracker.record_agent_response(
            agent_name="coder",
            stop_reason="end_turn",
            usage=usage,
            session_id="s1",
        )
        metrics = tracker.get_metrics("s1")
        assert metrics.agent_responses == 1
        assert metrics.llm_total_input_tokens == 10
        assert metrics.llm_total_output_tokens == 20

    def test_record_agent_response_error(self, tracker):
        usage = TokenUsage(0, 0, 0)
        tracker.record_agent_response(
            agent_name="coder",
            stop_reason="error",
            usage=usage,
            session_id="s1",
        )
        metrics = tracker.get_metrics("s1")
        assert metrics.agent_errors == 1

    def test_record_compression(self, tracker):
        tracker.record_compression(
            original_tokens=1000,
            sliced_tokens=500,
            ratio=0.5,
            session_id="s1",
        )
        metrics = tracker.get_metrics("s1")
        assert metrics.compression_count == 1
        assert metrics.compression_total_ratio == 0.5
        assert metrics.avg_compression_ratio == 0.5

    def test_record_slicer(self, tracker):
        tracker.record_slicer(
            original_tokens=1000,
            sliced_tokens=500,
            latency_ms=10.0,
            was_skipped=False,
            session_id="s1",
        )
        metrics = tracker.get_metrics("s1")
        assert metrics.slicer_count == 1
        assert metrics.slicer_total_original_tokens == 1000
        assert metrics.slicer_total_sliced_tokens == 500
        assert metrics.slicer_total_latency_ms == 10.0

    def test_record_strategy_execution(self, tracker):
        tracker.record_strategy_execution(
            strategy="single",
            total_time_ms=5000.0,
            session_id="s1",
        )
        metrics = tracker.get_metrics("s1")
        assert metrics.strategy_execution_count == 1
        assert metrics.strategy_execution_total_ms == 5000.0

    def test_get_metrics_empty_session(self, tracker):
        metrics = tracker.get_metrics("nonexistent")
        assert isinstance(metrics, SessionMetrics)
        assert metrics.session_id == "nonexistent"
        assert metrics.bus_dispatch_count == 0

    def test_debug_mode_details(self):
        tracker = MetricsTracker(debug=True)
        tracker.record_bus_dispatch(50.0, "coder", "s1")
        metrics = tracker.get_metrics("s1")
        assert len(metrics.dispatch_details) == 1
        assert metrics.dispatch_details[0]["target_agent"] == "coder"

    def test_non_debug_no_details(self):
        tracker = MetricsTracker(debug=False)
        tracker.record_bus_dispatch(50.0, "coder", "s1")
        metrics = tracker.get_metrics("s1")
        assert metrics.dispatch_details == []

    def test_clear(self, tracker):
        tracker.record_bus_dispatch(50.0, "coder", "s1")
        tracker.clear()
        metrics = tracker.get_metrics("s1")
        assert metrics.bus_dispatch_count == 0


class TestMetricsTrackerAutoSubscribe:
    """3.11 — тесты автозаписи из EventBus."""

    @pytest.mark.asyncio
    async def test_auto_subscribe_agent_response(self):
        bus = AgentEventBus()
        tracker = MetricsTracker()
        tracker.subscribe_to_bus(bus)

        response = AgentResponse(
            request_id="r1",
            text="hello",
            agent_name="coder",
            session_id="s1",
            stop_reason="end_turn",
            usage=TokenUsage(100, 50, 150),
        )
        await bus.publish(response)

        metrics = tracker.get_metrics("s1")
        assert metrics.agent_responses == 1
        assert metrics.llm_total_input_tokens == 100
        assert metrics.llm_total_output_tokens == 50

    @pytest.mark.asyncio
    async def test_auto_subscribe_debug_mode(self):
        bus = AgentEventBus()
        tracker = MetricsTracker(debug=True)
        tracker.subscribe_to_bus(bus)

        response = AgentResponse(
            request_id="r1",
            text="hello",
            agent_name="coder",
            session_id="s1",
            stop_reason="end_turn",
            usage=TokenUsage(100, 50, 150),
        )
        await bus.publish(response)

        metrics = tracker.get_metrics("s1")
        assert len(metrics.agent_response_details) == 1
        assert metrics.agent_response_details[0]["agent_name"] == "coder"

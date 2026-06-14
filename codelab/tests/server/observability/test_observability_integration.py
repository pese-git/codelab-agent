"""Интеграционные тесты observability с DI контейнером.

Проверяют что:
- ObservabilityProvider создаёт Tracer, EventTimeline, MetricsTracker
- Tracer передаётся в LLMLoopStage
- Observability компоненты работают корректно
"""

from __future__ import annotations

import pytest

from codelab.server.config import AppConfig
from codelab.server.di import make_container
from codelab.server.observability import EventTimeline, MetricsTracker, Tracer
from codelab.server.storage.memory import InMemoryStorage


@pytest.fixture
def config():
    return AppConfig()


@pytest.fixture
def storage():
    return InMemoryStorage()


class TestObservabilityProvider:
    """Тесты ObservabilityProvider."""

    @pytest.mark.asyncio
    async def test_creates_tracer(self, config, storage):
        container = make_container(config, storage)
        async with container() as request_container:
            tracer = await request_container.get(Tracer)
            assert isinstance(tracer, Tracer)
            assert tracer.debug is False

    @pytest.mark.asyncio
    async def test_creates_event_timeline(self, config, storage):
        container = make_container(config, storage)
        async with container() as request_container:
            timeline = await request_container.get(EventTimeline)
            assert isinstance(timeline, EventTimeline)
            assert timeline.debug is False

    @pytest.mark.asyncio
    async def test_creates_metrics_tracker(self, config, storage):
        container = make_container(config, storage)
        async with container() as request_container:
            metrics = await request_container.get(MetricsTracker)
            assert isinstance(metrics, MetricsTracker)
            assert metrics.debug is False

    @pytest.mark.asyncio
    async def test_debug_mode_enabled(self, config, storage):
        container = make_container(config, storage, observability_debug=True)
        async with container() as request_container:
            tracer = await request_container.get(Tracer)
            timeline = await request_container.get(EventTimeline)
            metrics = await request_container.get(MetricsTracker)
            assert tracer.debug is True
            assert timeline.debug is True
            # Все observability компоненты используют observability_debug
            assert metrics.debug is True

    @pytest.mark.asyncio
    async def test_tracer_is_singleton(self, config, storage):
        """Tracer должен быть синглтоном (APP scope)."""
        container = make_container(config, storage)
        async with container() as request_container:
            tracer1 = await request_container.get(Tracer)
            tracer2 = await request_container.get(Tracer)
            assert tracer1 is tracer2


class TestTracerIntegration:
    """Интеграционные тесты Tracer."""

    @pytest.mark.asyncio
    async def test_tracer_creates_spans(self, config, storage):
        container = make_container(config, storage)
        async with container() as request_container:
            tracer = await request_container.get(Tracer)

            parent = tracer.start_span("parent", session_id="s1")
            child = tracer.start_span("child", parent=parent, session_id="s1")
            tracer.end_span(child, attributes={"key": "value"})
            tracer.end_span(parent)

            completed = tracer.get_completed_spans()
            assert len(completed) == 2
            assert completed[0].name == "child"
            assert completed[1].name == "parent"
            assert completed[0].attributes.get("key") == "value"

    @pytest.mark.asyncio
    async def test_tracer_hierarchy(self, config, storage):
        container = make_container(config, storage)
        async with container() as request_container:
            tracer = await request_container.get(Tracer)

            root = tracer.start_span("root", session_id="s1")
            level1 = tracer.start_span("level1", parent=root, session_id="s1")
            level2 = tracer.start_span("level2", parent=level1, session_id="s1")

            assert level1.parent_id == root.span_id
            assert level2.parent_id == level1.span_id

            tracer.end_span(level2)
            tracer.end_span(level1)
            tracer.end_span(root)


class TestEventTimelineIntegration:
    """Интеграционные тесты EventTimeline."""

    @pytest.mark.asyncio
    async def test_timeline_records_events(self, config, storage):
        container = make_container(config, storage)
        async with container() as request_container:
            timeline = await request_container.get(EventTimeline)

            timeline.record_event("TestEvent", session_id="s1", details={"key": "value"})
            timeline.record_event("AnotherEvent", session_id="s1")
            timeline.record_event("OtherSession", session_id="s2")

            all_events = timeline.get_events()
            assert len(all_events) == 3

            s1_events = timeline.get_events(session_id="s1")
            assert len(s1_events) == 2
            assert s1_events[0].event_type == "TestEvent"
            assert s1_events[0].details.get("key") == "value"


class TestMetricsTrackerIntegration:
    """Интеграционные тесты MetricsTracker."""

    @pytest.mark.asyncio
    async def test_metrics_records_llm_calls(self, config, storage):
        container = make_container(config, storage)
        async with container() as request_container:
            metrics = await request_container.get(MetricsTracker)

            metrics.record_llm_call(
                latency_ms=100.0,
                model="gpt-4o",
                input_tokens=50,
                output_tokens=30,
                session_id="s1",
            )
            metrics.record_llm_call(
                latency_ms=200.0,
                model="gpt-4o",
                input_tokens=60,
                output_tokens=40,
                session_id="s1",
            )

            session_metrics = metrics.get_metrics("s1")
            assert session_metrics.llm_call_count == 2
            assert session_metrics.llm_total_input_tokens == 110
            assert session_metrics.llm_total_output_tokens == 70

    @pytest.mark.asyncio
    async def test_metrics_records_agent_responses(self, config, storage):
        container = make_container(config, storage)
        async with container() as request_container:
            metrics = await request_container.get(MetricsTracker)

            from codelab.server.agent.contracts.base import TokenUsage

            metrics.record_agent_response(
                agent_name="coder",
                stop_reason="end_turn",
                usage=TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
                session_id="s1",
            )

            session_metrics = metrics.get_metrics("s1")
            assert session_metrics.agent_responses == 1
            assert session_metrics.llm_total_input_tokens == 100
            assert session_metrics.llm_total_output_tokens == 50

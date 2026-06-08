"""Тесты для EventTimeline."""


import pytest

from codelab.server.agent.contracts.base import (
    AgentResponse,
    DomainEvent,
    TokenUsage,
)
from codelab.server.agent.event_bus.bus import AgentEventBus
from codelab.server.observability.event_timeline import EventTimeline, TimelineEvent


class SampleEvent(DomainEvent):
    pass


class TestEventTimelineRecord:
    """2.6 — тесты записи и получения событий."""

    @pytest.fixture
    def timeline(self):
        return EventTimeline()

    def test_record_event_creates_entry(self, timeline):
        event = timeline.record_event(
            event_type="test_event",
            session_id="sess_1",
            details={"key": "value"},
        )
        assert isinstance(event, TimelineEvent)
        assert event.event_type == "test_event"
        assert event.session_id == "sess_1"
        assert event.details == {"key": "value"}

    def test_record_event_default_details(self, timeline):
        event = timeline.record_event(
            event_type="test",
            session_id="s1",
        )
        assert event.details == {}

    def test_get_events_all(self, timeline):
        timeline.record_event("e1", "s1")
        timeline.record_event("e2", "s2")
        timeline.record_event("e3", "s1")

        events = timeline.get_events()
        assert len(events) == 3

    def test_get_events_filtered(self, timeline):
        timeline.record_event("e1", "s1")
        timeline.record_event("e2", "s2")
        timeline.record_event("e3", "s1")

        events = timeline.get_events("s1")
        assert len(events) == 2
        assert all(e.session_id == "s1" for e in events)

    def test_events_sorted_by_time(self, timeline):
        timeline.record_event("e1", "s1")
        timeline.record_event("e2", "s1")
        events = timeline.get_events("s1")
        assert events[0].timestamp <= events[1].timestamp

    def test_to_dict_minimal(self, timeline):
        timeline.debug = False
        event = timeline.record_event(
            "test", "s1", {"key1": "v1", "key2": "v2"}
        )
        d = event.to_dict(debug=False)
        assert "detail_keys" in d
        assert set(d["detail_keys"]) == {"key1", "key2"}
        assert "details" not in d

    def test_to_dict_debug(self, timeline):
        timeline.debug = True
        event = timeline.record_event(
            "test", "s1", {"key": "value"}
        )
        d = event.to_dict(debug=True)
        assert "details" in d
        assert d["details"]["key"] == "value"

    def test_clear(self, timeline):
        timeline.record_event("e1", "s1")
        timeline.clear()
        assert timeline.get_events() == []


class TestEventTimelineAutoSubscribe:
    """2.7 — тесты автозаписи из событий EventBus."""

    @pytest.mark.asyncio
    async def test_auto_subscribe_agent_registered(self):
        bus = AgentEventBus()
        timeline = EventTimeline()
        timeline.subscribe_to_bus(bus)

        await bus.register_agent("coder", lambda r, p: None)  # type: ignore[arg-type]

        events = timeline.get_events()
        assert len(events) >= 1
        assert any(e.event_type == "AgentRegistered" for e in events)

    @pytest.mark.asyncio
    async def test_auto_subscribe_agent_response(self):
        bus = AgentEventBus()
        timeline = EventTimeline()
        timeline.subscribe_to_bus(bus)

        response = AgentResponse(
            request_id="r1",
            text="hello",
            agent_name="coder",
            session_id="s1",
            usage=TokenUsage(10, 20, 30),
        )
        await bus.publish(response)

        events = timeline.get_events("s1")
        assert any(e.event_type == "AgentResponse" for e in events)

    @pytest.mark.asyncio
    async def test_debug_mode_full_payload(self):
        bus = AgentEventBus()
        timeline = EventTimeline(debug=True)
        timeline.subscribe_to_bus(bus)

        response = AgentResponse(
            request_id="r1",
            text="hello",
            agent_name="coder",
            session_id="s1",
            usage=TokenUsage(10, 20, 30),
        )
        await bus.publish(response)

        events = timeline.get_events("s1")
        response_events = [e for e in events if e.event_type == "AgentResponse"]
        assert len(response_events) >= 1
        # В debug mode — полный payload
        assert "details" in response_events[0].to_dict(debug=True)

"""Integration тесты: Tracer + EventBus + MetricsTracker + EventTimeline вместе."""


import pytest

from codelab.server.agent.contracts.base import (
    AgentRequest,
    AgentResponse,
    AgentResult,
    TokenUsage,
)
from codelab.server.agent.event_bus.bus import AgentEventBus, RetryConfig
from codelab.server.observability.event_timeline import EventTimeline
from codelab.server.observability.metrics_tracker import MetricsTracker
from codelab.server.observability.tracer import Tracer


class MockHandler:
    """Mock RequestHandler для тестов."""

    def __init__(self, result: AgentResult) -> None:
        self.result = result
        self.call_count = 0

    async def __call__(self, request, parent_span=None):
        self.call_count += 1
        return AgentResponse(
            request_id=request.correlation_id,
            text=self.result.text,
            tool_calls=self.result.tool_calls,
            usage=self.result.usage,
            stop_reason=self.result.stop_reason,
            agent_name=self.result.agent_name,
            session_id=request.session_id,
        )


@pytest.fixture
def bus():
    return AgentEventBus(retry_config=RetryConfig(max_attempts=1, base_delay=0.0))


@pytest.fixture
def tracer():
    return Tracer(debug=True)


@pytest.fixture
def timeline():
    return EventTimeline(debug=True)


@pytest.fixture
def metrics():
    return MetricsTracker(debug=True)


@pytest.mark.asyncio
async def test_full_observability_integration(
    bus: AgentEventBus,
    tracer: Tracer,
    timeline: EventTimeline,
    metrics: MetricsTracker,
):
    """5.2 — интеграция всех observability компонентов."""
    # Подписываем observability НА ПЕРЕД регистрацией агента
    timeline.subscribe_to_bus(bus)
    metrics.subscribe_to_bus(bus)

    # Регистрируем агента (AgentRegistered будет записан)
    handler = MockHandler(
        result=AgentResult(
            text="response",
            agent_name="coder",
            stop_reason="end_turn",
            usage=TokenUsage(100, 50, 150),
        )
    )
    await bus.register_agent("coder", handler)

    # Создаём span для запроса
    span = tracer.start_span("bus_request", session_id="s1")

    # Отправляем запрос
    request = AgentRequest(
        target_agent="coder",
        correlation_id="c1",
        session_id="s1",
    )
    await bus.send_request(request)

    # Завершаем span
    tracer.end_span(span, {"target": "coder"})

    # Проверяем Tracer
    completed = tracer.get_completed_spans("s1")
    assert len(completed) == 1
    assert completed[0].name == "bus_request"
    assert completed[0].duration_ms is not None

    # Проверяем EventTimeline
    events = timeline.get_events()  # Все события, не только s1
    assert len(events) >= 2  # AgentRegistered + AgentResponse
    assert any(e.event_type == "AgentRegistered" for e in events)
    assert any(e.event_type == "AgentResponse" for e in events)

    # Проверяем MetricsTracker
    m = metrics.get_metrics("s1")
    assert m.agent_responses == 1
    assert m.llm_total_input_tokens == 100
    assert m.llm_total_output_tokens == 50


@pytest.mark.asyncio
async def test_debug_mode_full_details(
    bus: AgentEventBus,
    tracer: Tracer,
    timeline: EventTimeline,
    metrics: MetricsTracker,
):
    """4.4 — debug mode даёт полные детали."""
    timeline.subscribe_to_bus(bus)
    metrics.subscribe_to_bus(bus)

    handler = MockHandler(
        result=AgentResult(
            text="hello",
            agent_name="coder",
            stop_reason="end_turn",
            usage=TokenUsage(10, 5, 15),
        )
    )
    await bus.register_agent("coder", handler)

    request = AgentRequest(
        target_agent="coder",
        correlation_id="c1",
        session_id="s1",
    )
    await bus.send_request(request)

    # Tracer — полные атрибуты
    span = tracer.start_span("test", session_id="s1")
    tracer.end_span(span, {"key": "value"})
    completed = tracer.get_completed_spans("s1")
    assert completed[-1].to_dict(debug=True).get("attributes") == {"key": "value"}

    # Timeline — полные payload'ы
    events = timeline.get_events("s1")
    for event in events:
        d = event.to_dict(debug=True)
        assert "details" in d

    # Metrics — детальные записи
    m = metrics.get_metrics("s1")
    assert len(m.agent_response_details) >= 1


@pytest.mark.asyncio
async def test_non_debug_mode_minimal_details():
    """4.5 — non-debug mode даёт минимальные детали."""
    bus = AgentEventBus(retry_config=RetryConfig(max_attempts=1, base_delay=0.0))
    tracer = Tracer(debug=False)
    timeline = EventTimeline(debug=False)
    metrics = MetricsTracker(debug=False)

    timeline.subscribe_to_bus(bus)
    metrics.subscribe_to_bus(bus)

    handler = MockHandler(
        result=AgentResult(
            text="hello",
            agent_name="coder",
            stop_reason="end_turn",
            usage=TokenUsage(10, 5, 15),
        )
    )
    await bus.register_agent("coder", handler)

    request = AgentRequest(
        target_agent="coder",
        correlation_id="c1",
        session_id="s1",
    )
    await bus.send_request(request)

    # Tracer — без атрибутов
    span = tracer.start_span("test", session_id="s1")
    tracer.end_span(span, {"key": "value"})
    completed = tracer.get_completed_spans("s1")
    d = completed[-1].to_dict(debug=False)
    assert "attributes" not in d

    # Timeline — без полных payload'ов
    events = timeline.get_events("s1")
    for event in events:
        d = event.to_dict(debug=False)
        assert "details" not in d
        assert "detail_keys" in d

    # Metrics — без детальных записей
    m = metrics.get_metrics("s1")
    assert m.dispatch_details == []
    assert m.agent_response_details == []


@pytest.mark.asyncio
async def test_nested_spans_with_observability(
    bus: AgentEventBus,
    tracer: Tracer,
):
    """Тест: вложенные span'ы корректно работают с observability."""
    timeline = EventTimeline()
    metrics = MetricsTracker()
    timeline.subscribe_to_bus(bus)
    metrics.subscribe_to_bus(bus)

    handler = MockHandler(
        result=AgentResult(
            text="ok",
            agent_name="coder",
            usage=TokenUsage(10, 10, 20),
        )
    )
    await bus.register_agent("coder", handler)

    # Иерархия: strategy → bus_request → llm_call
    strategy_span = tracer.start_span("strategy_execution", session_id="s1")
    bus_span = tracer.start_span("bus_request", parent=strategy_span, session_id="s1")
    llm_span = tracer.start_span("llm_call", parent=bus_span, session_id="s1")

    request = AgentRequest(
        target_agent="coder",
        correlation_id="c1",
        session_id="s1",
    )
    await bus.send_request(request)

    tracer.end_span(llm_span, {"model": "gpt-4"})
    tracer.end_span(bus_span, {"target": "coder"})
    tracer.end_span(strategy_span, {"strategy": "single"})

    completed = tracer.get_completed_spans("s1")
    assert len(completed) == 3

    # Проверяем иерархию
    llm = next(s for s in completed if s.name == "llm_call")
    bus_s = next(s for s in completed if s.name == "bus_request")
    strategy = next(s for s in completed if s.name == "strategy_execution")

    assert llm.parent_id == bus_s.span_id
    assert bus_s.parent_id == strategy.span_id

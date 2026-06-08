"""Тесты для Tracer — span hierarchy и context propagation."""


import pytest

from codelab.server.observability.tracer import SpanContext, Tracer


class TestSpanContext:
    def test_creates_with_defaults(self):
        span = SpanContext()
        assert span.span_id != ""
        assert span.name == ""
        assert span.parent_id is None
        assert span.attributes == {}
        assert span.end_time is None

    def test_creates_with_values(self):
        span = SpanContext(
            name="llm_call",
            parent_id="parent_1",
            session_id="sess_1",
        )
        assert span.name == "llm_call"
        assert span.parent_id == "parent_1"
        assert span.session_id == "sess_1"

    def test_duration_ms_is_none_when_not_ended(self):
        span = SpanContext()
        assert span.duration_ms is None

    def test_duration_ms_calculated(self):
        span = SpanContext(start_time=100.0)
        span.end_time = 100.5  # 500ms
        assert span.duration_ms == 500.0

    def test_to_dict_minimal(self):
        span = SpanContext(name="test", session_id="s1")
        span.end_time = span.start_time + 0.1
        d = span.to_dict(debug=False)
        assert "span_id" in d
        assert "name" in d
        assert "duration_ms" in d
        assert "attribute_count" not in d  # Нет атрибутов

    def test_to_dict_with_attributes_minimal(self):
        span = SpanContext(name="test", session_id="s1")
        span.attributes = {"model": "gpt-4", "tokens": 100}
        span.end_time = span.start_time + 0.1
        d = span.to_dict(debug=False)
        assert "attribute_count" in d
        assert d["attribute_count"] == 2
        assert "attributes" not in d

    def test_to_dict_debug(self):
        span = SpanContext(name="test", session_id="s1")
        span.attributes = {"model": "gpt-4"}
        span.end_time = span.start_time + 0.1
        d = span.to_dict(debug=True)
        assert "attributes" in d
        assert d["attributes"]["model"] == "gpt-4"
        assert "attribute_count" not in d


class TestTracerLifecycle:
    """1.6 — тесты жизненного цикла start/end span."""

    @pytest.fixture
    def tracer(self):
        return Tracer()

    def test_start_span_returns_span(self, tracer):
        span = tracer.start_span("test")
        assert isinstance(span, SpanContext)
        assert span.name == "test"
        assert span.end_time is None

    def test_end_span_sets_time(self, tracer):
        span = tracer.start_span("test")
        tracer.end_span(span)
        assert span.end_time is not None
        assert span.duration_ms is not None
        assert span.duration_ms >= 0

    def test_end_span_with_attributes(self, tracer):
        span = tracer.start_span("test")
        tracer.end_span(span, {"model": "gpt-4"})
        assert span.attributes.get("model") == "gpt-4"

    def test_get_current_span(self, tracer):
        span = tracer.start_span("test")
        assert tracer.get_current_span() is span

    def test_get_current_span_none_when_empty(self, tracer):
        assert tracer.get_current_span() is None

    def test_clear(self, tracer):
        span = tracer.start_span("test")
        tracer.end_span(span)
        tracer.clear()
        assert tracer.get_current_span() is None
        assert tracer.get_completed_spans() == []


class TestTracerHierarchy:
    """1.7 — тесты вложенной иерархии span."""

    @pytest.fixture
    def tracer(self):
        return Tracer()

    def test_child_inherits_parent_id(self, tracer):
        parent = tracer.start_span("parent")
        child = tracer.start_span("child")
        assert child.parent_id == parent.span_id

    def test_explicit_parent(self, tracer):
        p1 = tracer.start_span("p1")
        _p2 = tracer.start_span("p2")
        # Явный родитель — не текущий
        child = tracer.start_span("child", parent=p1)
        assert child.parent_id == p1.span_id

    def test_three_level_hierarchy(self, tracer):
        root = tracer.start_span("strategy")
        mid = tracer.start_span("bus_request")
        leaf = tracer.start_span("llm_call")

        assert mid.parent_id == root.span_id
        assert leaf.parent_id == mid.span_id

    def test_end_span_pops_from_stack(self, tracer):
        root = tracer.start_span("root")
        child = tracer.start_span("child")

        tracer.end_span(child)
        assert tracer.get_current_span() is root

    def test_completed_spans(self, tracer):
        s1 = tracer.start_span("s1")
        s2 = tracer.start_span("s2")
        tracer.end_span(s1)
        tracer.end_span(s2)

        completed = tracer.get_completed_spans()
        assert len(completed) == 2

    def test_completed_spans_filtered_by_session(self, tracer):
        s1 = tracer.start_span("s1", session_id="sess_a")
        s2 = tracer.start_span("s2", session_id="sess_b")
        tracer.end_span(s1)
        tracer.end_span(s2)

        assert len(tracer.get_completed_spans("sess_a")) == 1
        assert len(tracer.get_completed_spans("sess_b")) == 1


class TestTracerAttributes:
    """1.8 — тесты атрибутов span."""

    @pytest.fixture
    def tracer(self):
        return Tracer()

    def test_attributes_set_at_end(self, tracer):
        span = tracer.start_span("llm_call")
        tracer.end_span(span, {
            "model": "gpt-4",
            "input_tokens": 100,
            "output_tokens": 50,
        })
        assert span.attributes["model"] == "gpt-4"
        assert span.attributes["input_tokens"] == 100

    def test_attributes_merged(self, tracer):
        span = tracer.start_span("test")
        span.attributes["initial"] = "value"
        tracer.end_span(span, {"added": "attr"})
        assert span.attributes["initial"] == "value"
        assert span.attributes["added"] == "attr"

    def test_debug_mode_preserves_attributes(self, tracer):
        tracer_debug = Tracer(debug=True)
        span = tracer_debug.start_span("test")
        tracer_debug.end_span(span, {"key": "value"})
        d = span.to_dict(debug=True)
        assert d["attributes"]["key"] == "value"

    def test_non_debug_mode_hides_attributes(self, tracer):
        tracer_normal = Tracer(debug=False)
        span = tracer_normal.start_span("test")
        tracer_normal.end_span(span, {"key": "value"})
        d = span.to_dict(debug=False)
        assert "attributes" not in d
        assert d.get("attribute_count") == 1

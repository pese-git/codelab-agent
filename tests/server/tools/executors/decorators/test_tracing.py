"""Тесты для TraceSpan и TraceRecorder."""

from __future__ import annotations

import time

from codelab.server.tools.executors.decorators.tracing import (
    SpanStatus,
    TraceRecorder,
    TraceSpan,
    generate_span_id,
    generate_trace_id,
)


class TestTraceSpan:
    """Тесты для TraceSpan."""

    def test_create_span(self) -> None:
        span = TraceSpan(
            trace_id="abc123",
            span_id="def456",
            parent_span_id=None,
            tool_name="test_tool",
            session_id="session_1",
            start_time_ms=time.perf_counter() * 1000,
        )

        assert span.trace_id == "abc123"
        assert span.span_id == "def456"
        assert span.parent_span_id is None
        assert span.tool_name == "test_tool"
        assert span.status == SpanStatus.OK

    def test_finish_success(self) -> None:
        span = TraceSpan(
            trace_id="abc",
            span_id="def",
            parent_span_id=None,
            tool_name="tool",
            session_id="s1",
            start_time_ms=time.perf_counter() * 1000,
        )

        span.finish(success=True)

        assert span.status == SpanStatus.OK
        assert span.duration_ms >= 0
        assert span.end_time_ms > 0
        assert span.error_message is None

    def test_finish_error(self) -> None:
        span = TraceSpan(
            trace_id="abc",
            span_id="def",
            parent_span_id=None,
            tool_name="tool",
            session_id="s1",
            start_time_ms=time.perf_counter() * 1000,
        )

        span.finish(success=False, error_message="something failed")

        assert span.status == SpanStatus.ERROR
        assert span.error_message == "something failed"

    def test_to_dict(self) -> None:
        span = TraceSpan(
            trace_id="abc",
            span_id="def",
            parent_span_id="parent",
            tool_name="tool",
            session_id="s1",
            start_time_ms=1000.0,
            end_time_ms=1100.0,
            duration_ms=100.0,
            status=SpanStatus.OK,
        )

        result = span.to_dict()

        assert result["trace_id"] == "abc"
        assert result["span_id"] == "def"
        assert result["parent_span_id"] == "parent"
        assert result["tool_name"] == "tool"
        assert result["session_id"] == "s1"
        assert result["duration_ms"] == 100.0
        assert result["status"] == "ok"
        assert "error_message" not in result

    def test_to_dict_with_error(self) -> None:
        span = TraceSpan(
            trace_id="abc",
            span_id="def",
            parent_span_id=None,
            tool_name="tool",
            session_id="s1",
            start_time_ms=1000.0,
            end_time_ms=1100.0,
            duration_ms=100.0,
            status=SpanStatus.ERROR,
            error_message="failed",
        )

        result = span.to_dict()
        assert result["error_message"] == "failed"
        assert result["status"] == "error"

    def test_to_dict_with_attributes(self) -> None:
        span = TraceSpan(
            trace_id="abc",
            span_id="def",
            parent_span_id=None,
            tool_name="tool",
            session_id="s1",
            start_time_ms=1000.0,
            attributes={"key": "value"},
        )

        result = span.to_dict()
        assert result["attributes"] == {"key": "value"}


class TestTraceRecorder:
    """Тесты для TraceRecorder."""

    def test_record_and_retrieve(self) -> None:
        recorder = TraceRecorder()
        span = TraceSpan(
            trace_id="t1",
            span_id="s1",
            parent_span_id=None,
            tool_name="tool",
            session_id="sess",
            start_time_ms=1000.0,
        )
        recorder.record(span)

        spans = recorder.get_all_spans()
        assert len(spans) == 1
        assert spans[0].trace_id == "t1"

    def test_get_spans_by_trace_id(self) -> None:
        recorder = TraceRecorder()
        recorder.record(TraceSpan(
            trace_id="t1", span_id="s1", parent_span_id=None,
            tool_name="tool1", session_id="sess", start_time_ms=1000.0,
        ))
        recorder.record(TraceSpan(
            trace_id="t2", span_id="s2", parent_span_id=None,
            tool_name="tool2", session_id="sess", start_time_ms=2000.0,
        ))
        recorder.record(TraceSpan(
            trace_id="t1", span_id="s3", parent_span_id="s1",
            tool_name="tool3", session_id="sess", start_time_ms=3000.0,
        ))

        t1_spans = recorder.get_spans_by_trace_id("t1")
        assert len(t1_spans) == 2

    def test_get_spans_by_session_id(self) -> None:
        recorder = TraceRecorder()
        recorder.record(TraceSpan(
            trace_id="t1", span_id="s1", parent_span_id=None,
            tool_name="tool", session_id="sess_a", start_time_ms=1000.0,
        ))
        recorder.record(TraceSpan(
            trace_id="t2", span_id="s2", parent_span_id=None,
            tool_name="tool", session_id="sess_b", start_time_ms=2000.0,
        ))

        spans = recorder.get_spans_by_session_id("sess_a")
        assert len(spans) == 1

    def test_get_recent_spans(self) -> None:
        recorder = TraceRecorder()
        for i in range(10):
            recorder.record(TraceSpan(
                trace_id=f"t{i}", span_id=f"s{i}", parent_span_id=None,
                tool_name="tool", session_id="sess", start_time_ms=float(i),
            ))

        recent = recorder.get_recent_spans(limit=5)
        assert len(recent) == 5
        assert recent[0].trace_id == "t5"

    def test_max_spans_eviction(self) -> None:
        recorder = TraceRecorder(max_spans=10)
        for i in range(15):
            recorder.record(TraceSpan(
                trace_id=f"t{i}", span_id=f"s{i}", parent_span_id=None,
                tool_name="tool", session_id="sess", start_time_ms=float(i),
            ))

        all_spans = recorder.get_all_spans()
        assert len(all_spans) <= 10

    def test_reset(self) -> None:
        recorder = TraceRecorder()
        recorder.record(TraceSpan(
            trace_id="t1", span_id="s1", parent_span_id=None,
            tool_name="tool", session_id="sess", start_time_ms=1000.0,
        ))
        recorder.reset()

        assert recorder.get_all_spans() == []


class TestGenerateIds:
    """Тесты для генераторов ID."""

    def test_generate_trace_id_unique(self) -> None:
        ids = {generate_trace_id() for _ in range(100)}
        assert len(ids) == 100

    def test_generate_trace_id_format(self) -> None:
        trace_id = generate_trace_id()
        assert len(trace_id) == 32
        assert all(c in "0123456789abcdef" for c in trace_id)

    def test_generate_span_id_unique(self) -> None:
        ids = {generate_span_id() for _ in range(100)}
        assert len(ids) == 100

    def test_generate_span_id_format(self) -> None:
        span_id = generate_span_id()
        assert len(span_id) == 16

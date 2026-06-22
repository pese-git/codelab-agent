"""Тесты для TracingDecorator."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from codelab.server.protocol.state import SessionState
from codelab.server.tools.base import ToolExecutionResult
from codelab.server.tools.executors.decorators import TracingDecorator
from codelab.server.tools.executors.decorators.tracing import (
    SpanStatus,
    TraceRecorder,
)


class MockExecutor:
    """Mock executor для тестирования."""

    def __init__(
        self,
        result: ToolExecutionResult | None = None,
        delay: float = 0.0,
        raise_error: Exception | None = None,
    ) -> None:
        self.result = result or ToolExecutionResult(success=True, output="test")
        self.delay = delay
        self.raise_error = raise_error
        self.call_count = 0

    async def execute(
        self,
        session: SessionState,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        self.call_count += 1
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        if self.raise_error is not None:
            raise self.raise_error
        return self.result


@pytest.fixture
def mock_session() -> SessionState:
    session = MagicMock(spec=SessionState)
    session.session_id = "test_session"
    return session


@pytest.fixture
def mock_arguments() -> dict[str, Any]:
    return {"tool_name": "mcp:server:tool", "arg1": "value1"}


@pytest.fixture
def recorder() -> TraceRecorder:
    return TraceRecorder()


class TestTracingDecorator:
    """Тесты для TracingDecorator."""

    @pytest.mark.asyncio
    async def test_creates_span_on_success(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
        recorder: TraceRecorder,
    ) -> None:
        mock_executor = MockExecutor(result=ToolExecutionResult(success=True, output="ok"))
        decorator = TracingDecorator(mock_executor, recorder=recorder)

        result = await decorator.execute(mock_session, mock_arguments)

        assert result.success is True
        spans = recorder.get_all_spans()
        assert len(spans) == 1

        span = spans[0]
        assert span.tool_name == "mcp:server:tool"
        assert span.session_id == "test_session"
        assert span.status == SpanStatus.OK
        assert span.duration_ms >= 0
        assert span.trace_id is not None
        assert span.span_id is not None

    @pytest.mark.asyncio
    async def test_creates_span_on_failure_result(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
        recorder: TraceRecorder,
    ) -> None:
        mock_executor = MockExecutor(result=ToolExecutionResult(success=False, error="fail"))
        decorator = TracingDecorator(mock_executor, recorder=recorder)

        result = await decorator.execute(mock_session, mock_arguments)

        assert result.success is False
        spans = recorder.get_all_spans()
        assert len(spans) == 1
        assert spans[0].status == SpanStatus.ERROR
        assert spans[0].error_message == "fail"

    @pytest.mark.asyncio
    async def test_creates_span_on_exception(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
        recorder: TraceRecorder,
    ) -> None:
        mock_executor = MockExecutor(raise_error=ValueError("boom"))
        decorator = TracingDecorator(mock_executor, recorder=recorder)

        with pytest.raises(ValueError, match="boom"):
            await decorator.execute(mock_session, mock_arguments)

        spans = recorder.get_all_spans()
        assert len(spans) == 1
        assert spans[0].status == SpanStatus.ERROR
        assert spans[0].error_message == "boom"

    @pytest.mark.asyncio
    async def test_span_has_timing(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
        recorder: TraceRecorder,
    ) -> None:
        mock_executor = MockExecutor(delay=0.05)
        decorator = TracingDecorator(mock_executor, recorder=recorder)

        await decorator.execute(mock_session, mock_arguments)

        spans = recorder.get_all_spans()
        assert len(spans) == 1
        assert spans[0].duration_ms > 0
        assert spans[0].end_time_ms > spans[0].start_time_ms

    @pytest.mark.asyncio
    async def test_span_has_no_parent_by_default(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
        recorder: TraceRecorder,
    ) -> None:
        mock_executor = MockExecutor()
        decorator = TracingDecorator(mock_executor, recorder=recorder)

        await decorator.execute(mock_session, mock_arguments)

        spans = recorder.get_all_spans()
        assert spans[0].parent_span_id is None

    @pytest.mark.asyncio
    async def test_nested_decorators_share_trace_id(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
        recorder: TraceRecorder,
    ) -> None:
        inner = MockExecutor()
        inner_decorator = TracingDecorator(inner, recorder=recorder)
        outer_decorator = TracingDecorator(inner_decorator, recorder=recorder)

        await outer_decorator.execute(mock_session, mock_arguments)

        spans = recorder.get_all_spans()
        assert len(spans) == 2

        outer_span = spans[1]
        inner_span = spans[0]

        assert outer_span.trace_id == inner_span.trace_id
        assert inner_span.parent_span_id == outer_span.span_id
        assert outer_span.parent_span_id is None

    @pytest.mark.asyncio
    async def test_preserves_result(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
        recorder: TraceRecorder,
    ) -> None:
        expected = ToolExecutionResult(success=True, output="custom", raw_output={"k": "v"})
        mock_executor = MockExecutor(result=expected)
        decorator = TracingDecorator(mock_executor, recorder=recorder)

        result = await decorator.execute(mock_session, mock_arguments)

        assert result.success == expected.success
        assert result.output == expected.output
        assert result.raw_output == expected.raw_output

    @pytest.mark.asyncio
    async def test_multiple_calls_create_separate_spans(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
        recorder: TraceRecorder,
    ) -> None:
        mock_executor = MockExecutor()
        decorator = TracingDecorator(mock_executor, recorder=recorder)

        await decorator.execute(mock_session, mock_arguments)
        await decorator.execute(mock_session, mock_arguments)

        spans = recorder.get_all_spans()
        assert len(spans) == 2
        assert spans[0].span_id != spans[1].span_id

    @pytest.mark.asyncio
    async def test_uses_global_recorder_by_default(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
    ) -> None:
        from codelab.server.tools.executors.decorators.tracing import (
            get_global_trace_recorder,
        )

        get_global_trace_recorder().reset()
        mock_executor = MockExecutor()
        decorator = TracingDecorator(mock_executor)

        await decorator.execute(mock_session, mock_arguments)

        spans = get_global_trace_recorder().get_recent_spans(limit=1)
        assert len(spans) == 1

        get_global_trace_recorder().reset()

    @pytest.mark.asyncio
    async def test_unknown_tool_name(
        self,
        mock_session: SessionState,
        recorder: TraceRecorder,
    ) -> None:
        mock_executor = MockExecutor()
        decorator = TracingDecorator(mock_executor, recorder=recorder)

        await decorator.execute(mock_session, {})

        spans = recorder.get_all_spans()
        assert len(spans) == 1
        assert spans[0].tool_name == "unknown"

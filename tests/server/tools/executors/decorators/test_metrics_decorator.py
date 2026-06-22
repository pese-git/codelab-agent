"""Тесты для MetricsDecorator."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from codelab.server.protocol.state import SessionState
from codelab.server.tools.base import ToolExecutionResult
from codelab.server.tools.executors.decorators import MetricsDecorator
from codelab.server.tools.executors.decorators.metrics import MetricsCollector


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
def collector() -> MetricsCollector:
    return MetricsCollector()


class TestMetricsDecorator:
    """Тесты для MetricsDecorator."""

    @pytest.mark.asyncio
    async def test_records_success(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
        collector: MetricsCollector,
    ) -> None:
        mock_executor = MockExecutor(result=ToolExecutionResult(success=True, output="ok"))
        decorator = MetricsDecorator(mock_executor, collector=collector)

        result = await decorator.execute(mock_session, mock_arguments)

        assert result.success is True
        metrics = collector.get_tool_metrics("mcp:server:tool")
        assert metrics is not None
        assert metrics.total_calls == 1
        assert metrics.success_count == 1
        assert metrics.failure_count == 0

    @pytest.mark.asyncio
    async def test_records_failure_result(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
        collector: MetricsCollector,
    ) -> None:
        mock_executor = MockExecutor(result=ToolExecutionResult(success=False, error="fail"))
        decorator = MetricsDecorator(mock_executor, collector=collector)

        result = await decorator.execute(mock_session, mock_arguments)

        assert result.success is False
        metrics = collector.get_tool_metrics("mcp:server:tool")
        assert metrics is not None
        assert metrics.failure_count == 1
        assert metrics.success_count == 0

    @pytest.mark.asyncio
    async def test_records_exception_as_failure(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
        collector: MetricsCollector,
    ) -> None:
        mock_executor = MockExecutor(raise_error=ValueError("boom"))
        decorator = MetricsDecorator(mock_executor, collector=collector)

        with pytest.raises(ValueError, match="boom"):
            await decorator.execute(mock_session, mock_arguments)

        metrics = collector.get_tool_metrics("mcp:server:tool")
        assert metrics is not None
        assert metrics.total_calls == 1
        assert metrics.failure_count == 1

    @pytest.mark.asyncio
    async def test_records_duration(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
        collector: MetricsCollector,
    ) -> None:
        mock_executor = MockExecutor(delay=0.05)
        decorator = MetricsDecorator(mock_executor, collector=collector)

        await decorator.execute(mock_session, mock_arguments)

        metrics = collector.get_tool_metrics("mcp:server:tool")
        assert metrics is not None
        assert metrics.total_duration_ms > 0
        assert metrics.min_duration_ms > 0

    @pytest.mark.asyncio
    async def test_multiple_calls_aggregated(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
        collector: MetricsCollector,
    ) -> None:
        mock_executor = MockExecutor()
        decorator = MetricsDecorator(mock_executor, collector=collector)

        await decorator.execute(mock_session, mock_arguments)
        await decorator.execute(mock_session, mock_arguments)
        await decorator.execute(mock_session, mock_arguments)

        metrics = collector.get_tool_metrics("mcp:server:tool")
        assert metrics is not None
        assert metrics.total_calls == 3
        assert metrics.success_count == 3

    @pytest.mark.asyncio
    async def test_preserves_result(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
        collector: MetricsCollector,
    ) -> None:
        expected = ToolExecutionResult(success=True, output="custom", raw_output={"k": "v"})
        mock_executor = MockExecutor(result=expected)
        decorator = MetricsDecorator(mock_executor, collector=collector)

        result = await decorator.execute(mock_session, mock_arguments)

        assert result.success == expected.success
        assert result.output == expected.output
        assert result.raw_output == expected.raw_output

    @pytest.mark.asyncio
    async def test_unknown_tool_name(
        self,
        mock_session: SessionState,
        collector: MetricsCollector,
    ) -> None:
        mock_executor = MockExecutor()
        decorator = MetricsDecorator(mock_executor, collector=collector)

        await decorator.execute(mock_session, {})

        metrics = collector.get_tool_metrics("unknown")
        assert metrics is not None
        assert metrics.total_calls == 1

    @pytest.mark.asyncio
    async def test_uses_global_collector_by_default(
        self,
        mock_session: SessionState,
        mock_arguments: dict[str, Any],
    ) -> None:
        from codelab.server.tools.executors.decorators.metrics import (
            get_global_metrics_collector,
        )

        get_global_metrics_collector().reset()
        mock_executor = MockExecutor()
        decorator = MetricsDecorator(mock_executor)

        await decorator.execute(mock_session, mock_arguments)

        metrics = get_global_metrics_collector().get_tool_metrics("mcp:server:tool")
        assert metrics is not None
        assert metrics.total_calls == 1

        get_global_metrics_collector().reset()

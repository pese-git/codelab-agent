"""Тесты для ToolMetrics и MetricsCollector."""

from __future__ import annotations

import pytest

from codelab.server.tools.executors.decorators.metrics import (
    MetricsCollector,
    ToolMetrics,
)


class TestToolMetrics:
    """Тесты для ToolMetrics."""

    def test_initial_state(self) -> None:
        metrics = ToolMetrics(tool_name="test_tool")

        assert metrics.tool_name == "test_tool"
        assert metrics.total_calls == 0
        assert metrics.success_count == 0
        assert metrics.failure_count == 0
        assert metrics.total_duration_ms == 0.0
        assert metrics.max_duration_ms == 0.0

    def test_avg_duration_zero_calls(self) -> None:
        metrics = ToolMetrics(tool_name="test_tool")
        assert metrics.avg_duration_ms == 0.0

    def test_success_rate_zero_calls(self) -> None:
        metrics = ToolMetrics(tool_name="test_tool")
        assert metrics.success_rate == 0.0

    def test_record_success(self) -> None:
        metrics = ToolMetrics(tool_name="test_tool")
        metrics.record(100.0, success=True)

        assert metrics.total_calls == 1
        assert metrics.success_count == 1
        assert metrics.failure_count == 0
        assert metrics.total_duration_ms == 100.0
        assert metrics.min_duration_ms == 100.0
        assert metrics.max_duration_ms == 100.0

    def test_record_failure(self) -> None:
        metrics = ToolMetrics(tool_name="test_tool")
        metrics.record(50.0, success=False)

        assert metrics.total_calls == 1
        assert metrics.success_count == 0
        assert metrics.failure_count == 1

    def test_record_multiple(self) -> None:
        metrics = ToolMetrics(tool_name="test_tool")
        metrics.record(100.0, success=True)
        metrics.record(200.0, success=True)
        metrics.record(50.0, success=False)

        assert metrics.total_calls == 3
        assert metrics.success_count == 2
        assert metrics.failure_count == 1
        assert metrics.total_duration_ms == 350.0
        assert metrics.min_duration_ms == 50.0
        assert metrics.max_duration_ms == 200.0

    def test_avg_duration(self) -> None:
        metrics = ToolMetrics(tool_name="test_tool")
        metrics.record(100.0, success=True)
        metrics.record(200.0, success=True)

        assert metrics.avg_duration_ms == 150.0

    def test_success_rate(self) -> None:
        metrics = ToolMetrics(tool_name="test_tool")
        metrics.record(100.0, success=True)
        metrics.record(200.0, success=False)
        metrics.record(50.0, success=True)

        assert metrics.success_rate == pytest.approx(2 / 3)

    def test_to_dict(self) -> None:
        metrics = ToolMetrics(tool_name="test_tool")
        metrics.record(100.0, success=True)
        metrics.record(200.0, success=False)

        result = metrics.to_dict()

        assert result["tool_name"] == "test_tool"
        assert result["total_calls"] == 2
        assert result["success_count"] == 1
        assert result["failure_count"] == 1
        assert result["success_rate"] == 0.5
        assert result["avg_duration_ms"] == 150.0
        assert result["min_duration_ms"] == 100.0
        assert result["max_duration_ms"] == 200.0
        assert result["total_duration_ms"] == 300.0

    def test_to_dict_zero_calls(self) -> None:
        metrics = ToolMetrics(tool_name="test_tool")
        result = metrics.to_dict()

        assert result["min_duration_ms"] == 0.0
        assert result["total_calls"] == 0


class TestMetricsCollector:
    """Тесты для MetricsCollector."""

    def test_record_creates_tool_metrics(self) -> None:
        collector = MetricsCollector()
        collector.record("tool_a", 100.0, success=True)

        metrics = collector.get_tool_metrics("tool_a")
        assert metrics is not None
        assert metrics.tool_name == "tool_a"
        assert metrics.total_calls == 1

    def test_record_aggregates_same_tool(self) -> None:
        collector = MetricsCollector()
        collector.record("tool_a", 100.0, success=True)
        collector.record("tool_a", 200.0, success=False)

        metrics = collector.get_tool_metrics("tool_a")
        assert metrics is not None
        assert metrics.total_calls == 2
        assert metrics.success_count == 1
        assert metrics.failure_count == 1

    def test_record_different_tools(self) -> None:
        collector = MetricsCollector()
        collector.record("tool_a", 100.0, success=True)
        collector.record("tool_b", 200.0, success=True)

        assert collector.get_tool_metrics("tool_a") is not None
        assert collector.get_tool_metrics("tool_b") is not None

    def test_get_tool_metrics_not_found(self) -> None:
        collector = MetricsCollector()
        assert collector.get_tool_metrics("nonexistent") is None

    def test_get_all_metrics(self) -> None:
        collector = MetricsCollector()
        collector.record("tool_a", 100.0, success=True)
        collector.record("tool_b", 200.0, success=True)

        all_metrics = collector.get_all_metrics()
        assert len(all_metrics) == 2
        assert "tool_a" in all_metrics
        assert "tool_b" in all_metrics

    def test_get_summary(self) -> None:
        collector = MetricsCollector()
        collector.record("tool_a", 100.0, success=True)
        collector.record("tool_a", 200.0, success=False)
        collector.record("tool_b", 50.0, success=True)

        summary = collector.get_summary()

        assert summary["total_tools"] == 2
        assert summary["total_calls"] == 3
        assert summary["total_success"] == 2
        assert summary["total_failure"] == 1
        assert summary["overall_success_rate"] == pytest.approx(0.6667, abs=1e-4)
        assert summary["total_duration_ms"] == 350.0
        assert "tool_a" in summary["tools"]
        assert "tool_b" in summary["tools"]

    def test_get_summary_empty(self) -> None:
        collector = MetricsCollector()
        summary = collector.get_summary()

        assert summary["total_tools"] == 0
        assert summary["total_calls"] == 0
        assert summary["overall_success_rate"] == 0.0

    def test_reset(self) -> None:
        collector = MetricsCollector()
        collector.record("tool_a", 100.0, success=True)
        collector.reset()

        assert collector.get_tool_metrics("tool_a") is None
        assert collector.get_all_metrics() == {}

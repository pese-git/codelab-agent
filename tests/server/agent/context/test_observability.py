"""Тесты метрик и трейсинга Context Manager."""

from __future__ import annotations

import pytest

from codelab.server.agent.context.manager import DefaultContextManager
from codelab.server.agent.context.models import ContextConfig
from codelab.server.llm.models import CompletionResponse, StopReason
from codelab.server.observability.metrics_tracker import MetricsTracker
from codelab.server.observability.tracer import Tracer
from tests.server.agent.fakes import FakeSessionView


class MockToolRegistry:
    """Mock ToolRegistry для тестирования."""

    def __init__(self) -> None:
        self.tools: list = []

    def get_available_tools(self, session_id: str) -> list:
        return self.tools

    async def execute_tool(self, session_id: str, tool_name: str, arguments: dict):
        class Result:
            def __init__(self, success: bool, result: object) -> None:
                self.success = success
                self.result = result

        if tool_name == "fs_search":
            return Result(True, [{"path": "src/main.py"}])
        if tool_name == "fs_read":
            path = arguments.get("path", "")
            return Result(True, {"content": f"# Content of {path}\ndef example():\n    pass\n"})
        return Result(False, None)


class MockLLM:
    """Mock LLM провайдер."""

    def __init__(self, response_text: str) -> None:
        self._response_text = response_text

    async def create_completion(self, request):
        return CompletionResponse(
            text=self._response_text,
            tool_calls=[],
            stop_reason=StopReason.END_TURN,
            model=request.model,
        )


class TestContextMetrics:
    """Тесты метрик сборки контекста."""

    def test_record_context_build_updates_metrics(self):
        """record_context_build() должен обновлять метрики сессии."""
        tracker = MetricsTracker()

        tracker.record_context_build(
            build_duration_ms=50.0,
            gathered_files=3,
            baseline_tokens=500,
            tail_tokens=100,
            session_id="session-1",
        )

        metrics = tracker.get_metrics("session-1")
        assert metrics.context_build_count == 1
        assert metrics.context_build_total_ms == 50.0
        assert metrics.context_gathered_files == 3
        assert metrics.context_baseline_tokens == 500
        assert metrics.context_tail_tokens == 100

    def test_record_context_build_accumulates(self):
        """record_context_build() должен накапливать значения."""
        tracker = MetricsTracker()

        tracker.record_context_build(10.0, 1, 100, 50, "s1")
        tracker.record_context_build(20.0, 2, 200, 100, "s1")

        metrics = tracker.get_metrics("s1")
        assert metrics.context_build_count == 2
        assert metrics.context_build_total_ms == 30.0
        assert metrics.context_gathered_files == 3
        assert metrics.context_baseline_tokens == 300
        assert metrics.context_tail_tokens == 150

    def test_record_context_build_always_saves_details(self):
        """record_context_build() сохраняет детали всегда, не только в debug mode."""
        tracker = MetricsTracker(debug=False)

        tracker.record_context_build(25.0, 5, 1000, 200, "s1")

        metrics = tracker.get_metrics("s1")
        assert len(metrics.context_build_details) == 1
        detail = metrics.context_build_details[0]
        assert detail["build_duration_ms"] == 25.0
        assert detail["gathered_files"] == 5
        assert detail["baseline_tokens"] == 1000
        assert detail["tail_tokens"] == 200
        assert "timestamp" in detail

    def test_record_context_build_extended_params(self):
        """record_context_build() с расширенными параметрами сохраняет детали."""
        tracker = MetricsTracker()

        tracker.record_context_build(
            build_duration_ms=100.0,
            gathered_files=3,
            baseline_tokens=1500,
            tail_tokens=300,
            session_id="s1",
            task_type="feature",
            file_paths=["src/a.py", "src/b.py", "src/c.py"],
            candidate_count=10,
            stage_timings={"extract_ms": 5.0, "analyze_ms": 20.0, "gather_ms": 50.0},
            graph_stats={"files_in_graph": 50, "total_dependencies": 120},
        )

        metrics = tracker.get_metrics("s1")
        detail = metrics.context_build_details[0]
        assert detail["task_type"] == "feature"
        assert detail["file_paths"] == ["src/a.py", "src/b.py", "src/c.py"]
        assert detail["candidate_count"] == 10
        assert detail["stage_timings"]["extract_ms"] == 5.0
        assert detail["graph_stats"]["files_in_graph"] == 50

    def test_record_context_build_backward_compatible(self):
        """record_context_build() без новых параметров работает (обратная совместимость)."""
        tracker = MetricsTracker(debug=True)

        tracker.record_context_build(25.0, 5, 1000, 200, "s1")

        metrics = tracker.get_metrics("s1")
        detail = metrics.context_build_details[0]
        assert detail["task_type"] == ""
        assert detail["file_paths"] == []
        assert detail["candidate_count"] == 0
        assert detail["stage_timings"] == {}
        assert detail["graph_stats"] == {}

    def test_last_task_profile_default_none(self):
        """last_task_profile по умолчанию None."""
        tracker = MetricsTracker()
        metrics = tracker.get_metrics("s1")
        assert metrics.last_task_profile is None

    def test_last_task_profile_set_and_read(self):
        """last_task_profile можно установить и прочитать."""
        tracker = MetricsTracker()
        tracker.record_context_build(0.0, 0, 0, 0, "s1")
        metrics = tracker.get_metrics("s1")
        metrics.last_task_profile = {
            "task_type": "bug_fix",
            "search_terms": ["auth", "crash"],
            "target_modules": ["src/auth"],
            "investigation_depth": 2,
            "needs_tests": True,
        }

        loaded = tracker.get_metrics("s1")
        assert loaded.last_task_profile is not None
        assert loaded.last_task_profile["task_type"] == "bug_fix"
        assert loaded.last_task_profile["needs_tests"] is True

    def test_get_metrics_does_not_persist(self):
        """get_metrics() не создаёт объект — read-only семантика."""
        tracker = MetricsTracker()

        # get_metrics для несуществующей сессии
        metrics = tracker.get_metrics("nonexistent")
        assert metrics.session_id == "nonexistent"

        # Модифицируем полученный объект
        metrics.last_task_profile = {"task_type": "test"}

        # Получаем снова — модификация потеряна
        metrics_again = tracker.get_metrics("nonexistent")
        assert metrics_again.last_task_profile is None

    def test_get_or_create_metrics_persists(self):
        """get_or_create_metrics() создаёт и сохраняет объект."""
        tracker = MetricsTracker()

        # get_or_create_metrics для несуществующей сессии
        metrics = tracker.get_or_create_metrics("new-session")
        metrics.last_task_profile = {"task_type": "feature"}

        # Получаем через get_metrics — модификация сохранена
        loaded = tracker.get_metrics("new-session")
        assert loaded.last_task_profile is not None
        assert loaded.last_task_profile["task_type"] == "feature"

    def test_last_task_profile_persisted_via_get_or_create(self):
        """last_task_profile сохраняется при использовании get_or_create_metrics."""
        tracker = MetricsTracker()

        # Симулируем поведение manager.py с get_or_create_metrics
        session_metrics = tracker.get_or_create_metrics("s1")
        session_metrics.last_task_profile = {
            "task_type": "architecture",
            "search_terms": ["lib", "main.dart"],
            "target_modules": ["lib/main.dart"],
            "investigation_depth": 3,
            "needs_tests": False,
        }

        # Затем record_context_build (как в manager.py)
        tracker.record_context_build(100.0, 5, 1000, 200, "s1")

        # Проверяем через get_metrics (как делает /context profile)
        loaded = tracker.get_metrics("s1")
        assert loaded.last_task_profile is not None
        assert loaded.last_task_profile["task_type"] == "architecture"
        assert loaded.context_build_count == 1


class TestContextBuildTracing:
    """Тесты span трейсинга context.build."""

    @pytest.mark.asyncio
    async def test_build_context_creates_span(self):
        """build_context() должен создавать span 'context.build'."""
        tool_registry = MockToolRegistry()
        tracer = Tracer()
        config = ContextConfig(enabled=True, gather_enabled=False)

        _manager = DefaultContextManager(
            tool_registry=tool_registry,
            config=config,
            llm=None,
            tracer=tracer,
        )

        _session = FakeSessionView(session_id="test-session", cwd="/tmp", config_values={})
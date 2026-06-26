"""Тесты метрик и трейсинга Context Manager."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from codelab.server.agent.context.manager import DefaultContextManager
from codelab.server.agent.context.models import ContextConfig
from codelab.server.llm.models import CompletionResponse, StopReason
from codelab.server.observability.metrics_tracker import MetricsTracker
from codelab.server.observability.tracer import Tracer


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

    def test_record_context_build_debug_mode(self):
        """В debug mode record_context_build() сохраняет детали."""
        tracker = MetricsTracker(debug=True)

        tracker.record_context_build(25.0, 5, 1000, 200, "s1")

        metrics = tracker.get_metrics("s1")
        assert len(metrics.context_build_details) == 1
        detail = metrics.context_build_details[0]
        assert detail["build_duration_ms"] == 25.0
        assert detail["gathered_files"] == 5
        assert detail["baseline_tokens"] == 1000
        assert detail["tail_tokens"] == 200
        assert "timestamp" in detail


class TestContextBuildTracing:
    """Тесты span трейсинга context.build."""

    @pytest.mark.asyncio
    async def test_build_context_creates_span(self):
        """build_context() должен создавать span 'context.build'."""
        tool_registry = MockToolRegistry()
        tracer = Tracer()
        config = ContextConfig(enabled=True, gather_enabled=False)

        manager = DefaultContextManager(
            tool_registry=tool_registry,
            config=config,
            llm=None,
            tracer=tracer,
        )

        session = MagicMock()
        session.session_id = "test-session"
        prompt = [{"type": "text", "text": "Hello"}]

        await manager.build_context(
            session=session,
            prompt=prompt,
            agent_scope="single",
            system_prompt="System prompt",
        )

        completed = tracer.get_completed_spans()
        assert len(completed) == 1
        assert completed[0].name == "context.build"

    @pytest.mark.asyncio
    async def test_build_context_span_has_attributes(self):
        """Span 'context.build' должен содержать атрибуты."""
        tool_registry = MockToolRegistry()
        tracer = Tracer()
        config = ContextConfig(enabled=True, gather_enabled=False)

        manager = DefaultContextManager(
            tool_registry=tool_registry,
            config=config,
            llm=None,
            tracer=tracer,
        )

        session = MagicMock()
        session.session_id = "test-session"
        prompt = [{"type": "text", "text": "Hello"}]

        await manager.build_context(
            session=session,
            prompt=prompt,
            agent_scope="orchestrated",
            system_prompt="System prompt",
        )

        completed = tracer.get_completed_spans()
        assert len(completed) == 1
        span = completed[0]
        assert span.attributes["agent_scope"] == "orchestrated"
        assert "task_type" in span.attributes
        assert "baseline_tokens" in span.attributes
        assert "tail_tokens" in span.attributes

    @pytest.mark.asyncio
    async def test_build_context_without_tracer(self):
        """build_context() должен работать без tracer."""
        tool_registry = MockToolRegistry()
        config = ContextConfig(enabled=True, gather_enabled=False)

        manager = DefaultContextManager(
            tool_registry=tool_registry,
            config=config,
            llm=None,
            tracer=None,
        )

        session = MagicMock()
        session.session_id = "test-session"
        prompt = [{"type": "text", "text": "Hello"}]

        envelope = await manager.build_context(
            session=session,
            prompt=prompt,
            agent_scope="single",
            system_prompt="System prompt",
        )

        assert envelope is not None
        assert len(envelope.baseline) > 0


class TestContextBuildMetricsIntegration:
    """Интеграционные тесты метрик в build_context."""

    @pytest.mark.asyncio
    async def test_build_context_records_metrics(self):
        """build_context() должен записывать метрики в MetricsTracker."""
        tool_registry = MockToolRegistry()
        tracker = MetricsTracker()
        config = ContextConfig(enabled=True, gather_enabled=False)

        manager = DefaultContextManager(
            tool_registry=tool_registry,
            config=config,
            llm=None,
            metrics_tracker=tracker,
        )

        session = MagicMock()
        session.session_id = "test-session"
        prompt = [{"type": "text", "text": "Hello"}]

        await manager.build_context(
            session=session,
            prompt=prompt,
            agent_scope="single",
            system_prompt="System prompt",
        )

        metrics = tracker.get_metrics("test-session")
        assert metrics.context_build_count == 1
        assert metrics.context_build_total_ms > 0
        assert metrics.context_baseline_tokens > 0
        assert metrics.context_tail_tokens > 0

    @pytest.mark.asyncio
    async def test_build_context_without_metrics_tracker(self):
        """build_context() должен работать без MetricsTracker."""
        tool_registry = MockToolRegistry()
        config = ContextConfig(enabled=True, gather_enabled=False)

        manager = DefaultContextManager(
            tool_registry=tool_registry,
            config=config,
            llm=None,
            metrics_tracker=None,
        )

        session = MagicMock()
        session.session_id = "test-session"
        prompt = [{"type": "text", "text": "Hello"}]

        envelope = await manager.build_context(
            session=session,
            prompt=prompt,
            agent_scope="single",
            system_prompt="System prompt",
        )

        assert envelope is not None


class TestContextGatherTracing:
    """Тесты span трейсинга context.gather."""

    @pytest.mark.asyncio
    async def test_gather_creates_span(self):
        """gather() должен создавать span 'context.gather'."""
        from codelab.server.agent.context.dependency_graph import RegexDependencyGraph
        from codelab.server.agent.context.gatherer import ACPContextGatherer
        from codelab.server.agent.context.models import TaskProfile, TaskType

        tool_registry = MockToolRegistry()
        tracer = Tracer()
        dep_graph = RegexDependencyGraph()

        gatherer = ACPContextGatherer(
            tool_registry=tool_registry,
            dependency_graph=dep_graph,
            session_id="test-session",
            tracer=tracer,
        )

        profile = TaskProfile(
            task_type=TaskType.FEATURE,
            search_terms=["main"],
            target_modules=["src/main.py"],
            investigation_depth=1,
            needs_tests=False,
        )

        session = MagicMock()
        session.session_id = "test-session"

        await gatherer.gather(profile, session)

        completed = tracer.get_completed_spans()
        assert len(completed) == 1
        assert completed[0].name == "context.gather"

    @pytest.mark.asyncio
    async def test_gather_span_has_attributes(self):
        """Span 'context.gather' должен содержать атрибуты."""
        from codelab.server.agent.context.dependency_graph import RegexDependencyGraph
        from codelab.server.agent.context.gatherer import ACPContextGatherer
        from codelab.server.agent.context.models import TaskProfile, TaskType

        tool_registry = MockToolRegistry()
        tracer = Tracer()
        dep_graph = RegexDependencyGraph()

        gatherer = ACPContextGatherer(
            tool_registry=tool_registry,
            dependency_graph=dep_graph,
            session_id="test-session",
            tracer=tracer,
        )

        profile = TaskProfile(
            task_type=TaskType.BUG_FIX,
            search_terms=["auth", "login"],
            target_modules=[],
            investigation_depth=2,
            needs_tests=True,
        )

        session = MagicMock()
        session.session_id = "test-session"

        await gatherer.gather(profile, session)

        completed = tracer.get_completed_spans()
        assert len(completed) == 1
        span = completed[0]
        assert span.attributes["task_type"] == TaskType.BUG_FIX
        assert span.attributes["search_terms"] == ["auth", "login"]
        assert "candidate_files" in span.attributes
        assert "selected_files" in span.attributes

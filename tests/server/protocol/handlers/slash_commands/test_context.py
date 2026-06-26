"""Тесты для ContextCommandHandler."""

from __future__ import annotations

from unittest.mock import MagicMock

from codelab.server.observability.metrics_tracker import MetricsTracker
from codelab.server.observability.tracer import Tracer
from codelab.server.protocol.handlers.slash_commands.builtin.context import (
    ContextCommandHandler,
)


class TestContextCommandHandler:
    """Тесты для /context slash-команды."""

    def _make_session(self, session_id: str = "test-session") -> MagicMock:
        """Создать mock SessionState."""
        session = MagicMock()
        session.session_id = session_id
        session.config_values = {}
        return session

    def test_show_summary_no_metrics(self):
        """/context без метрик показывает 'нет данных'."""
        tracker = MetricsTracker()
        handler = ContextCommandHandler(tracker)
        session = self._make_session()

        result = handler.execute([], session)

        assert len(result.content) == 1
        text = result.content[0]["text"]
        assert "Context Manager" in text
        assert "нет данных" in text

    def test_show_summary_with_metrics(self):
        """/context с метриками показывает статистику."""
        tracker = MetricsTracker()
        tracker.record_context_build(
            build_duration_ms=50.0,
            gathered_files=5,
            baseline_tokens=2000,
            tail_tokens=500,
            session_id="test-session",
        )
        handler = ContextCommandHandler(tracker)
        session = self._make_session()

        result = handler.execute([], session)

        text = result.content[0]["text"]
        assert "Сборок контекста" in text
        assert "5" in text or "2,000" in text

    def test_show_spans_no_tracer(self):
        """/context spans без tracer показывает предупреждение."""
        tracker = MetricsTracker()
        handler = ContextCommandHandler(tracker, tracer=None)
        session = self._make_session()

        result = handler.execute(["spans"], session)

        text = result.content[0]["text"]
        assert "Tracer не инициализирован" in text

    def test_show_spans_empty(self):
        """/context spans без span'ов показывает 'нет span'ов'."""
        tracker = MetricsTracker()
        tracer = Tracer()
        handler = ContextCommandHandler(tracker, tracer)
        session = self._make_session()

        result = handler.execute(["spans"], session)

        text = result.content[0]["text"]
        assert "Нет span'ов" in text

    def test_show_spans_with_context_spans(self):
        """/context spans показывает context.build и context.gather."""
        tracker = MetricsTracker()
        tracer = Tracer()
        handler = ContextCommandHandler(tracker, tracer)
        session = self._make_session()

        # Создаём span'ы
        span1 = tracer.start_span("context.build", session_id="test-session")
        tracer.end_span(span1, attributes={
            "agent_scope": "single",
            "task_type": "feature",
            "gathered_files": 3,
            "baseline_tokens": 1000,
        })

        span2 = tracer.start_span("context.gather", session_id="test-session")
        tracer.end_span(span2, attributes={
            "task_type": "feature",
            "candidate_files": 10,
            "selected_files": 3,
        })

        result = handler.execute(["spans"], session)

        text = result.content[0]["text"]
        assert "context.build" in text
        assert "context.gather" in text

    def test_context_on(self):
        """/context on включает Context Manager."""
        tracker = MetricsTracker()
        handler = ContextCommandHandler(tracker)
        session = self._make_session()
        session.config_values["context_enabled"] = "false"

        result = handler.execute(["on"], session)

        text = result.content[0]["text"]
        assert "включён" in text
        assert session.config_values["context_enabled"] == "true"

    def test_context_off(self):
        """/context off выключает Context Manager."""
        tracker = MetricsTracker()
        handler = ContextCommandHandler(tracker)
        session = self._make_session()
        session.config_values["context_enabled"] = "true"

        result = handler.execute(["off"], session)

        text = result.content[0]["text"]
        assert "выключен" in text
        assert session.config_values["context_enabled"] == "false"

    def test_context_already_enabled(self):
        """/context on когда уже включён показывает 'уже включён'."""
        tracker = MetricsTracker()
        handler = ContextCommandHandler(tracker)
        session = self._make_session()
        session.config_values["context_enabled"] = "true"

        result = handler.execute(["on"], session)

        text = result.content[0]["text"]
        assert "уже включён" in text

    def test_context_unknown_subcommand(self):
        """/context unknown показывает ошибку и подсказку."""
        tracker = MetricsTracker()
        handler = ContextCommandHandler(tracker)
        session = self._make_session()

        result = handler.execute(["unknown"], session)

        text = result.content[0]["text"]
        assert "Неизвестная подкоманда" in text
        assert "spans" in text
        assert "on" in text
        assert "off" in text

    def test_get_definition(self):
        """get_definition() возвращает корректное определение."""
        tracker = MetricsTracker()
        handler = ContextCommandHandler(tracker)

        definition = handler.get_definition()

        assert definition.name == "context"
        assert "Context Manager" in definition.description
        assert definition.input is not None
        assert "spans" in definition.input.hint

"""Тесты для ContextCommandHandler."""

from __future__ import annotations

from unittest.mock import MagicMock

from codelab.server.agent.context.models import ContextConfig
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

    def _make_config(self, enabled: bool = False, gather_enabled: bool = True) -> ContextConfig:
        """Создать ContextConfig для тестов."""
        return ContextConfig(enabled=enabled, gather_enabled=gather_enabled)

    def test_show_summary_no_metrics(self):
        """/context без метрик показывает 'нет данных'."""
        tracker = MetricsTracker()
        config = self._make_config()
        handler = ContextCommandHandler(tracker, config)
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
        config = self._make_config()
        handler = ContextCommandHandler(tracker, config)
        session = self._make_session()

        result = handler.execute([], session)

        text = result.content[0]["text"]
        assert "Сборок контекста" in text
        assert "5" in text or "2,000" in text

    def test_show_summary_enabled_status(self):
        """/context показывает правильный статус из конфигурации."""
        tracker = MetricsTracker()
        config = self._make_config(enabled=True, gather_enabled=True)
        handler = ContextCommandHandler(tracker, config)
        session = self._make_session()

        result = handler.execute([], session)

        text = result.content[0]["text"]
        assert "enabled=True" in text
        assert "gather=on" in text
        assert "✅" in text

    def test_show_summary_disabled_status(self):
        """/context показывает правильный статус когда выключен."""
        tracker = MetricsTracker()
        config = self._make_config(enabled=False, gather_enabled=True)
        handler = ContextCommandHandler(tracker, config)
        session = self._make_session()

        result = handler.execute([], session)

        text = result.content[0]["text"]
        assert "enabled=False" in text
        assert "⏸️" in text

    def test_context_on_runtime_override(self):
        """/context on устанавливает runtime override."""
        tracker = MetricsTracker()
        config = self._make_config(enabled=False)
        handler = ContextCommandHandler(tracker, config)
        session = self._make_session()

        result = handler.execute(["on"], session)

        text = result.content[0]["text"]
        assert "включён" in text
        assert session.config_values["context_enabled"] == "true"

        # После on статус должен показывать enabled=True
        result2 = handler.execute([], session)
        assert "enabled=True" in result2.content[0]["text"]

    def test_context_off_runtime_override(self):
        """/context off устанавливает runtime override."""
        tracker = MetricsTracker()
        config = self._make_config(enabled=True)
        handler = ContextCommandHandler(tracker, config)
        session = self._make_session()

        # Сначала проверим что статус enabled=True из конфига
        result_before = handler.execute([], session)
        assert "enabled=True" in result_before.content[0]["text"]

        # Выключаем через команду
        result = handler.execute(["off"], session)

        text = result.content[0]["text"]
        assert "выключен" in text
        assert session.config_values["context_enabled"] == "false"

        # После off статус должен показывать enabled=False
        result2 = handler.execute([], session)
        assert "enabled=False" in result2.content[0]["text"]

    def test_show_spans_no_tracer(self):
        """/context spans без tracer показывает предупреждение."""
        tracker = MetricsTracker()
        config = self._make_config()
        handler = ContextCommandHandler(tracker, config, tracer=None)
        session = self._make_session()

        result = handler.execute(["spans"], session)

        text = result.content[0]["text"]
        assert "Tracer не инициализирован" in text

    def test_show_spans_empty(self):
        """/context spans без span'ов показывает 'нет span'ов'."""
        tracker = MetricsTracker()
        tracer = Tracer()
        config = self._make_config()
        handler = ContextCommandHandler(tracker, config, tracer)
        session = self._make_session()

        result = handler.execute(["spans"], session)

        text = result.content[0]["text"]
        assert "Нет span'ов" in text

    def test_show_spans_with_context_spans(self):
        """/context spans показывает context.build и context.gather."""
        tracker = MetricsTracker()
        tracer = Tracer()
        config = self._make_config()
        handler = ContextCommandHandler(tracker, config, tracer)
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

    def test_context_unknown_subcommand(self):
        """/context unknown показывает ошибку и подсказку."""
        tracker = MetricsTracker()
        config = self._make_config()
        handler = ContextCommandHandler(tracker, config)
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
        config = self._make_config()
        handler = ContextCommandHandler(tracker, config)

        definition = handler.get_definition()

        assert definition.name == "context"
        assert "Context Manager" in definition.description
        assert definition.input is not None
        assert "spans" in definition.input.hint

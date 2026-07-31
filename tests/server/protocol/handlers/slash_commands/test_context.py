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
        """Создать mock DomainSession."""
        session = MagicMock()
        session.id = session_id
        session.config.config_values = {}
        # Seam-контракт резидента (pre-step D4-d): set_config_value пишет в config_values.
        session.set_config_value = lambda k, v: session.config.config_values.__setitem__(k, v)
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
        assert "Контекст" in text
        assert "5" in text or "2,000" in text

    def test_show_summary_llm_and_agent_sections(self):
        """/context показывает секции LLM и Агент."""
        tracker = MetricsTracker()
        tracker.record_llm_call(
            latency_ms=100.0,
            model="gpt-4",
            input_tokens=1000,
            output_tokens=500,
            session_id="test-session",
        )
        tracker.record_agent_response(
            agent_name="test-agent",
            stop_reason="end_turn",
            usage=MagicMock(input_tokens=1000, output_tokens=500, total_tokens=1500),
            session_id="test-session",
        )
        config = self._make_config()
        handler = ContextCommandHandler(tracker, config)
        session = self._make_session()

        result = handler.execute([], session)

        text = result.content[0]["text"]
        assert "LLM" in text
        assert "Агент" in text
        assert "1,000" in text

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
        assert session.config.config_values["context_enabled"] == "true"

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
        assert session.config.config_values["context_enabled"] == "false"

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
        tracer.end_span(
            span1,
            attributes={
                "agent_scope": "single",
                "task_type": "feature",
                "gathered_files": 3,
                "baseline_tokens": 1000,
            },
        )

        span2 = tracer.start_span("context.gather", session_id="test-session")
        tracer.end_span(
            span2,
            attributes={
                "task_type": "feature",
                "candidate_files": 10,
                "selected_files": 3,
            },
        )

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
        assert "config" in text
        assert "last" in text
        assert "files" in text
        assert "graph" in text
        assert "profile" in text
        assert "spans" in text
        assert "on" in text
        assert "off" in text

    def test_show_config(self):
        """/context config показывает полную конфигурацию."""
        tracker = MetricsTracker()
        config = self._make_config(enabled=True)
        handler = ContextCommandHandler(tracker, config)
        session = self._make_session()

        result = handler.execute(["config"], session)

        text = result.content[0]["text"]
        assert "Конфигурация" in text
        assert "enabled" in text
        assert "gather_enabled" in text
        assert "max_context_tokens" in text
        assert "system" in text
        assert "history" in text

    def test_show_config_with_runtime_overrides(self):
        """/context config показывает runtime overrides."""
        tracker = MetricsTracker()
        config = self._make_config()
        handler = ContextCommandHandler(tracker, config)
        session = self._make_session()
        session.config.config_values["context_enabled"] = "true"

        result = handler.execute(["config"], session)

        text = result.content[0]["text"]
        assert "Runtime overrides" in text
        assert "context_enabled" in text

    def test_show_last_no_details(self):
        """/context last без debug details показывает сообщение."""
        tracker = MetricsTracker()
        config = self._make_config()
        handler = ContextCommandHandler(tracker, config)
        session = self._make_session()

        result = handler.execute(["last"], session)

        text = result.content[0]["text"]
        assert "Детали недоступны" in text

    def test_show_last_with_details(self):
        """/context last показывает детали последней сборки."""
        tracker = MetricsTracker()
        tracker.record_context_build(
            build_duration_ms=100.0,
            gathered_files=3,
            baseline_tokens=1500,
            tail_tokens=300,
            session_id="test-session",
            task_type="feature",
            file_paths=["src/a.py", "src/b.py"],
            stage_timings={"extract_ms": 5.0, "analyze_ms": 20.0},
            graph_stats={"files_in_graph": 10},
        )
        config = self._make_config()
        handler = ContextCommandHandler(tracker, config)
        session = self._make_session()

        result = handler.execute(["last"], session)

        text = result.content[0]["text"]
        assert "Последняя сборка" in text
        assert "feature" in text
        assert "100ms" in text

    def test_show_files_no_details(self):
        """/context files без debug details показывает сообщение."""
        tracker = MetricsTracker()
        config = self._make_config()
        handler = ContextCommandHandler(tracker, config)
        session = self._make_session()

        result = handler.execute(["files"], session)

        text = result.content[0]["text"]
        assert "недоступен" in text

    def test_show_files_with_files(self):
        """/context files показывает список файлов."""
        tracker = MetricsTracker()
        tracker.record_context_build(
            build_duration_ms=100.0,
            gathered_files=2,
            baseline_tokens=1000,
            tail_tokens=200,
            session_id="test-session",
            file_paths=["src/a.py", "src/b.py"],
        )
        config = self._make_config()
        handler = ContextCommandHandler(tracker, config)
        session = self._make_session()

        result = handler.execute(["files"], session)

        text = result.content[0]["text"]
        assert "src/a.py" in text
        assert "src/b.py" in text

    def test_show_graph_no_details(self):
        """/context graph без debug details показывает сообщение."""
        tracker = MetricsTracker()
        config = self._make_config()
        handler = ContextCommandHandler(tracker, config)
        session = self._make_session()

        result = handler.execute(["graph"], session)

        text = result.content[0]["text"]
        assert "не инициализирован" in text

    def test_show_graph_with_stats(self):
        """/context graph показывает статистику графа."""
        tracker = MetricsTracker()
        tracker.record_context_build(
            build_duration_ms=100.0,
            gathered_files=2,
            baseline_tokens=1000,
            tail_tokens=200,
            session_id="test-session",
            graph_stats={
                "files_in_graph": 50,
                "total_dependencies": 120,
                "total_dependents": 120,
                "project_files_cached": 200,
            },
        )
        config = self._make_config()
        handler = ContextCommandHandler(tracker, config)
        session = self._make_session()

        result = handler.execute(["graph"], session)

        text = result.content[0]["text"]
        assert "Граф зависимостей" in text
        assert "50" in text
        assert "120" in text

    def test_show_profile_no_profile(self):
        """/context profile без профиля показывает сообщение."""
        tracker = MetricsTracker()
        config = self._make_config()
        handler = ContextCommandHandler(tracker, config)
        session = self._make_session()

        result = handler.execute(["profile"], session)

        text = result.content[0]["text"]
        assert "Профиль задачи недоступен" in text

    def test_show_profile_with_profile(self):
        """/context profile показывает последний профиль задачи."""
        tracker = MetricsTracker()
        # Сначала создаём сессию через record, чтобы она сохранилась
        tracker.record_context_build(0.0, 0, 0, 0, "test-session")
        metrics = tracker.get_metrics("test-session")
        metrics.last_task_profile = {
            "task_type": "bug_fix",
            "search_terms": ["auth", "crash"],
            "target_modules": ["src/auth"],
            "investigation_depth": 2,
            "needs_tests": True,
        }
        config = self._make_config()
        handler = ContextCommandHandler(tracker, config)
        session = self._make_session()

        result = handler.execute(["profile"], session)

        text = result.content[0]["text"]
        assert "последний профиль задачи" in text.lower()
        assert "bug_fix" in text
        assert "auth" in text

    def test_get_definition(self):
        """get_definition() возвращает корректное определение."""
        tracker = MetricsTracker()
        config = self._make_config()
        handler = ContextCommandHandler(tracker, config)

        definition = handler.get_definition()

        assert definition.name == "context"
        assert "Context Manager" in definition.description
        assert definition.input is not None
        assert "config" in definition.input.hint
        assert "last" in definition.input.hint
        assert "files" in definition.input.hint
        assert "graph" in definition.input.hint
        assert "profile" in definition.input.hint
        assert "spans" in definition.input.hint

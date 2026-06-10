"""Интеграционные тесты observability file persistence."""

import asyncio
import json
from pathlib import Path

from codelab.server.observability.event_timeline import EventTimeline
from codelab.server.observability.exporters import (
    FileEventExporter,
    FileMetricsExporter,
    FileSpanExporter,
)
from codelab.server.observability.metrics_tracker import MetricsTracker
from codelab.server.observability.tracer import Tracer


class TestObservabilityFilePersistenceIntegration:
    """Интеграционные тесты полного цикла observability → файлы."""

    def test_span_to_file_cycle(self, tmp_path: Path) -> None:
        """Полный цикл: span → Tracer → FileSpanExporter → файл."""
        exporter = FileSpanExporter(export_dir=str(tmp_path))
        tracer = Tracer()

        # Создаём span hierarchy
        parent = tracer.start_span("parent_span", session_id="sess_1")
        child = tracer.start_span("child_span", parent=parent, session_id="sess_1")
        tracer.end_span(child, {"result": "success"})
        tracer.end_span(parent)

        # Экспортируем
        result = exporter.flush(tracer)

        assert result is not None
        data = json.loads(result.read_text())
        assert len(data) == 2

        # Проверяем hierarchy
        child_data = next(d for d in data if d["name"] == "child_span")
        parent_data = next(d for d in data if d["name"] == "parent_span")
        assert child_data["parent_id"] == parent_data["span_id"]
        assert parent_data["parent_id"] is None

    def test_event_to_file_cycle(self, tmp_path: Path) -> None:
        """Полный цикл: event → EventTimeline → FileEventExporter → файл."""
        exporter = FileEventExporter(export_dir=str(tmp_path))
        timeline = EventTimeline()

        # Записываем события
        timeline.record_event("AgentRegistered", "sess_1", {"agent": "coder"})
        timeline.record_event("AgentResponse", "sess_1", {"stop_reason": "end_turn"})

        # Экспортируем
        result = exporter.flush(timeline)

        assert result is not None
        data = json.loads(result.read_text())
        assert len(data) == 2
        assert data[0]["event_type"] == "AgentRegistered"
        assert data[1]["event_type"] == "AgentResponse"

    def test_metrics_to_file_cycle(self, tmp_path: Path) -> None:
        """Полный цикл: metrics → MetricsTracker → FileMetricsExporter → файл."""
        exporter = FileMetricsExporter(export_dir=str(tmp_path))
        tracker = MetricsTracker()

        # Записываем метрики
        tracker.record_llm_call(
            latency_ms=1500.0,
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            session_id="sess_1",
        )
        tracker.record_llm_call(
            latency_ms=2000.0,
            model="gpt-4o",
            input_tokens=200,
            output_tokens=100,
            session_id="sess_1",
        )

        # Экспортируем
        result = exporter.flush(tracker)

        assert result is not None
        data = json.loads(result.read_text())
        assert "sess_1" in data
        assert data["sess_1"]["llm_call_count"] == 2
        assert data["sess_1"]["llm_total_input_tokens"] == 300
        assert data["sess_1"]["llm_total_output_tokens"] == 150

    async def test_periodic_flush_works(self, tmp_path: Path) -> None:
        """Periodic flush работает корректно."""
        from codelab.server.di import ObservabilityFlushManager

        exporter = FileSpanExporter(export_dir=str(tmp_path))
        event_exporter = FileEventExporter(export_dir=str(tmp_path))
        metrics_exporter = FileMetricsExporter(export_dir=str(tmp_path))

        tracer = Tracer()
        timeline = EventTimeline()
        metrics = MetricsTracker()

        # Создаём span
        span = tracer.start_span("test_span", session_id="sess_1")
        tracer.end_span(span)

        # Запускаем менеджер с коротким интервалом
        manager = ObservabilityFlushManager(enabled=True, flush_interval=1)
        await manager.start(
            tracer=tracer,
            timeline=timeline,
            metrics=metrics,
            span_exporter=exporter,
            event_exporter=event_exporter,
            metrics_exporter=metrics_exporter,
        )

        # Ждём немного больше одного интервала
        await asyncio.sleep(1.5)

        # Останавливаем
        await manager.stop()

        # Проверяем что файлы созданы
        span_files = list(tmp_path.glob("spans/*.json"))
        assert len(span_files) > 0

    def test_multiple_flushes_create_multiple_files(self, tmp_path: Path) -> None:
        """Несколько flush'ей создают несколько файлов."""
        exporter = FileSpanExporter(export_dir=str(tmp_path))
        tracer = Tracer()

        # Первый flush
        span1 = tracer.start_span("span1", session_id="sess_1")
        tracer.end_span(span1)
        exporter.flush(tracer)

        # Небольшая задержка для уникальности имени файла
        import time
        time.sleep(0.1)

        # Второй flush
        span2 = tracer.start_span("span2", session_id="sess_2")
        tracer.end_span(span2)
        exporter.flush(tracer)

        # Проверяем что создано 2 файла
        span_files = list(tmp_path.glob("spans/*.json"))
        assert len(span_files) == 2

    def test_export_dir_created_on_first_export(self, tmp_path: Path) -> None:
        """Директория экспорта создаётся лениво при первом экспорте."""
        export_dir = tmp_path / "nested" / "dir" / "observability"
        exporter = FileSpanExporter(export_dir=str(export_dir))

        # Директория ещё не создана
        assert not (export_dir / "spans").exists()

        # Создаём span и экспортируем
        tracer = Tracer()
        span = tracer.start_span("test_span")
        tracer.end_span(span)
        exporter.flush(tracer)

        # Теперь директория создана
        assert (export_dir / "spans").exists()
        assert (export_dir / "spans").is_dir()

    def test_session_completion_flush(self, tmp_path: Path) -> None:
        """Flush при завершении сессии экспортирует все данные."""
        span_exporter = FileSpanExporter(export_dir=str(tmp_path))
        event_exporter = FileEventExporter(export_dir=str(tmp_path))
        metrics_exporter = FileMetricsExporter(export_dir=str(tmp_path))

        tracer = Tracer()
        timeline = EventTimeline()
        metrics = MetricsTracker()

        # Заполняем данными
        span = tracer.start_span("session_span", session_id="sess_1")
        tracer.end_span(span)

        timeline.record_event("SessionStart", "sess_1")
        timeline.record_event("SessionEnd", "sess_1")

        metrics.record_llm_call(1000.0, "gpt-4o", 50, 30, "sess_1")

        # Flush при завершении сессии
        span_exporter.flush(tracer)
        event_exporter.flush(timeline)
        metrics_exporter.flush(metrics)

        # Проверяем все файлы
        span_files = list(tmp_path.glob("spans/*.json"))
        event_files = list(tmp_path.glob("events/*.json"))
        metrics_files = list(tmp_path.glob("metrics/*.json"))

        assert len(span_files) == 1
        assert len(event_files) == 1
        assert len(metrics_files) == 1

        # Проверяем содержимое
        span_data = json.loads(span_files[0].read_text())
        assert len(span_data) == 1
        assert span_data[0]["name"] == "session_span"

        event_data = json.loads(event_files[0].read_text())
        assert len(event_data) == 2

        metrics_data = json.loads(metrics_files[0].read_text())
        assert "sess_1" in metrics_data

"""Тесты для file exporters observability данных."""

import json
from pathlib import Path

from codelab.server.observability.event_timeline import EventTimeline, TimelineEvent
from codelab.server.observability.exporters import (
    FileEventExporter,
    FileMetricsExporter,
    FileSpanExporter,
)
from codelab.server.observability.metrics_tracker import SessionMetrics
from codelab.server.observability.tracer import Tracer


class TestFileSpanExporter:
    """Тесты для FileSpanExporter."""

    def test_export_spans_creates_file(self, tmp_path: Path) -> None:
        """Экспорт span'ов создаёт JSON файл."""
        exporter = FileSpanExporter(export_dir=str(tmp_path))

        tracer = Tracer()
        span = tracer.start_span("test_span", session_id="sess_1")
        tracer.end_span(span, {"key": "value"})

        result = exporter.export_spans([span])

        assert result is not None
        assert result.exists()
        assert result.suffix == ".json"

        data = json.loads(result.read_text())
        assert len(data) == 1
        assert data[0]["name"] == "test_span"
        assert data[0]["session_id"] == "sess_1"
        assert data[0]["attributes"]["key"] == "value"

    def test_export_spans_empty_returns_none(self, tmp_path: Path) -> None:
        """Экспорт пустого списка возвращает None."""
        exporter = FileSpanExporter(export_dir=str(tmp_path))
        result = exporter.export_spans([])
        assert result is None

    def test_export_spans_multiple_spans(self, tmp_path: Path) -> None:
        """Экспорт нескольких span'ов."""
        exporter = FileSpanExporter(export_dir=str(tmp_path))

        tracer = Tracer()
        span1 = tracer.start_span("span1", session_id="sess_1")
        tracer.end_span(span1)
        span2 = tracer.start_span("span2", session_id="sess_1")
        tracer.end_span(span2)

        result = exporter.export_spans([span1, span2])

        assert result is not None
        data = json.loads(result.read_text())
        assert len(data) == 2
        assert data[0]["name"] == "span1"
        assert data[1]["name"] == "span2"

    def test_flush_clears_tracer(self, tmp_path: Path) -> None:
        """Flush очищает tracer после экспорта."""
        exporter = FileSpanExporter(export_dir=str(tmp_path))

        tracer = Tracer()
        span = tracer.start_span("test_span", session_id="sess_1")
        tracer.end_span(span)

        assert len(tracer.get_completed_spans()) == 1

        exporter.flush(tracer)

        assert len(tracer.get_completed_spans()) == 0

    def test_flush_non_tracer_returns_none(self, tmp_path: Path) -> None:
        """Flush с не-Tracer объектом возвращает None."""
        exporter = FileSpanExporter(export_dir=str(tmp_path))
        result = exporter.flush("not_a_tracer")
        assert result is None

    def test_rotation_creates_rotated_file(self, tmp_path: Path) -> None:
        """Ротация создаёт файл с суффиксом .rotated при превышении max_file_size."""
        # Маленький max_file_size для теста
        exporter = FileSpanExporter(export_dir=str(tmp_path), max_file_size=100)

        tracer = Tracer()
        # Создаём span с большим количеством атрибутов
        span = tracer.start_span("large_span", session_id="sess_1")
        tracer.end_span(span, {"data": "x" * 200})

        result = exporter.export_spans([span])

        assert result is not None
        # Проверяем что создан .rotated файл
        rotated = result.with_suffix(f"{result.suffix}.rotated")
        assert rotated.exists()


class TestFileEventExporter:
    """Тесты для FileEventExporter."""

    def test_export_events_creates_file(self, tmp_path: Path) -> None:
        """Экспорт событий создаёт JSON файл."""
        exporter = FileEventExporter(export_dir=str(tmp_path))

        event = TimelineEvent(
            event_type="AgentResponse",
            session_id="sess_1",
            details={"agent": "coder", "status": "ok"},
        )

        result = exporter.export_events([event])

        assert result is not None
        assert result.exists()

        data = json.loads(result.read_text())
        assert len(data) == 1
        assert data[0]["event_type"] == "AgentResponse"
        assert data[0]["session_id"] == "sess_1"

    def test_export_events_empty_returns_none(self, tmp_path: Path) -> None:
        """Экспорт пустого списка возвращает None."""
        exporter = FileEventExporter(export_dir=str(tmp_path))
        result = exporter.export_events([])
        assert result is None

    def test_append_mode_adds_to_existing(self, tmp_path: Path) -> None:
        """Append mode добавляет события в существующий файл."""
        exporter = FileEventExporter(export_dir=str(tmp_path))

        event1 = TimelineEvent(event_type="Event1", session_id="sess_1")
        event2 = TimelineEvent(event_type="Event2", session_id="sess_1")

        # Первый экспорт
        result1 = exporter.export_events([event1])
        assert result1 is not None

        # Второй экспорт
        result2 = exporter.export_events([event2])
        assert result2 is not None

        # Проверяем что файл содержит оба события
        data = json.loads(result2.read_text())
        assert len(data) == 2
        assert data[0]["event_type"] == "Event1"
        assert data[1]["event_type"] == "Event2"

    def test_flush_clears_timeline(self, tmp_path: Path) -> None:
        """Flush очищает timeline после экспорта."""
        exporter = FileEventExporter(export_dir=str(tmp_path))

        timeline = EventTimeline()
        timeline.record_event("Test", "sess_1")

        assert len(timeline.get_events()) == 1

        exporter.flush(timeline)

        assert len(timeline.get_events()) == 0

    def test_flush_non_timeline_returns_none(self, tmp_path: Path) -> None:
        """Flush с не-EventTimeline объектом возвращает None."""
        exporter = FileEventExporter(export_dir=str(tmp_path))
        result = exporter.flush("not_a_timeline")
        assert result is None


class TestFileMetricsExporter:
    """Тесты для FileMetricsExporter."""

    def test_export_metrics_creates_file(self, tmp_path: Path) -> None:
        """Экспорт метрик создаёт JSON файл."""
        exporter = FileMetricsExporter(export_dir=str(tmp_path))

        metrics = {
            "sess_1": SessionMetrics(
                session_id="sess_1",
                llm_call_count=5,
                agent_responses=3,
            )
        }

        result = exporter.export_metrics(metrics)

        assert result is not None
        assert result.exists()

        data = json.loads(result.read_text())
        assert "sess_1" in data
        assert data["sess_1"]["llm_call_count"] == 5
        assert data["sess_1"]["agent_responses"] == 3

    def test_export_metrics_empty_returns_none(self, tmp_path: Path) -> None:
        """Экспорт пустых метрик возвращает None."""
        exporter = FileMetricsExporter(export_dir=str(tmp_path))
        result = exporter.export_metrics({})
        assert result is None

    def test_export_metrics_overwrites(self, tmp_path: Path) -> None:
        """Экспорт метрик перезаписывает файл (overwrite mode)."""
        exporter = FileMetricsExporter(export_dir=str(tmp_path))

        metrics1 = {"sess_1": SessionMetrics(session_id="sess_1", llm_call_count=1)}
        metrics2 = {"sess_2": SessionMetrics(session_id="sess_2", llm_call_count=2)}

        exporter.export_metrics(metrics1)
        result = exporter.export_metrics(metrics2)

        assert result is not None
        data = json.loads(result.read_text())
        # Должна быть только sess_2 (overwrite)
        assert "sess_1" not in data
        assert "sess_2" in data
        assert data["sess_2"]["llm_call_count"] == 2

    def test_flush_non_metrics_tracker_returns_none(self, tmp_path: Path) -> None:
        """Flush с не-MetricsTracker объектом возвращает None."""
        exporter = FileMetricsExporter(export_dir=str(tmp_path))
        result = exporter.flush("not_a_tracker")
        assert result is None

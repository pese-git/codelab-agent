"""Тесты для улучшений observability exporters (Phase 1).

Тестирует:
- Tracer: mark_exported(), clear_exported()
- EventTimeline: mark_exported(), clear_exported(), clear() не отписывается
- FileSpanExporter: flush() с mark/clear, cleanup(), get_metrics()
- FileEventExporter: flush() с mark/clear, cleanup(), get_metrics()
"""

from __future__ import annotations

from pathlib import Path

from codelab.server.observability.event_timeline import EventTimeline
from codelab.server.observability.exporters import (
    FileEventExporter,
    FileMetricsExporter,
    FileSpanExporter,
)
from codelab.server.observability.metrics_tracker import MetricsTracker, SessionMetrics
from codelab.server.observability.tracer import Tracer


class TestTracerExportMethods:
    """Тесты методов экспорта Tracer."""

    def test_mark_exported_updates_count(self) -> None:
        """mark_exported() обновляет _exported_count."""
        tracer = Tracer()

        # Создаём 3 завершённых span'а
        for i in range(3):
            span = tracer.start_span(f"span_{i}")
            tracer.end_span(span)

        assert len(tracer.get_completed_spans()) == 3
        assert tracer._exported_count == 0

        # Отмечаем 2 как экспортированные
        tracer.mark_exported(2)
        assert tracer._exported_count == 2

    def test_clear_exported_removes_exported_spans(self) -> None:
        """clear_exported() удаляет экспортированные span'ы."""
        tracer = Tracer()

        # Создаём 3 завершённых span'а
        for i in range(3):
            span = tracer.start_span(f"span_{i}")
            tracer.end_span(span)

        # Отмечаем 2 как экспортированные и очищаем
        tracer.mark_exported(2)
        tracer.clear_exported()

        # Должен остаться 1 span
        assert len(tracer.get_completed_spans()) == 1
        assert tracer._exported_count == 0

    def test_clear_exported_preserves_active_spans(self) -> None:
        """clear_exported() не затрагивает активные span'ы."""
        tracer = Tracer()

        # Создаём 2 завершённых и 1 активный span
        span1 = tracer.start_span("span_1")
        tracer.end_span(span1)
        span2 = tracer.start_span("span_2")
        tracer.end_span(span2)
        active_span = tracer.start_span("active_span")

        assert len(tracer.get_completed_spans()) == 2
        assert tracer.get_current_span() == active_span

        # Отмечаем все завершённые как экспортированные и очищаем
        tracer.mark_exported(2)
        tracer.clear_exported()

        # Активный span должен остаться
        assert tracer.get_current_span() == active_span
        assert len(tracer.get_completed_spans()) == 0

    def test_clear_resets_exported_count(self) -> None:
        """clear() сбрасывает _exported_count."""
        tracer = Tracer()

        span = tracer.start_span("span_1")
        tracer.end_span(span)

        tracer.mark_exported(1)
        assert tracer._exported_count == 1

        tracer.clear()
        assert tracer._exported_count == 0
        assert len(tracer.get_completed_spans()) == 0


class TestEventTimelineExportMethods:
    """Тесты методов экспорта EventTimeline."""

    def test_mark_exported_updates_count(self) -> None:
        """mark_exported() обновляет _exported_count."""
        timeline = EventTimeline()

        # Создаём 3 события
        for i in range(3):
            timeline.record_event(f"event_{i}", "session_1")

        assert len(timeline.get_events()) == 3
        assert timeline._exported_count == 0

        # Отмечаем 2 как экспортированные
        timeline.mark_exported(2)
        assert timeline._exported_count == 2

    def test_clear_exported_removes_exported_events(self) -> None:
        """clear_exported() удаляет экспортированные события."""
        timeline = EventTimeline()

        # Создаём 3 события
        for i in range(3):
            timeline.record_event(f"event_{i}", "session_1")

        # Отмечаем 2 как экспортированные и очищаем
        timeline.mark_exported(2)
        timeline.clear_exported()

        # Должно остаться 1 событие
        assert len(timeline.get_events()) == 1
        assert timeline._exported_count == 0

    def test_clear_does_not_clear_subscriptions(self) -> None:
        """clear() не очищает подписки на EventBus."""
        timeline = EventTimeline()

        # Имитируем подписку
        timeline._subscriptions.append("mock_subscription")

        # Создаём события
        timeline.record_event("event_1", "session_1")

        # Очищаем
        timeline.clear()

        # Подписки должны остаться
        assert len(timeline._subscriptions) == 1
        assert timeline._exported_count == 0


class TestFileSpanExporterPhase1:
    """Тесты улучшений FileSpanExporter (Phase 1)."""

    def test_flush_calls_mark_and_clear(self, tmp_path: Path) -> None:
        """flush() вызывает mark_exported() и clear_exported()."""
        exporter = FileSpanExporter(export_dir=str(tmp_path))
        tracer = Tracer()

        # Создаём 3 завершённых span'а
        for i in range(3):
            span = tracer.start_span(f"span_{i}")
            tracer.end_span(span)

        assert len(tracer.get_completed_spans()) == 3

        # Экспортируем
        result = exporter.flush(tracer)

        # Файл должен быть создан
        assert result is not None
        assert result.exists()

        # Все span'ы должны быть очищены
        assert len(tracer.get_completed_spans()) == 0
        assert tracer._exported_count == 0

    def test_cleanup_removes_old_files(self, tmp_path: Path) -> None:
        """cleanup() удаляет старые файлы."""
        exporter = FileSpanExporter(export_dir=str(tmp_path))

        # Создаём директорию
        exporter._ensure_dir()

        # Создаём старый файл (31 день назад)
        old_file = exporter.export_dir / "2024-01-01-00-00-00.json"
        old_file.write_text("[]")

        # Устанавливаем старое время модификации
        import time
        old_time = time.time() - (31 * 24 * 60 * 60)  # 31 день назад
        import os
        os.utime(old_file, (old_time, old_time))

        # Создаём новый файл
        new_file = exporter.export_dir / "2026-06-10-00-00-00.json"
        new_file.write_text("[]")

        # Очищаем файлы старше 30 дней
        removed = exporter.cleanup(max_age_days=30)

        assert removed == 1
        assert not old_file.exists()
        assert new_file.exists()

    def test_metrics_updated_on_success(self, tmp_path: Path) -> None:
        """Метрики обновляются при успешном экспорте."""
        exporter = FileSpanExporter(export_dir=str(tmp_path))
        tracer = Tracer()

        # Создаём span
        span = tracer.start_span("span_1")
        tracer.end_span(span)

        # Проверяем начальные метрики
        metrics = exporter.get_metrics()
        assert metrics.total_exports == 0
        assert metrics.total_items_exported == 0

        # Экспортируем
        exporter.flush(tracer)

        # Проверяем обновлённые метрики
        metrics = exporter.get_metrics()
        assert metrics.total_exports == 1
        assert metrics.total_items_exported == 1
        assert metrics.last_export_time is not None
        assert metrics.last_export_size_bytes > 0


class TestFileEventExporterPhase1:
    """Тесты улучшений FileEventExporter (Phase 1)."""

    def test_flush_calls_mark_and_clear(self, tmp_path: Path) -> None:
        """flush() вызывает mark_exported() и clear_exported()."""
        exporter = FileEventExporter(export_dir=str(tmp_path))
        timeline = EventTimeline()

        # Создаём 3 события
        for i in range(3):
            timeline.record_event(f"event_{i}", "session_1")

        assert len(timeline.get_events()) == 3

        # Экспортируем
        result = exporter.flush(timeline)

        # Файл должен быть создан
        assert result is not None
        assert result.exists()

        # Все события должны быть очищены
        assert len(timeline.get_events()) == 0
        assert timeline._exported_count == 0

    def test_cleanup_removes_old_files(self, tmp_path: Path) -> None:
        """cleanup() удаляет старые файлы."""
        exporter = FileEventExporter(export_dir=str(tmp_path))

        # Создаём директорию
        exporter._ensure_dir()

        # Создаём старый файл (31 день назад)
        old_file = exporter.export_dir / "2024-01-01.json"
        old_file.write_text("[]")

        # Устанавливаем старое время модификации
        import time
        old_time = time.time() - (31 * 24 * 60 * 60)  # 31 день назад
        import os
        os.utime(old_file, (old_time, old_time))

        # Создаём новый файл
        new_file = exporter.export_dir / "2026-06-10.json"
        new_file.write_text("[]")

        # Очищаем файлы старше 30 дней
        removed = exporter.cleanup(max_age_days=30)

        assert removed == 1
        assert not old_file.exists()
        assert new_file.exists()

    def test_metrics_updated_on_success(self, tmp_path: Path) -> None:
        """Метрики обновляются при успешном экспорте."""
        exporter = FileEventExporter(export_dir=str(tmp_path))
        timeline = EventTimeline()

        # Создаём событие
        timeline.record_event("event_1", "session_1")

        # Проверяем начальные метрики
        metrics = exporter.get_metrics()
        assert metrics.total_exports == 0

        # Экспортируем
        exporter.flush(timeline)

        # Проверяем обновлённые метрики
        metrics = exporter.get_metrics()
        assert metrics.total_exports == 1
        assert metrics.total_items_exported == 1


class TestFileMetricsExporterPhase1:
    """Тесты улучшений FileMetricsExporter (Phase 1)."""

    def test_cleanup_removes_old_files(self, tmp_path: Path) -> None:
        """cleanup() удаляет старые файлы."""
        exporter = FileMetricsExporter(export_dir=str(tmp_path))

        # Создаём директорию
        exporter._ensure_dir()

        # Создаём старый файл (31 день назад)
        old_file = exporter.export_dir / "2024-01-01.json"
        old_file.write_text("{}")

        # Устанавливаем старое время модификации
        import time
        old_time = time.time() - (31 * 24 * 60 * 60)  # 31 день назад
        import os
        os.utime(old_file, (old_time, old_time))

        # Создаём новый файл
        new_file = exporter.export_dir / "2026-06-10.json"
        new_file.write_text("{}")

        # Очищаем файлы старше 30 дней
        removed = exporter.cleanup(max_age_days=30)

        assert removed == 1
        assert not old_file.exists()
        assert new_file.exists()

    def test_metrics_updated_on_success(self, tmp_path: Path) -> None:
        """Метрики обновляются при успешном экспорте."""
        exporter = FileMetricsExporter(export_dir=str(tmp_path))
        metrics_tracker = MetricsTracker()

        # Создаём метрику
        metrics_tracker._sessions["session_1"] = SessionMetrics(session_id="session_1")

        # Проверяем начальные метрики
        metrics = exporter.get_metrics()
        assert metrics.total_exports == 0

        # Экспортируем
        exporter.flush(metrics_tracker)

        # Проверяем обновлённые метрики
        metrics = exporter.get_metrics()
        assert metrics.total_exports == 1
        assert metrics.total_items_exported == 1

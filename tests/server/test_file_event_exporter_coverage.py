"""Тесты для непокрытых веток FileEventExporter.

Покрывают обработку повреждённого существующего файла, ошибки записи,
ошибки ротации и cleanup при отсутствии директории.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from codelab.server.observability.event_timeline import TimelineEvent
from codelab.server.observability.exporters.file_event_exporter import FileEventExporter


class TestFileEventExporterExistingFileHandling:
    """Тесты обработки существующего файла событий."""

    def test_invalid_existing_json_replaced(self, tmp_path: Path) -> None:
        """Невалидное содержимое существующего файла заменяется новыми событиями."""
        exporter = FileEventExporter(export_dir=str(tmp_path))
        exporter._ensure_dir()
        date_str = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        file_path = exporter.export_dir / f"{date_str}.json"
        file_path.write_text('{"not": "a list"}')

        event = TimelineEvent(event_type="TestEvent", session_id="sess_1")
        result = exporter.export_events([event])

        assert result is not None
        data = json.loads(result.read_text())
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["event_type"] == "TestEvent"

    def test_existing_json_decode_error_replaced(self, tmp_path: Path) -> None:
        """Невалидный JSON в существующем файле заменяется новыми событиями."""
        exporter = FileEventExporter(export_dir=str(tmp_path))
        exporter._ensure_dir()
        date_str = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        file_path = exporter.export_dir / f"{date_str}.json"
        file_path.write_text("not json at all")

        event = TimelineEvent(event_type="TestEvent", session_id="sess_1")
        result = exporter.export_events([event])

        assert result is not None
        data = json.loads(result.read_text())
        assert len(data) == 1


class TestFileEventExporterErrors:
    """Тесты ошибочных сценариев экспорта."""

    def test_export_events_exception_increments_failed_metrics(
        self,
        tmp_path: Path,
    ) -> None:
        """Исключение при записи увеличивает failed_exports и не пробрасывается."""
        exporter = FileEventExporter(export_dir=str(tmp_path))
        event = TimelineEvent(event_type="TestEvent", session_id="sess_1")

        with patch(
            "codelab.server.observability.exporters.file_event_exporter.json.dump",
            side_effect=RuntimeError("write failed"),
        ):
            result = exporter.export_events([event])

        assert result is None
        assert exporter._metrics.failed_exports == 1

    def test_rotation_failure_still_exports(
        self,
        tmp_path: Path,
    ) -> None:
        """Ошибка ротации не мешает экспорту в текущий файл."""
        exporter = FileEventExporter(export_dir=str(tmp_path), max_file_size=1)
        exporter._ensure_dir()
        date_str = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        file_path = exporter.export_dir / f"{date_str}.json"
        file_path.write_text("existing content")

        archive_name = file_path.stem + "_000000"
        archive_path = file_path.with_name(archive_name + file_path.suffix)
        archive_path.write_text("")

        event = TimelineEvent(event_type="TestEvent", session_id="sess_1")

        result = exporter.export_events([event])

        assert result == file_path
        assert result.exists()

    def test_cleanup_nonexistent_dir_returns_zero(self, tmp_path: Path) -> None:
        """cleanup возвращает 0 если директория экспорта не существует."""
        exporter = FileEventExporter(export_dir=str(tmp_path / "missing"))

        assert exporter.cleanup() == 0

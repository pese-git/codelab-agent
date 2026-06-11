"""FileEventExporter — экспорт событий EventTimeline в JSON файлы.

Поддерживает:
- Append mode — добавление событий в существующий файл дня
- Формат файла: events/YYYY-MM-DD.json (один файл на день)
- Ротацию файлов при достижении max_file_size
- Очистку старых файлов по возрасту
- Метрики экспорта
"""

from __future__ import annotations

import json
import logging
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codelab.server.observability.event_timeline import EventTimeline, TimelineEvent

logger = logging.getLogger(__name__)


@dataclass
class ExportMetrics:
    """Метрики экспорта.

    Attributes:
        total_exports: Общее количество успешных экспортов.
        failed_exports: Общее количество неудачных экспортов.
        total_items_exported: Общее количество экспортированных элементов.
        last_export_time: Время последнего экспорта (timestamp).
        last_export_size_bytes: Размер последнего экспортированного файла (байты).
    """

    total_exports: int = 0
    failed_exports: int = 0
    total_items_exported: int = 0
    last_export_time: float | None = None
    last_export_size_bytes: int = 0


class FileEventExporter:
    """Экспортёр событий в JSON файлы.

    Attributes:
        export_dir: Базовая директория для экспорта.
        max_file_size: Максимальный размер файла перед ротацией (байты).
    """

    def __init__(
        self,
        export_dir: str = "~/.codelab/data/observability",
        max_file_size: int = 10485760,
    ) -> None:
        self.export_dir = Path(export_dir).expanduser() / "events"
        self.max_file_size = max_file_size
        self._metrics = ExportMetrics()
        # Директория создаётся лениво при первом экспорте

    def _ensure_dir(self) -> None:
        """Создать директорию при первом экспорте."""
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def export_events(self, events: list[TimelineEvent]) -> Path | None:
        """Экспортировать список событий в JSON файл дня.

        Args:
            events: Список TimelineEvent для экспорта.

        Returns:
            Путь к файлу или None если события пустые.
        """
        if not events:
            return None

        self._ensure_dir()

        # Один файл на день
        date_str = datetime.now().strftime("%Y-%m-%d")
        file_path = self.export_dir / f"{date_str}.json"

        # Ротация если файл слишком большой
        file_path = self._rotate_if_needed(file_path)

        # Загружаем существующие события (append mode)
        existing_events: list[dict] = []
        if file_path.exists():
            try:
                with open(file_path, encoding="utf-8") as f:
                    existing_events = json.load(f)
                    if not isinstance(existing_events, list):
                        existing_events = []
            except (json.JSONDecodeError, Exception) as e:
                logger.warning("Failed to read existing events file %s: %s", file_path, e)
                existing_events = []

        # Добавляем новые события
        new_events = [event.to_dict(debug=True) for event in events]
        existing_events.extend(new_events)

        # Атомарная запись через временный файл
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".tmp",
                dir=self.export_dir,
                delete=False,
                encoding="utf-8",
            ) as tmp_f:
                json.dump(existing_events, tmp_f, indent=2, ensure_ascii=False)
                tmp_path = Path(tmp_f.name)

            # Заменяем оригинальный файл
            tmp_path.replace(file_path)

            # Обновляем метрики
            self._metrics.total_exports += 1
            self._metrics.total_items_exported += len(events)
            self._metrics.last_export_time = time.time()
            self._metrics.last_export_size_bytes = file_path.stat().st_size

            logger.info(
                "Exported %d events to %s (total: %d)",
                len(events), file_path, len(existing_events),
            )
            return file_path
        except Exception as e:
            self._metrics.failed_exports += 1
            logger.error("Failed to export events: %s", e)
            # Удаляем временный файл если он остался
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
            return None

    def _rotate_if_needed(self, file_path: Path) -> Path:
        """Ротировать файл если он превышает max_file_size.

        Args:
            file_path: Путь к файлу для проверки.

        Returns:
            Путь к актуальному файлу (новому если была ротация).
        """
        if not file_path.exists():
            return file_path

        try:
            file_size = file_path.stat().st_size
            if file_size <= self.max_file_size:
                return file_path

            # Архивировать текущий файл
            archive_name = file_path.stem + f"_{datetime.now().strftime('%H%M%S')}"
            archive_path = file_path.with_name(archive_name + file_path.suffix)
            file_path.rename(archive_path)
            logger.info("Rotated event file: %s -> %s", file_path, archive_path)

            # Возвращаем путь к новому файлу (который будет создан)
            return file_path
        except Exception as e:
            logger.warning("Failed to rotate event file %s: %s", file_path, e)
            return file_path

    def flush(self, timeline: EventTimeline) -> Path | None:
        """Получить события из EventTimeline и экспортировать.

        После успешного экспорта вызывает mark_exported() и clear_exported()
        для удаления экспортированных событий из EventTimeline.

        Args:
            timeline: Экземпляр EventTimeline.

        Returns:
            Путь к файлу или None.
        """
        from codelab.server.observability.event_timeline import EventTimeline

        if not isinstance(timeline, EventTimeline):
            return None

        events = timeline.get_events()
        if not events:
            return None

        result = self.export_events(events)

        if result is not None:
            # Успешный экспорт — отметить и очистить экспортированные
            timeline.mark_exported(len(events))
            timeline.clear_exported()

        return result

    def cleanup(self, max_age_days: int = 30) -> int:
        """Удалить файлы старше max_age_days.

        Args:
            max_age_days: Максимальный возраст файлов в днях.

        Returns:
            Количество удалённых файлов.
        """
        if not self.export_dir.exists():
            return 0

        cutoff = datetime.now() - timedelta(days=max_age_days)
        removed = 0

        for file in self.export_dir.glob("*.json"):
            file_time = datetime.fromtimestamp(file.stat().st_mtime)
            if file_time < cutoff:
                file.unlink()
                removed += 1

        if removed > 0:
            logger.info("Cleaned up %d old event files", removed)

        return removed

    def get_metrics(self) -> ExportMetrics:
        """Получить метрики экспорта.

        Returns:
            ExportMetrics с метриками экспорта.
        """
        return self._metrics

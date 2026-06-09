"""FileEventExporter — экспорт событий EventTimeline в JSON файлы.

Поддерживает:
- Append mode — добавление событий в существующий файл дня
- Формат файла: events/YYYY-MM-DD.json (один файл на день)
- Атомарную запись через временный файл
"""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codelab.server.observability.event_timeline import TimelineEvent

logger = logging.getLogger(__name__)


class FileEventExporter:
    """Экспортёр событий в JSON файлы.

    Attributes:
        export_dir: Базовая директория для экспорта.
    """

    def __init__(self, export_dir: str = "~/.codelab/data/observability") -> None:
        self.export_dir = Path(export_dir).expanduser() / "events"
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

        # Один файл на день
        date_str = datetime.now().strftime("%Y-%m-%d")
        file_path = self.export_dir / f"{date_str}.json"

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

            logger.info(
                "Exported %d events to %s (total: %d)",
                len(events), file_path, len(existing_events),
            )
            return file_path
        except Exception as e:
            logger.error("Failed to export events: %s", e)
            # Удаляем временный файл если он остался
            if "tmp_path" in locals():
                tmp_path.unlink(missing_ok=True)
            return None

    def flush(self, timeline: object) -> Path | None:
        """Получить события из EventTimeline и экспортировать.

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

        # Очищаем экспортированные события
        timeline.clear()

        return result

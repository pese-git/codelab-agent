"""FileSpanExporter — экспорт завершённых span'ов в JSON файлы.

Поддерживает:
- Запись span'ов в формат YYYY-MM-DD-HH-MM-SS.json
- Ротацию файлов при достижении max_file_size
- Очистку экспортированных span'ов после записи
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codelab.server.observability.tracer import SpanContext

logger = logging.getLogger(__name__)


class FileSpanExporter:
    """Экспортёр span'ов в JSON файлы.

    Attributes:
        export_dir: Базовая директория для экспорта.
        max_file_size: Максимальный размер файла перед ротацией (байты).
    """

    def __init__(
        self,
        export_dir: str = "~/.codelab/data/observability",
        max_file_size: int = 10485760,
    ) -> None:
        self.export_dir = Path(export_dir).expanduser() / "spans"
        self.max_file_size = max_file_size
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def export_spans(self, spans: list[SpanContext]) -> Path | None:
        """Экспортировать список span'ов в JSON файл.

        Args:
            spans: Список SpanContext для экспорта.

        Returns:
            Путь к созданному файлу или None если span'ы пустые.
        """
        if not spans:
            return None

        # Генерируем имя файла с текущим временем
        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        file_path = self.export_dir / f"{timestamp}.json"

        # Если файл уже существует, добавляем суффикс
        if file_path.exists():
            timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S-%f")
            file_path = self.export_dir / f"{timestamp}.json"

        # Сериализуем span'ы
        data = [span.to_dict(debug=True) for span in spans]

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info("Exported %d spans to %s", len(spans), file_path)

            # Проверяем размер файла и ротируем если нужно
            self._rotate_if_needed(file_path)

            return file_path
        except Exception as e:
            logger.error("Failed to export spans: %s", e)
            return None

    def _rotate_if_needed(self, file_path: Path) -> None:
        """Ротировать файл если он превышает max_file_size.

        Args:
            file_path: Путь к файлу для проверки.
        """
        try:
            file_size = file_path.stat().st_size
            if file_size > self.max_file_size:
                # Переименовываем файл с суффиксом .rotated
                rotated_path = file_path.with_suffix(f"{file_path.suffix}.rotated")
                file_path.rename(rotated_path)
                logger.info("Rotated span file: %s -> %s", file_path, rotated_path)
        except Exception as e:
            logger.warning("Failed to rotate span file %s: %s", file_path, e)

    def flush(self, tracer: object) -> Path | None:
        """Получить завершённые span'ы из Tracer и экспортировать.

        Args:
            tracer: Экземпляр Tracer.

        Returns:
            Путь к файлу или None.
        """
        # Импортируем здесь чтобы избежать циклических зависимостей
        from codelab.server.observability.tracer import Tracer

        if not isinstance(tracer, Tracer):
            return None

        spans = tracer.get_completed_spans()
        if not spans:
            return None

        result = self.export_spans(spans)

        # Очищаем экспортированные span'ы
        tracer.clear()

        return result

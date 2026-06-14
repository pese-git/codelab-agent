"""FileSpanExporter — экспорт завершённых span'ов в JSON файлы.

Поддерживает:
- Запись span'ов в формат YYYY-MM-DD-HH-MM-SS.json
- Ротацию файлов при достижении max_file_size
- Очистку старых файлов по возрасту
- Метрики экспорта
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codelab.server.observability.tracer import SpanContext, Tracer

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
        self._metrics = ExportMetrics()
        # Директория создаётся лениво при первом экспорте

    def _ensure_dir(self) -> None:
        """Создать директорию при первом экспорте."""
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

        self._ensure_dir()

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

            # Обновляем метрики
            self._metrics.total_exports += 1
            self._metrics.total_items_exported += len(spans)
            self._metrics.last_export_time = time.time()
            self._metrics.last_export_size_bytes = file_path.stat().st_size

            logger.info("Exported %d spans to %s", len(spans), file_path)

            # Проверяем размер файла и ротируем если нужно
            self._rotate_if_needed(file_path)

            return file_path
        except Exception as e:
            self._metrics.failed_exports += 1
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

    def flush(self, tracer: Tracer) -> Path | None:
        """Получить завершённые span'ы из Tracer и экспортировать.

        После успешного экспорта вызывает mark_exported() и clear_exported()
        для удаления экспортированных span'ов из Tracer.

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

        if result is not None:
            # Успешный экспорт — отметить и очистить экспортированные
            tracer.mark_exported(len(spans))
            tracer.clear_exported()

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

        # Также удаляем .rotated файлы
        for file in self.export_dir.glob("*.rotated"):
            file.unlink()
            removed += 1

        if removed > 0:
            logger.info("Cleaned up %d old span files", removed)

        return removed

    def get_metrics(self) -> ExportMetrics:
        """Получить метрики экспорта.

        Returns:
            ExportMetrics с метриками экспорта.
        """
        return self._metrics

"""FileMetricsExporter — экспорт метрик в JSON файлы.

Поддерживает:
- Формат файла: metrics/YYYY-MM-DD.json (один файл на день)
- Overwrite mode — полная запись всех метрик при каждом flush
- Очистку старых файлов по возрасту
- Метрики экспорта
"""

from __future__ import annotations

import json
import logging
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codelab.server.observability.metrics_tracker import MetricsTracker, SessionMetrics

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


class FileMetricsExporter:
    """Экспортёр метрик в JSON файлы.

    Attributes:
        export_dir: Базовая директория для экспорта.
    """

    # Минимальный интервал между экспортами (секунды) для предотвращения дублирования
    MIN_EXPORT_INTERVAL = 5.0

    # Class variable для отслеживания последнего экспорта across all instances
    _global_last_export_time: float = 0.0
    _flush_lock: threading.Lock = threading.Lock()  # Lock для предотвращения параллельных flush

    def __init__(self, export_dir: str = "~/.codelab/data/observability") -> None:
        self.export_dir = Path(export_dir).expanduser() / "metrics"
        self._metrics = ExportMetrics()
        # Директория создаётся лениво при первом экспорте

    def _ensure_dir(self) -> None:
        """Создать директорию при первом экспорте."""
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def export_metrics(self, metrics: dict[str, SessionMetrics]) -> Path | None:
        """Экспортировать метрики сессий в JSON файл дня.

        Args:
            metrics: Dict session_id -> SessionMetrics.

        Returns:
            Путь к файлу или None если метрики пустые или экспорт недавно выполнялся.
        """
        if not metrics:
            return None

        # Используем lock для предотвращения параллельных flush
        with FileMetricsExporter._flush_lock:
            # Защита от дублирования: не экспортируем чаще чем MIN_EXPORT_INTERVAL
            current_time = time.time()
            time_since_last = current_time - FileMetricsExporter._global_last_export_time
            if time_since_last < self.MIN_EXPORT_INTERVAL:
                logger.debug(
                    "Skipping metrics export (last export %.1fs ago)",
                    time_since_last,
                )
                return None

            self._ensure_dir()

            # Один файл на день
            date_str = datetime.now().strftime("%Y-%m-%d")
            file_path = self.export_dir / f"{date_str}.json"

            # Сериализуем метрики
            data = {}
            for session_id, session_metrics in metrics.items():
                data[session_id] = {
                    "session_id": session_metrics.session_id,
                    "bus_dispatch_count": session_metrics.bus_dispatch_count,
                    "bus_dispatch_total_ms": session_metrics.bus_dispatch_total_ms,
                    "llm_call_count": session_metrics.llm_call_count,
                    "llm_total_input_tokens": session_metrics.llm_total_input_tokens,
                    "llm_total_output_tokens": session_metrics.llm_total_output_tokens,
                    "compression_count": session_metrics.compression_count,
                    "compression_total_ratio": session_metrics.compression_total_ratio,
                    "slicer_count": session_metrics.slicer_count,
                    "slicer_total_original_tokens": session_metrics.slicer_total_original_tokens,
                    "slicer_total_sliced_tokens": session_metrics.slicer_total_sliced_tokens,
                    "slicer_total_latency_ms": session_metrics.slicer_total_latency_ms,
                    "strategy_execution_count": session_metrics.strategy_execution_count,
                    "strategy_execution_total_ms": session_metrics.strategy_execution_total_ms,
                    "agent_responses": session_metrics.agent_responses,
                    "agent_errors": session_metrics.agent_errors,
                    "context_build_count": session_metrics.context_build_count,
                    "context_build_total_ms": session_metrics.context_build_total_ms,
                    "context_gathered_files": session_metrics.context_gathered_files,
                    "context_baseline_tokens": session_metrics.context_baseline_tokens,
                    "context_tail_tokens": session_metrics.context_tail_tokens,
                    "avg_bus_dispatch_ms": session_metrics.avg_bus_dispatch_ms,
                    "avg_compression_ratio": session_metrics.avg_compression_ratio,
                }

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
                    json.dump(data, tmp_f, indent=2, ensure_ascii=False)
                    tmp_path = Path(tmp_f.name)

                # Заменяем оригинальный файл
                tmp_path.replace(file_path)

                # Обновляем метрики
                self._metrics.total_exports += 1
                self._metrics.total_items_exported += len(metrics)
                self._metrics.last_export_time = time.time()
                self._metrics.last_export_size_bytes = file_path.stat().st_size
                FileMetricsExporter._global_last_export_time = self._metrics.last_export_time

                logger.info("Exported metrics for %d sessions to %s", len(metrics), file_path)
                return file_path
            except Exception as e:
                self._metrics.failed_exports += 1
                logger.error("Failed to export metrics: %s", e)
                if tmp_path is not None:
                    tmp_path.unlink(missing_ok=True)
                return None

    def flush(self, metrics_tracker: MetricsTracker) -> Path | None:
        """Получить метрики из MetricsTracker и экспортировать.

        Args:
            metrics_tracker: Экземпляр MetricsTracker.

        Returns:
            Путь к файлу или None.
        """
        from codelab.server.observability.metrics_tracker import MetricsTracker

        if not isinstance(metrics_tracker, MetricsTracker):
            return None

        # Получаем все метрики (protected access — внутри observability пакета)
        metrics = metrics_tracker._sessions  # type: ignore[attr-defined]
        if not metrics:
            return None

        return self.export_metrics(metrics)

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
            logger.info("Cleaned up %d old metrics files", removed)

        return removed

    def get_metrics(self) -> ExportMetrics:
        """Получить метрики экспорта.

        Returns:
            ExportMetrics с метриками экспорта.
        """
        return self._metrics

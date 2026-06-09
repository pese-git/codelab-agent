"""FileMetricsExporter — экспорт метрик в JSON файлы.

Поддерживает:
- Формат файла: metrics/YYYY-MM-DD.json (один файл на день)
- Overwrite mode — полная запись всех метрик при каждом flush
"""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codelab.server.observability.metrics_tracker import SessionMetrics

logger = logging.getLogger(__name__)


class FileMetricsExporter:
    """Экспортёр метрик в JSON файлы.

    Attributes:
        export_dir: Базовая директория для экспорта.
    """

    def __init__(self, export_dir: str = "~/.codelab/data/observability") -> None:
        self.export_dir = Path(export_dir).expanduser() / "metrics"
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def export_metrics(self, metrics: dict[str, SessionMetrics]) -> Path | None:
        """Экспортировать метрики сессий в JSON файл дня.

        Args:
            metrics: Dict session_id -> SessionMetrics.

        Returns:
            Путь к файлу или None если метрики пустые.
        """
        if not metrics:
            return None

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
                "avg_bus_dispatch_ms": session_metrics.avg_bus_dispatch_ms,
                "avg_compression_ratio": session_metrics.avg_compression_ratio,
            }

        # Атомарная запись через временный файл
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

            logger.info("Exported metrics for %d sessions to %s", len(metrics), file_path)
            return file_path
        except Exception as e:
            logger.error("Failed to export metrics: %s", e)
            if "tmp_path" in locals():
                tmp_path.unlink(missing_ok=True)
            return None

    def flush(self, metrics_tracker: object) -> Path | None:
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

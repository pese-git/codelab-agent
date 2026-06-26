"""Pytest fixtures for observability tests."""

from __future__ import annotations

import pytest

from codelab.server.observability.exporters.file_metrics_exporter import (
    FileMetricsExporter,
)


@pytest.fixture(autouse=True)
def reset_metrics_export_interval():
    """Сбрасывает _global_last_export_time перед каждым тестом.

    FileMetricsExporter использует class variable для предотвращения
    дублирования экспорта в production. В тестах это мешает потому что
    тесты запускаются быстро и попадают в MIN_EXPORT_INTERVAL.
    """
    FileMetricsExporter._global_last_export_time = 0.0
    yield
    FileMetricsExporter._global_last_export_time = 0.0

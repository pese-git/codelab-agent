"""Провайдеры observability (APP scope).

Содержит маркерный тип debug-режима, менеджер периодического flush и
провайдеры трейсинга/метрик/событий с их файловыми экспортёрами.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Annotated

import structlog
from dishka import Provider, Scope, from_context, provide

from ..config import AppConfig
from ..observability import EventTimeline, MetricsTracker, Tracer
from ..observability.exporters import FileEventExporter, FileMetricsExporter, FileSpanExporter

logger = structlog.get_logger()


# Тип для observability debug mode (чтобы отличить от require_auth)
class ObservabilityDebug:
    """Marker type for observability debug mode."""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled


class ObservabilityFlushManager:
    """Менеджер периодического flush observability данных в файлы.

    Запускает asyncio task для периодического flush и предоставляет
    метод для ручного flush при завершении сессии.

    Attributes:
        enabled: Включить ли periodic flush.
        flush_interval: Интервал flush в секундах.
    """

    def __init__(
        self,
        enabled: bool = True,
        flush_interval: int = 60,
    ) -> None:
        self.enabled = enabled
        self.flush_interval = flush_interval
        self._task: asyncio.Task | None = None

    async def start(
        self,
        tracer: Tracer,
        timeline: EventTimeline,
        metrics: MetricsTracker,
        span_exporter: FileSpanExporter,
        event_exporter: FileEventExporter,
        metrics_exporter: FileMetricsExporter,
    ) -> None:
        """Запустить periodic flush task.

        Args:
            tracer: Экземпляр Tracer.
            timeline: Экземпляр EventTimeline.
            metrics: Экземпляр MetricsTracker.
            span_exporter: Экземпляр FileSpanExporter.
            event_exporter: Экземпляр FileEventExporter.
            metrics_exporter: Экземпляр FileMetricsExporter.
        """
        if not self.enabled:
            logger.info("observability flush manager disabled")
            return

        self._tracer = tracer
        self._timeline = timeline
        self._metrics = metrics
        self._span_exporter = span_exporter
        self._event_exporter = event_exporter
        self._metrics_exporter = metrics_exporter

        self._task = asyncio.create_task(self._flush_loop())
        logger.info(
            "observability flush manager started",
            flush_interval=self.flush_interval,
        )

    async def _flush_loop(self) -> None:
        """Основной цикл периодического flush."""
        while True:
            try:
                await asyncio.sleep(self.flush_interval)
                await self.flush_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in observability flush loop: %s", e)

    async def flush_all(self) -> None:
        """Выполнить flush всех observability данных."""
        try:
            span_result = None
            event_result = None
            metrics_result = None

            span_exporter = getattr(self, "_span_exporter", None)
            if span_exporter:
                span_result = span_exporter.flush(getattr(self, "_tracer", None))

            event_exporter = getattr(self, "_event_exporter", None)
            if event_exporter:
                event_result = event_exporter.flush(getattr(self, "_timeline", None))

            metrics_exporter = getattr(self, "_metrics_exporter", None)
            if metrics_exporter:
                metrics_result = metrics_exporter.flush(getattr(self, "_metrics", None))

            if span_result or event_result or metrics_result:
                logger.debug(
                    "observability data flushed",
                    spans=bool(span_result),
                    events=bool(event_result),
                    metrics=bool(metrics_result),
                )
        except Exception as e:
            logger.error("Failed to flush observability data: %s", e)

    async def stop(self) -> None:
        """Остановить periodic flush и выполнить финальный flush."""
        if self._task:
            self._task.cancel()
            with suppress(Exception):
                await self._task

        # Финальный flush
        await self.flush_all()


class ObservabilityProvider(Provider):
    """Провайдер observability компонентов (APP scope).

    Создаёт и настраивает:
    - Tracer — span hierarchy для tracing LLM вызовов
    - EventTimeline — хронология событий сессии
    - MetricsTracker — автоматический сбор метрик
    - FileSpanExporter — экспорт span'ов в файлы
    - FileEventExporter — экспорт событий в файлы
    - FileMetricsExporter — экспорт метрик в файлы
    """

    @provide(scope=Scope.APP)
    def get_tracer(
        self,
        debug: Annotated[ObservabilityDebug, from_context(provides=ObservabilityDebug)],
    ) -> Tracer:
        """Создаёт Tracer для observability."""
        return Tracer(debug=debug.enabled)

    @provide(scope=Scope.APP)
    def get_event_timeline(
        self,
        debug: Annotated[ObservabilityDebug, from_context(provides=ObservabilityDebug)],
    ) -> EventTimeline:
        """Создаёт EventTimeline для записи событий сессии."""
        return EventTimeline(debug=debug.enabled)

    @provide(scope=Scope.APP)
    def get_metrics_tracker(
        self,
        debug: Annotated[ObservabilityDebug, from_context(provides=ObservabilityDebug)],
    ) -> MetricsTracker:
        """Создаёт MetricsTracker для сбора метрик."""
        return MetricsTracker(debug=debug.enabled)

    @provide(scope=Scope.APP)
    def get_file_span_exporter(
        self,
        config: Annotated[AppConfig, from_context(provides=AppConfig)],
    ) -> FileSpanExporter:
        """Создаёт FileSpanExporter для экспорта span'ов."""
        return FileSpanExporter(
            export_dir=config.observability.export_dir,
            max_file_size=config.observability.max_file_size,
        )

    @provide(scope=Scope.APP)
    def get_file_event_exporter(
        self,
        config: Annotated[AppConfig, from_context(provides=AppConfig)],
    ) -> FileEventExporter:
        """Создаёт FileEventExporter для экспорта событий."""
        return FileEventExporter(export_dir=config.observability.export_dir)

    @provide(scope=Scope.APP)
    def get_file_metrics_exporter(
        self,
        config: Annotated[AppConfig, from_context(provides=AppConfig)],
    ) -> FileMetricsExporter:
        """Создаёт FileMetricsExporter для экспорта метрик."""
        return FileMetricsExporter(export_dir=config.observability.export_dir)


class ObservabilityFlushProvider(Provider):
    """Провайдер менеджера периодического flush observability данных."""

    @provide(scope=Scope.APP)
    async def get_flush_manager(
        self,
        config: Annotated[AppConfig, from_context(provides=AppConfig)],
        tracer: Tracer,
        timeline: EventTimeline,
        metrics: MetricsTracker,
        span_exporter: FileSpanExporter,
        event_exporter: FileEventExporter,
        metrics_exporter: FileMetricsExporter,
    ) -> AsyncIterator[ObservabilityFlushManager]:
        """Создаёт и запускает ObservabilityFlushManager."""
        manager = ObservabilityFlushManager(
            enabled=config.observability.enabled,
            flush_interval=config.observability.flush_interval,
        )

        await manager.start(
            tracer=tracer,
            timeline=timeline,
            metrics=metrics,
            span_exporter=span_exporter,
            event_exporter=event_exporter,
            metrics_exporter=metrics_exporter,
        )

        yield manager

        # Cleanup — финальный flush при остановке
        await manager.stop()

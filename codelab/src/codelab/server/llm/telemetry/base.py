"""Базовый класс для telemetry sink."""

from __future__ import annotations

from abc import ABC, abstractmethod


class TelemetrySink(ABC):
    """Абстрактный класс для сбора телеметрии LLM провайдеров.

    Реализации:
    - NoOpTelemetry: заглушка (MVP)
    - PrometheusTelemetry: экспорт метрик в Prometheus (future)
    - DatadogTelemetry: экспорт метрик в Datadog (future)
    """

    @abstractmethod
    async def record_request(
        self,
        provider_id: str,
        model_id: str,
        latency_ms: float,
        success: bool,
    ) -> None:
        """Записать метрику запроса.

        Args:
            provider_id: ID провайдера
            model_id: ID модели
            latency_ms: Задержка в миллисекундах
            success: Успешность запроса
        """
        ...

    @abstractmethod
    async def record_cost(
        self,
        provider_id: str,
        model_id: str,
        cost_usd: float,
    ) -> None:
        """Записать метрику стоимости.

        Args:
            provider_id: ID провайдера
            model_id: ID модели
            cost_usd: Стоимость в USD
        """
        ...

"""Конфигурация fallback системы."""

from __future__ import annotations

from dataclasses import dataclass, field

from codelab.server.llm.errors import ProviderErrorType


@dataclass
class FallbackConfig:
    """Конфигурация fallback цепочки.

    Атрибуты:
        enabled: Включён ли fallback
        strategy: Стратегия fallback (sequential, cost, latency, smart)
        order: Порядок провайдеров в fallback цепочке
        retry_on: Типы ошибок, при которых retry через fallback
        max_attempts: Максимальное количество попыток
        failure_threshold: Порог ошибок для circuit breaker
        reset_timeout: Время (секунды) до попытки восстановления circuit
    """

    enabled: bool = False
    strategy: str = "sequential"
    order: list[str] = field(default_factory=list)
    retry_on: list[ProviderErrorType] = field(
        default_factory=lambda: [
            ProviderErrorType.RATE_LIMIT,
            ProviderErrorType.TIMEOUT,
            ProviderErrorType.SERVICE_UNAVAILABLE,
        ]
    )
    max_attempts: int = 3
    failure_threshold: int = 5
    reset_timeout: float = 60.0

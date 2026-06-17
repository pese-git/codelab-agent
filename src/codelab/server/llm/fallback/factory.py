"""Factory для создания fallback стратегий."""

from __future__ import annotations

from codelab.server.llm.fallback.base import FallbackStrategy
from codelab.server.llm.fallback.circuit_breaker import CircuitBreaker
from codelab.server.llm.fallback.config import FallbackConfig
from codelab.server.llm.fallback.sequential import SequentialFallback


class FallbackStrategyFactory:
    """Factory для создания fallback стратегий.

    Создаёт стратегию на основе конфигурации.
    Поддерживаемые стратегии: sequential (MVP), cost, latency, smart (extension points).
    """

    @staticmethod
    def create(config: FallbackConfig) -> FallbackStrategy:
        """Создать fallback стратегию.

        Args:
            config: Конфигурация fallback

        Returns:
            Экземпляр fallback стратегии

        Raises:
            ValueError: Если стратегия не поддерживается
        """
        if config.strategy == "sequential":
            circuit_breaker = CircuitBreaker(
                failure_threshold=config.failure_threshold,
                reset_timeout=config.reset_timeout,
            )
            return SequentialFallback(
                provider_order=config.order,
                circuit_breaker=circuit_breaker,
            )
        else:
            # Extension points для future стратегий
            msg = f"Unsupported fallback strategy: {config.strategy}"
            raise ValueError(msg)

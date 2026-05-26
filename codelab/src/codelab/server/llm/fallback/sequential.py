"""Sequential fallback стратегия.

Перебирает провайдеры по порядку, пока один не обработает запрос успешно.
"""

from __future__ import annotations

import structlog

from codelab.server.llm.base import LLMProvider
from codelab.server.llm.errors import ProviderError
from codelab.server.llm.fallback.base import FallbackContext, FallbackStrategy
from codelab.server.llm.fallback.circuit_breaker import CircuitBreaker

logger = structlog.get_logger()


class SequentialFallback(FallbackStrategy):
    """Последовательная fallback стратегия.

    Перебирает провайдеры в заданном порядке.
    Если провайдер упал с retryable ошибкой — переходит к следующему.
    Если все провайдеры упали — бросает AllProvidersFailed.
    """

    def __init__(
        self,
        provider_order: list[str] | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        """Инициализация.

        Args:
            provider_order: Порядок провайдеров (по умолчанию — порядок кандидатов)
            circuit_breaker: Circuit breaker для отслеживания ошибок
        """
        self._provider_order = provider_order or []
        self._circuit_breaker = circuit_breaker
        self._failed_providers: set[str] = set()

    async def select_provider(
        self,
        candidates: list[LLMProvider],
        request: dict[str, Any],  # noqa: ARG002
        context: FallbackContext,
    ) -> LLMProvider:
        """Выбрать следующий провайдер в порядке.

        Args:
            candidates: Список доступных провайдеров
            request: Данные запроса
            context: Контекст fallback операции

        Returns:
            Следующий провайдер в порядке

        Raises:
            ProviderError: Если все провайдеры упали или circuit open
        """
        from codelab.server.llm.errors import AllProvidersFailed

        context.attempt += 1

        # Определить порядок провайдеров
        order = self._provider_order or [p.name for p in candidates]

        # Найти первого доступного провайдера
        for provider_id in order:
            # Проверить circuit breaker
            if self._circuit_breaker and self._circuit_breaker.is_circuit_open(provider_id):
                logger.debug("circuit open, skipping provider", provider_id=provider_id)
                continue

            # Проверить что провайдер уже не падал в этой цепочке
            if provider_id in self._failed_providers:
                logger.debug("provider already failed, skipping", provider_id=provider_id)
                continue

            # Найти провайдер в кандидатах
            for candidate in candidates:
                if candidate.name == provider_id:
                    return candidate

        # Все провайдеры недоступны
        raise AllProvidersFailed(
            errors=[],
            message=f"No available providers in order: {order}",
        )

    def on_success(self, provider_id: str) -> None:
        """Обработать успешный запрос.

        Сбрасывает список.failed провайдеров.

        Args:
            provider_id: ID успешного провайдера
        """
        logger.info("provider success, resetting failed list", provider_id=provider_id)
        self._failed_providers.clear()

        if self._circuit_breaker:
            self._circuit_breaker.record_success(provider_id)

    def on_failure(self, provider_id: str, error: ProviderError) -> None:
        """Обработать.failed запрос.

        Добавляет провайдер в список.failed.

        Args:
            provider_id: ID.failed провайдера
            error: Ошибка
        """
        self._failed_providers.add(provider_id)
        logger.warning(
            "provider failed, adding to failed list",
            provider_id=provider_id,
            error_type=error.error_type.value,
            retryable=error.retryable,
        )

        if self._circuit_breaker:
            self._circuit_breaker.record_failure(provider_id, error)

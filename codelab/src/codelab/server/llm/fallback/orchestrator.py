"""Оркестратор fallback системы.

Управляет выполнением fallback цепочки:
- Получает completion от primary провайдера
- При retryable ошибке переключается на следующий провайдер
- При успехе — возвращает ответ
- При всех.failed — бросает AllProvidersFailed
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import structlog

from codelab.server.llm.base import CompletionRequest, CompletionResponse, LLMProvider
from codelab.server.llm.errors import AllProvidersFailed, ProviderError
from codelab.server.llm.fallback.base import FallbackContext, FallbackStrategy
from codelab.server.llm.fallback.config import FallbackConfig

logger = structlog.get_logger()


class FallbackOrchestrator:
    """Оркестратор fallback цепочки.

    Выполняет запрос к провайдерам через fallback стратегию.
    Поддерживает как completion, так и streaming режим.
    """

    def __init__(
        self,
        strategy: FallbackStrategy,
        config: FallbackConfig,
    ) -> None:
        """Инициализация.

        Args:
            strategy: Fallback стратегия
            config: Конфигурация fallback
        """
        self._strategy = strategy
        self._config = config
        self._errors: list[ProviderError] = []

    async def execute_completion(
        self,
        providers: list[LLMProvider],
        request: CompletionRequest,
        context: FallbackContext | None = None,
    ) -> CompletionResponse:
        """Выполнить completion через fallback цепочку.

        Args:
            providers: Список провайдеров в порядке приоритета
            request: Запрос к LLM
            context: Контекст fallback (опционально)

        Returns:
            Ответ от первого успешного провайдера

        Raises:
            AllProvidersFailed: Если все провайдеры упали
        """
        if not self._config.enabled or len(providers) <= 1:
            # Fallback выключен или только один провайдер — выполнить напрямую
            return await providers[0].create_completion(request)

        context = context or FallbackContext()
        self._errors = []

        for attempt in range(self._config.max_attempts):
            try:
                provider = await self._strategy.select_provider(
                    candidates=providers,
                    request={"model": request.model},
                    context=context,
                )

                response = await provider.create_completion(request)
                self._strategy.on_success(provider.name)
                logger.info(
                    "fallback success",
                    provider_id=provider.name,
                    attempt=attempt + 1,
                )
                return response

            except ProviderError as e:
                # Установить provider_id из выбранного провайдера если не установлен
                if not e.provider_id:
                    e.provider_id = provider.name
                self._errors.append(e)
                self._strategy.on_failure(provider.name, e)

                if not e.retryable or e.error_type not in self._config.retry_on:
                    # Non-retryable ошибка — propagate
                    logger.error(
                        "non-retryable error, propagating",
                        error_type=e.error_type.value,
                    )
                    raise

                logger.warning(
                    "retryable error, trying next provider",
                    error_type=e.error_type.value,
                    attempt=attempt + 1,
                )

        # Все попытки exhausted
        raise AllProvidersFailed(
            errors=self._errors,
            message=f"All {len(self._errors)} providers failed after {self._config.max_attempts} attempts",
        )

    async def execute_streaming(
        self,
        providers: list[LLMProvider],
        request: CompletionRequest,
        context: FallbackContext | None = None,
    ) -> AsyncGenerator[CompletionResponse, None]:
        """Выполнить streaming completion через fallback цепочку.

        В MVP streaming fallback не поддерживается — используем первый провайдер.
        В future можно реализовать buffering и переключение между провайдерами.

        Args:
            providers: Список провайдеров
            request: Запрос к LLM
            context: Контекст fallback

        Yields:
            Streaming ответы
        """
        # В MVP streaming fallback не поддерживается
        if not self._config.enabled:
            async for chunk in providers[0].stream_completion(request):
                yield chunk
            return

        # Fallback для streaming — использовать первый провайдер
        # TODO: реализовать buffering и переключение
        logger.warning("streaming fallback not supported, using first provider")
        async for chunk in providers[0].stream_completion(request):
            yield chunk

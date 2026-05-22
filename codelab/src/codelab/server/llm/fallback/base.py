"""Базовые классы для fallback стратегии."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from codelab.server.llm.base import LLMProvider
from codelab.server.llm.errors import ProviderError


@dataclass
class FallbackContext:
    """Контекст для fallback операции.

    Атрибуты:
        request_data: Данные запроса (модель, сообщения, инструменты)
        session_id: ID сессии (опционально)
        attempt: Номер текущей попытки
        max_attempts: Максимальное количество попыток
        metadata: Дополнительные метаданные
    """

    request_data: dict[str, Any] = field(default_factory=dict)
    session_id: str | None = None
    attempt: int = 0
    max_attempts: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)


class FallbackStrategy(ABC):
    """Абстрактная стратегия fallback.

    Определяет интерфейс для выбора провайдера при ошибках.
    Реализации: SequentialFallback, CostFallback, LatencyFallback, SmartFallback.
    """

    @abstractmethod
    async def select_provider(
        self,
        candidates: list[LLMProvider],
        request: dict[str, Any],
        context: FallbackContext,
    ) -> LLMProvider:
        """Выбрать провайдер из списка кандидатов.

        Args:
            candidates: Список доступных провайдеров
            request: Данные запроса
            context: Контекст fallback операции

        Returns:
            Выбранный провайдер

        Raises:
            ProviderError: Если не удалось выбрать провайдер
        """
        ...

    @abstractmethod
    def on_success(self, provider_id: str) -> None:
        """Обработать успешный запрос.

        Args:
            provider_id: ID провайдера, который успешно обработал запрос
        """
        ...

    @abstractmethod
    def on_failure(self, provider_id: str, error: ProviderError) -> None:
        """Обработать失敗ный запрос.

        Args:
            provider_id: ID провайдера, который упал
            error: Ошибка, которая произошла
        """
        ...

"""Базовый интерфейс для провайдеров LLM.

Определяет абстрактный класс LLMProvider и связанные типы данных
для мульти-провайдер архитектуры. Все провайдеры должны наследоваться
от LLMProvider и реализовать его абстрактные методы.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from codelab.server.llm.models import (
    CompletionRequest,
    CompletionResponse,
    LLMMessage,
    LLMToolCall,
    ModelInfo,
    StopReason,
)


@dataclass
class LLMCapabilities:
    """Возможности LLM провайдера.

    Атрибуты:
        supports_tools: Поддерживает ли вызов инструментов
        supports_streaming: Поддерживает ли streaming completion
        supports_function_calling: Поддерживает ли function calling
        supports_vision: Поддерживает ли изображения
        supports_system_prompt: Поддерживает ли system prompt
        max_context_window: Максимальный размер контекста (токены)
        max_output_tokens: Максимальное количество выходных токенов
    """

    supports_tools: bool = True
    supports_streaming: bool = True
    supports_function_calling: bool = True
    supports_vision: bool = False
    supports_system_prompt: bool = True
    max_context_window: int | None = None
    max_output_tokens: int | None = None


@dataclass
class LLMConfig:
    """Конфигурация для инициализации LLM провайдера.

    Атрибуты:
        api_key: API ключ провайдера
        model: Идентификатор модели
        base_url: Base URL API (опционально, для кастомных endpoint)
        temperature: Температура генерации (0.0-2.0)
        max_tokens: Максимальное количество токенов
        extra: Дополнительные параметры провайдера
    """

    api_key: str | None = None
    model: str = "gpt-4o"
    base_url: str | None = None
    temperature: float = 0.7
    max_tokens: int = 8192
    extra: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """Интерфейс для взаимодействия с LLM API.

    Провайдер инкапсулирует всю специфику работы с конкретной LLM,
    включая форматирование сообщений, обработку tool calls, retry-логику.

    Каждый провайдер должен реализовать:
    - initialize() — инициализация с конфигурацией
    - create_completion() — получение завершения
    - stream_completion() — потоковое получение завершения
    - name property — имя провайдера
    - capabilities property — возможности провайдера
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Имя провайдера (например, 'openai', 'anthropic')."""
        ...

    @property
    @abstractmethod
    def capabilities(self) -> LLMCapabilities:
        """Возможности данного провайдера."""
        ...

    @abstractmethod
    async def initialize(self, config: LLMConfig) -> None:
        """Инициализация провайдера с конфигурацией.

        Args:
            config: Конфигурация провайдера
        """
        ...

    @abstractmethod
    async def create_completion(
        self,
        request: CompletionRequest,
    ) -> CompletionResponse:
        """Получить завершение от LLM.

        Args:
            request: Запрос к провайдеру

        Returns:
            CompletionResponse с ответом модели
        """
        ...

    @abstractmethod
    def stream_completion(
        self,
        request: CompletionRequest,
    ) -> AsyncGenerator[CompletionResponse, None]:
        """Потоковое получение ответа от LLM.

        Args:
            request: Запрос к провайдеру

        Yields:
            CompletionResponse с промежуточными результатами
        """
        ...

    async def get_available_models(self) -> list[ModelInfo]:
        """Получить список доступных моделей.

        По умолчанию возвращает пустой список.
        Провайдеры могут переопределить для динамического discovery.

        Returns:
            Список доступных моделей
        """
        return []


# Алиас для обратной совместимости (LLMResponse → CompletionResponse)
LLMResponse = CompletionResponse

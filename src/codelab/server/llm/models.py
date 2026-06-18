"""Модели данных для мульти-провайдер LLM архитектуры.

Определяет единые типы данных для всех LLM провайдеров:
- CompletionRequest/Response — запрос и ответ провайдера
- LLMMessage/LLMToolCall — сообщения и вызовы инструментов
- ModelInfo/ProviderInfo — метаданные моделей и провайдеров
- StopReason — причины завершения генерации
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class StopReason(StrEnum):
    """Причины завершения генерации LLM."""

    END_TURN = "end_turn"  # Модель завершила ответ
    TOOL_USE = "tool_use"  # Модель хочет вызвать инструмент
    MAX_TOKENS = "max_tokens"  # Достигнут лимит токенов
    STOP_SEQUENCE = "stop_sequence"  # Встречена stop-последовательность
    ERROR = "error"  # Ошибка при генерации
    CANCELLED = "cancelled"  # Запрос отменён пользователем
    STREAMING = "streaming"  # Промежуточный chunk (только для streaming)
    REFUSAL = "refusal"  # Модель отказалась отвечать


@dataclass
class LLMToolCall:
    """Вызов инструмента из LLM.

    Атрибуты:
        id: Уникальный идентификатор вызова
        name: Имя инструмента
        arguments: Аргументы вызова
    """

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMMessage:
    """Сообщение для LLM.

    Поддерживает формат OpenAI и Anthropic:
    - role: "system", "user", "assistant", "tool"
    - content: текстовое содержимое
    - tool_calls: список вызовов инструментов (для assistant)
    - tool_call_id: ID вызова инструмента (для tool)
    - name: имя инструмента (для tool)
    """

    role: str  # "system", "user", "assistant", "tool"
    content: str | None = None
    tool_calls: list[LLMToolCall] | None = None  # Для assistant messages
    tool_call_id: str | None = None  # Для tool messages
    name: str | None = None  # Для tool messages


@dataclass
class CompletionRequest:
    """Запрос к LLM провайдеру.

    Атрибуты:
        model: Идентификатор модели ("provider/model" или просто "model")
        messages: История сообщений
        tools: Список инструментов в формате провайдера
        temperature: Температура генерации (0.0-2.0)
        max_tokens: Максимальное количество токенов
        stop: Stop-последовательности
        stream: Флаг streaming режима
        extra: Дополнительные параметры провайдера
    """

    model: str
    messages: list[LLMMessage]
    tools: list[dict[str, Any]] | None = None
    temperature: float = 0.7
    max_tokens: int = 8192
    stop: list[str] | None = None
    stream: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompletionResponse:
    """Ответ от LLM провайдера.

    Атрибуты:
        text: Текстовый ответ модели
        tool_calls: Список вызовов инструментов
        stop_reason: Причина завершения
        model: Имя использованной модели
        usage: Информация об использовании токенов
        extra: Дополнительные данные провайдера
    """

    text: str
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    stop_reason: StopReason = StopReason.END_TURN
    model: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelInfo:
    """Метаданные модели LLM.

    Атрибуты:
        id: Идентификатор модели (например, "gpt-4o")
        provider_id: ID провайдера (например, "openai")
        name: Отображаемое имя
        description: Описание модели
        context_window: Размер контекстного окна в токенах
        max_output_tokens: Максимальное количество выходных токенов
        supports_tools: Поддерживает ли модель инструменты
        supports_streaming: Поддерживает ли streaming
        cost_per_input_token: Стоимость входного токена (USD)
        cost_per_output_token: Стоимость выходного токена (USD)
    """

    id: str
    provider_id: str
    name: str | None = None
    description: str | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    supports_tools: bool = True
    supports_streaming: bool = True
    cost_per_input_token: float | None = None
    cost_per_output_token: float | None = None

    @property
    def full_id(self) -> str:
        """Полный идентификатор в формате "provider/model"."""
        return f"{self.provider_id}/{self.id}"


@dataclass
class ProviderInfo:
    """Метаданные провайдера LLM.

    Атрибуты:
        id: Идентификатор провайдера (например, "openai")
        name: Отображаемое имя
        description: Описание провайдера
        base_url: Base URL API
        models: Список доступных моделей
    """

    id: str
    name: str
    description: str | None = None
    base_url: str | None = None
    models: list[ModelInfo] = field(default_factory=list)

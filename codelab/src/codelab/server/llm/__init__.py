"""LLM провайдеры и интерфейсы для работы с языковыми моделями.

Мульти-провайдер архитектура с поддержкой:
- OpenAI, Anthropic, OpenRouter, Zen, Go, Ollama, LMStudio
- Registry для динамической регистрации провайдеров
- Fallback цепочки при ошибках
- Model discovery и telemetry (extension points)
"""

from codelab.server.llm.base import (
    LLMCapabilities,
    LLMConfig,
    LLMMessage,
    LLMProvider,
    LLMResponse,  # Алиас для CompletionResponse
    LLMToolCall,
)
from codelab.server.llm.errors import (
    AllProvidersFailed,
    ModelNotFoundError,
    ProviderError,
    ProviderErrorType,
    ProviderNotFoundError,
)
from codelab.server.llm.models import (
    CompletionRequest,
    CompletionResponse,
    ModelInfo,
    ProviderInfo,
    StopReason,
)
from codelab.server.llm.mock_provider import MockLLMProvider
from codelab.server.llm.openai_provider import OpenAIProvider

__all__ = [
    # Базовые классы
    "LLMProvider",
    "LLMConfig",
    "LLMCapabilities",
    # Модели сообщений
    "LLMMessage",
    "LLMToolCall",
    "LLMResponse",  # Алиас для CompletionResponse
    # Новые модели
    "CompletionRequest",
    "CompletionResponse",
    "ModelInfo",
    "ProviderInfo",
    "StopReason",
    # Исключения
    "ProviderError",
    "ProviderErrorType",
    "ProviderNotFoundError",
    "ModelNotFoundError",
    "AllProvidersFailed",
    # Провайдеры
    "OpenAIProvider",
    "MockLLMProvider",
]

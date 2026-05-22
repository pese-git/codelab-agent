"""LLM провайдеры и интерфейсы для работы с языковыми моделями.

Мульти-провайдер архитектура с поддержкой:
- OpenAI, Anthropic, OpenRouter, Zen, Go, Ollama, LMStudio
- Registry для динамической регистрации провайдеров
- Fallback цепочки при ошибках
- Model discovery и telemetry (extension points)
- ProviderEventBus для событий жизненного цикла
"""

# Базовые классы и модели
from codelab.server.llm.base import (
    LLMCapabilities,
    LLMConfig,
    LLMProvider,
    LLMResponse,  # Алиас для CompletionResponse
)
from codelab.server.llm.models import (
    LLMMessage,
    LLMToolCall,
)

# Discovery система
from codelab.server.llm.discovery import (
    DiscoveryConfig,
    ModelDiscovery,
    StaticDiscovery,
)

# Исключения
from codelab.server.llm.errors import (
    AllProvidersFailed,
    ModelNotFoundError,
    ProviderError,
    ProviderErrorType,
    ProviderNotFoundError,
)

# Event Bus
from codelab.server.llm.events import (
    FallbackTriggered,
    ModelsUpdated,
    ProviderEvent,
    ProviderEventBus,
    ProviderFailed,
    ProviderInitialized,
    event_bus,
)

# Fallback система
from codelab.server.llm.fallback import (
    CircuitBreaker,
    FallbackConfig,
    FallbackContext,
    FallbackOrchestrator,
    FallbackStrategy,
    FallbackStrategyFactory,
    SequentialFallback,
)
from codelab.server.llm.mock_provider import MockLLMProvider

# Модели данных
from codelab.server.llm.models import (
    CompletionRequest,
    CompletionResponse,
    ModelInfo,
    ProviderInfo,
    StopReason,
)

# Провайдеры
from codelab.server.llm.providers import (
    OpenAICompatibleProvider,
    OpenAIProvider,
)
from codelab.server.llm.providers.anthropic import AnthropicProvider
from codelab.server.llm.providers.go import GoProvider
from codelab.server.llm.providers.lmstudio import LMStudioProvider
from codelab.server.llm.providers.ollama import OllamaProvider
from codelab.server.llm.providers.openrouter import OpenRouterProvider
from codelab.server.llm.providers.zen import ZenProvider

# Registry и Resolver
from codelab.server.llm.registry import LLMProviderRegistry
from codelab.server.llm.resolver import ModelRef, ModelResolver

# Telemetry система
from codelab.server.llm.telemetry import (
    NoOpTelemetry,
    TelemetrySink,
)

__all__ = [
    # Базовые классы
    "LLMProvider",
    "LLMConfig",
    "LLMCapabilities",
    "LLMMessage",
    "LLMToolCall",
    "LLMResponse",  # Алиас
    # Модели
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
    # Registry и Resolver
    "LLMProviderRegistry",
    "ModelRef",
    "ModelResolver",
    # Fallback
    "FallbackStrategy",
    "FallbackContext",
    "SequentialFallback",
    "CircuitBreaker",
    "FallbackConfig",
    "FallbackStrategyFactory",
    "FallbackOrchestrator",
    # Discovery
    "ModelDiscovery",
    "StaticDiscovery",
    "DiscoveryConfig",
    # Telemetry
    "TelemetrySink",
    "NoOpTelemetry",
    # Events
    "ProviderEvent",
    "ProviderEventBus",
    "ProviderInitialized",
    "ProviderFailed",
    "FallbackTriggered",
    "ModelsUpdated",
    "event_bus",
    # Провайдеры
    "OpenAICompatibleProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "OpenRouterProvider",
    "ZenProvider",
    "GoProvider",
    "OllamaProvider",
    "LMStudioProvider",
    "MockLLMProvider",
]

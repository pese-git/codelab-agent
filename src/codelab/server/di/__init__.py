"""DI контейнер для серверной части ACP (Composition Root).

Архитектура скоупов:
- APP: синглтоны на всё время жизни сервера (LLM, ToolRegistry, менеджеры, стадии пайплайна)
- REQUEST: на одно WebSocket соединение (ClientRPCService, ACPProtocol)

Пример использования:
    container = make_container(config, storage)
    async with container() as request_scope:
        protocol = await request_scope.get(ACPProtocol)

Провайдеры разнесены по доменам в подмодулях (observability/agent/llm/services/
pipeline/request); этот модуль — единственная точка сборки контейнера.
"""

from __future__ import annotations

from dishka import AsyncContainer, make_async_container

from ..config import AppConfig
from ..storage import SessionRepository, SessionStorage
from .agent import EventBusProvider, MultiAgentProvider
from .llm import LLMProvider_, RegistryProvider
from .observability import (
    ObservabilityDebug,
    ObservabilityFlushManager,
    ObservabilityFlushProvider,
    ObservabilityProvider,
)
from .pipeline import ConfigSpecProvider, PipelineProvider, PromptOrchestratorProvider
from .request import RequestProvider, RuntimeRegistryProvider
from .services import (
    ManagersProvider,
    SlashCommandsProvider,
    StorageProvider,
    ToolsProvider,
)

__all__ = [
    "ConfigSpecProvider",
    "EventBusProvider",
    "LLMProvider_",
    "ManagersProvider",
    "MultiAgentProvider",
    "ObservabilityDebug",
    "ObservabilityFlushManager",
    "ObservabilityFlushProvider",
    "ObservabilityProvider",
    "PipelineProvider",
    "PromptOrchestratorProvider",
    "RegistryProvider",
    "RequestProvider",
    "RuntimeRegistryProvider",
    "SlashCommandsProvider",
    "StorageProvider",
    "ToolsProvider",
    "make_container",
]


def make_container(
    config: AppConfig,
    storage: SessionStorage,
    *,
    require_auth: bool = False,
    auth_api_key: str | None = None,
    trace_messages: bool = False,
    observability_debug: bool = False,
) -> AsyncContainer:
    """Создаёт DI контейнер со всеми провайдерами.

    Args:
        config: Глобальная конфигурация приложения.
        storage: Хранилище сессий.
        require_auth: Требовать аутентификацию.
        auth_api_key: API ключ для аутентификации.
        trace_messages: Включить детальное логирование всех JSON-RPC сообщений.
        observability_debug: Включить debug mode для observability (полные payload'ы).

    Returns:
        AsyncContainer для получения зависимостей.
    """
    container = make_async_container(
        ObservabilityProvider(),
        ObservabilityFlushProvider(),
        EventBusProvider(),
        MultiAgentProvider(),
        ManagersProvider(),
        SlashCommandsProvider(),
        StorageProvider(),
        RegistryProvider(),
        LLMProvider_(),
        ToolsProvider(),
        RuntimeRegistryProvider(),
        PipelineProvider(),
        PromptOrchestratorProvider(),
        ConfigSpecProvider(),
        RequestProvider(),
        context={
            AppConfig: config,
            SessionStorage: storage,
            # Доменный порт над ТЕМ ЖЕ backend (write-фаза D4-d1, ADR-006).
            # Параллельная выдача обоих типов безопасна: резидентного кэша нет,
            # транзакции не делят объект сессии в памяти — только диск. Прикладные
            # пути переезжают на репозиторий по одному; после переезда всех
            # `SessionStorage` уходит из context и остаётся только под портом.
            SessionRepository: SessionRepository(backend=storage),
            bool: require_auth,
            str | None: auth_api_key,
            "trace_messages": trace_messages,
            ObservabilityDebug: ObservabilityDebug(observability_debug),
        },
    )
    return container

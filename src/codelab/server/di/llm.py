"""Провайдеры LLM (APP scope).

LLM-провайдер по умолчанию, реестр провайдеров с автоинициализацией из TOML,
builder опций конфигурации и резолвер моделей.
"""

from __future__ import annotations

import os
from typing import Annotated

import structlog
from dishka import Provider, Scope, from_context, provide

from ..config import AppConfig
from ..llm import LLMProvider, MockLLMProvider
from ..llm.base import LLMConfig, LLMTimeoutConfig
from ..llm.errors import ProviderNotFoundError
from ..llm.registry import LLMProviderRegistry
from ..llm.resolver import ModelResolver
from ..llm.scripted_mock import ScriptedMockLLMProvider
from ..protocol.handlers.config_option_builder import ConfigOptionBuilder

logger = structlog.get_logger()


def _make_mock_provider() -> LLMProvider:
    """Создать mock-провайдер.

    Если задан CODELAB_MOCK_SCENARIO (путь к JSON-сценарию), возвращает
    сценарный ScriptedMockLLMProvider (конечный автомат для e2e-flow),
    иначе — обычный MockLLMProvider с дефолтным ответом.
    """
    scenario_path = os.getenv("CODELAB_MOCK_SCENARIO")
    if scenario_path:
        logger.info("loading scripted mock scenario", path=scenario_path)
        return ScriptedMockLLMProvider.from_file(scenario_path)
    return MockLLMProvider()


class LLMProvider_(Provider):
    """Провайдер LLM провайдеров (APP scope)."""

    @provide(scope=Scope.APP)
    async def get_llm_provider(
        self,
        config: Annotated[AppConfig, from_context(provides=AppConfig)],
        registry: LLMProviderRegistry,
    ) -> LLMProvider:
        """Создаёт LLM провайдера через Registry.

        Registry автоматически инициализирует провайдер через default_config,
        установленный в RegistryProvider.get_llm_registry().
        """
        provider_id = config.llm.provider

        try:
            return await registry.get_provider(provider_id)
        except ProviderNotFoundError:
            # Fallback на mock если провайдер не зарегистрирован
            provider = MockLLMProvider()
            await provider.initialize(
                LLMConfig(
                    model=config.llm.model,
                    temperature=config.llm.temperature,
                    max_tokens=config.llm.max_tokens,
                    timeout=LLMTimeoutConfig(
                        connect=config.llm.timeout.connect,
                        read=config.llm.timeout.read,
                        write=config.llm.timeout.write,
                        pool=config.llm.timeout.pool,
                    ),
                )
            )
            return provider


class RegistryProvider(Provider):
    """Провайдер LLM Registry и ConfigOptionBuilder (APP scope)."""

    @provide(scope=Scope.APP)
    def get_llm_registry(
        self,
        config: Annotated[AppConfig, from_context(provides=AppConfig)],
    ) -> LLMProviderRegistry:
        """Создаёт реестр провайдеров с ProviderInfo из AppConfig."""
        registry = LLMProviderRegistry()

        # Устанавливаем default config для автоинициализации провайдеров
        # Все провайдеры, получаемые через get_provider(), будут автоматически
        # инициализированы этой конфигурацией
        default_llm_config = LLMConfig(
            api_key=config.llm.api_key,
            model=config.llm.model,
            base_url=config.llm.base_url,
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens,
            timeout=LLMTimeoutConfig(
                connect=config.llm.timeout.connect,
                read=config.llm.timeout.read,
                write=config.llm.timeout.write,
                pool=config.llm.timeout.pool,
            ),
        )
        registry.set_default_config(default_llm_config)

        # Регистрируем провайдеры из AppConfig (загружено из TOML при load())
        for provider_id, provider_cfg in config.llm.providers.items():
            provider_info = provider_cfg.to_provider_info(provider_id)
            factory = self._get_provider_factory(provider_id)
            registry.register(provider_id, factory, info=provider_info)
            logger.debug(
                "provider registered from config",
                provider_id=provider_id,
                models_count=len(provider_cfg.models),
            )

        # Mock провайдер без TOML config
        if "mock" not in registry.get_registered_providers():
            registry.register("mock", _make_mock_provider)

        logger.info(
            "llm registry created",
            providers_count=len(registry.get_registered_providers()),
            models_count=len(registry.list_all_models()),
        )

        # Честный контракт: секция [llm.fallback] парсится в config, но пакет
        # server/llm/fallback (оркестратор/стратегии/circuit breaker) ещё не
        # подключён к исполнению — это задел под будущий multi-provider gateway.
        # Пока предупреждаем, чтобы enabled=true не выглядел рабочим (см. tech-debt P2).
        if config.llm.fallback.enabled:
            logger.warning(
                "llm fallback configured but not active",
                hint=(
                    "секция [llm.fallback] пока экспериментальная и не влияет на "
                    "выбор провайдера; переключение при сбое не выполняется"
                ),
                strategy=config.llm.fallback.strategy,
            )

        return registry

    @staticmethod
    def _get_provider_factory(provider_id: str):
        """Возвращает factory-функцию для провайдера."""
        from codelab.server.llm.providers.anthropic import AnthropicProvider
        from codelab.server.llm.providers.go import GoProvider
        from codelab.server.llm.providers.lmstudio import LMStudioProvider
        from codelab.server.llm.providers.ollama import OllamaProvider
        from codelab.server.llm.providers.openai import OpenAIProvider
        from codelab.server.llm.providers.openrouter import OpenRouterProvider
        from codelab.server.llm.providers.zen import ZenProvider

        factories = {
            "openai": OpenAIProvider,
            "openrouter": OpenRouterProvider,
            "anthropic": AnthropicProvider,
            "zen": ZenProvider,
            "go": GoProvider,
            "ollama": OllamaProvider,
            "lmstudio": LMStudioProvider,
        }
        return factories.get(provider_id, _make_mock_provider)

    @provide(scope=Scope.APP)
    def get_config_option_builder(
        self,
        registry: LLMProviderRegistry,
    ) -> ConfigOptionBuilder:
        """Создаёт билдер config options."""
        return ConfigOptionBuilder(registry)

    @provide(scope=Scope.APP)
    def get_model_resolver(
        self,
        config: Annotated[AppConfig, from_context(provides=AppConfig)],
        registry: LLMProviderRegistry,
    ) -> ModelResolver:
        """Создаёт ModelResolver для dynamic model selection.

        ModelResolver резолвит ссылки на модели в формате "provider/model"
        в конкретные LLMProvider экземпляры через Registry.
        Поддерживает кэширование на уровне сессии и инвалидацию
        при смене модели через session/set_config_option.
        """
        return ModelResolver(
            registry=registry,
            default_provider=config.llm.provider,
            provider_configs=config.llm.providers,
        )

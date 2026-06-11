"""Resolver для моделей LLM.

ModelRef — представление ссылки на модель в формате "provider/model".
ModelResolver — резолвит ModelRef в конкретный LLMProvider.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from codelab.server.llm.base import LLMConfig, LLMProvider, LLMTimeoutConfig
from codelab.server.llm.errors import ProviderNotFoundError
from codelab.server.llm.registry import LLMProviderRegistry

if TYPE_CHECKING:
    from codelab.server.toml_config.pydantic_config import ProviderConfig

logger = structlog.get_logger()


@dataclass
class ModelRef:
    """Ссылка на модель в формате "provider/model".

    Атрибуты:
        provider_id: Идентификатор провайдера
        model_id: Идентификатор модели

    Пример:
        ref = ModelRef.parse("openai/gpt-4o")
        assert ref.provider_id == "openai"
        assert ref.model_id == "gpt-4o"
    """

    provider_id: str
    model_id: str

    @classmethod
    def parse(cls, value: str) -> ModelRef:
        """Распарсить строку "provider/model" в ModelRef.

        Args:
            value: Строка в формате "provider/model" или просто "model"

        Returns:
            ModelRef с provider_id и model_id

        Raises:
            ValueError: Если формат некорректен
        """
        if "/" in value:
            parts = value.split("/", 1)
            return cls(provider_id=parts[0], model_id=parts[1])
        else:
            # Если нет "/", считаем что это только model_id
            # provider_id будет определён позже через default provider
            return cls(provider_id="", model_id=value)

    def __str__(self) -> str:
        """Вернуть строковое представление "provider/model"."""
        if self.provider_id:
            return f"{self.provider_id}/{self.model_id}"
        return self.model_id

    def is_fully_qualified(self) -> bool:
        """Проверить, что ссылка содержит provider_id."""
        return bool(self.provider_id)


class ModelResolver:
    """Резолвер моделей.

    Резолвит ModelRef в конкретный LLMProvider через Registry.
    Поддерживает default provider для ссылок без provider_id.
    Кэширует провайдеры на уровне сессии для производительности.

    Пример использования:
        registry = LLMProviderRegistry()
        registry.register("openai", lambda: OpenAIProvider())

        resolver = ModelResolver(registry, default_provider="openai")
        provider, model_id = await resolver.resolve_for_session("sess_1", "openai/gpt-4o")
        # provider — экземпляр OpenAIProvider, model_id = "gpt-4o"
    """

    def __init__(
        self,
        registry: LLMProviderRegistry,
        default_provider: str = "openai",
        provider_configs: dict[str, ProviderConfig] | None = None,
    ) -> None:
        """Инициализация резолвера.

        Args:
            registry: Реестр провайдеров
            default_provider: Провайдер по умолчанию для ссылок без provider_id
            provider_configs: Конфигурации провайдеров (API keys, base_url)
                из AppConfig.llm.providers. Используются для инициализации
                провайдеров при динамическом переключении моделей.
        """
        self._registry = registry
        self._default_provider = default_provider
        # Кэш провайдеров per-session: session_id -> (provider, model_id)
        # Инвалидируется при смене модели через session/set_config_option
        self._session_cache: dict[str, tuple[LLMProvider, str]] = {}
        # Конфигурации провайдеров из TOML/env/CLI
        self._provider_configs: dict[str, ProviderConfig] = provider_configs or {}

    @property
    def default_provider(self) -> str:
        """Провайдер по умолчанию."""
        return self._default_provider

    @default_provider.setter
    def default_provider(self, value: str) -> None:
        """Установить провайдер по умолчанию."""
        self._default_provider = value

    def invalidate_session(self, session_id: str) -> None:
        """Очистить кэш провайдера для сессии.

        Вызывается при смене модели через session/set_config_option,
        чтобы следующий turn использовал новый провайдер.

        Args:
            session_id: ID сессии для инвалидации
        """
        evicted = self._session_cache.pop(session_id, None)
        if evicted is not None:
            logger.debug(
                "session provider cache invalidated",
                session_id=session_id,
                previous_provider=evicted[0].name,
            )

    async def resolve_for_session(
        self,
        session_id: str,
        model_ref: str | ModelRef,
        config: LLMConfig | None = None,
    ) -> tuple[LLMProvider, str]:
        """Резолвить провайдер для сессии с кэшированием.

        При первом вызове для сессии создаёт провайдер и кэширует его.
        Повторные вызовы возвращают кэшированный экземпляр.

        Args:
            session_id: ID сессии для кэширования
            model_ref: Строка "provider/model" или ModelRef
            config: Конфигурация для инициализации провайдера

        Returns:
            Кортеж (LLMProvider, model_id)
        """
        # Проверить кэш
        if session_id in self._session_cache:
            cached_provider, cached_model_id = self._session_cache[session_id]
            # Если model_ref совпадает — вернуть кэш
            if isinstance(model_ref, str):
                full_id = f"{cached_provider.name}/{cached_model_id}"
                if model_ref in (cached_model_id, full_id):
                    logger.debug(
                        "using cached provider for session",
                        session_id=session_id,
                        model=model_ref,
                    )
                    return cached_provider, cached_model_id
            elif isinstance(model_ref, ModelRef):
                matches = (
                    model_ref.provider_id == cached_provider.name
                    and model_ref.model_id == cached_model_id
                )
                if matches:
                    return cached_provider, cached_model_id

        # Резолвить новый провайдер
        provider, model_id = await self.resolve(model_ref, config)
        self._session_cache[session_id] = (provider, model_id)
        logger.info(
            "provider resolved for session",
            session_id=session_id,
            provider=provider.name,
            model=model_id,
        )
        return provider, model_id

    async def resolve(
        self,
        model_ref: str | ModelRef,
        config: LLMConfig | None = None,
    ) -> tuple[LLMProvider, str]:
        """Резолвить ссылку на модель в провайдер и model_id.

        Args:
            model_ref: Строка "provider/model" или ModelRef
            config: Конфигурация для инициализации провайдера

        Returns:
            Кортеж (LLMProvider, model_id)

        Raises:
            ProviderNotFoundError: Если провайдер не найден
            ModelNotFoundError: Если модель не найдена у провайдера
        """
        # Распарсить строку если нужно
        if isinstance(model_ref, str):
            ref = ModelRef.parse(model_ref)
        else:
            ref = model_ref

        # Определить provider_id
        provider_id = ref.provider_id or self._default_provider

        # Проверить что провайдер зарегистрирован
        if not self._registry.is_registered(provider_id):
            raise ProviderNotFoundError(provider_id)

        # Построить конфигурацию для инициализации
        if config is not None:
            # Когда config передан явно — использовать его, но обновить model
            provider_config = LLMConfig(
                api_key=config.api_key,
                model=ref.model_id,
                base_url=config.base_url,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                timeout=config.timeout,
                extra=config.extra,
            )
        else:
            # Когда config не передан — собрать из provider_configs (TOML/env/CLI)
            provider_config = self._build_config_from_store(provider_id, ref.model_id)

        # Всегда инициализировать провайдер (create_provider вызывает initialize)
        provider = await self._registry.create_provider(provider_id, provider_config)

        logger.debug(
            "model resolved",
            provider_id=provider_id,
            model_id=ref.model_id,
        )

        return provider, ref.model_id

    def _build_config_from_store(
        self,
        provider_id: str,
        model_id: str,
    ) -> LLMConfig:
        """Построить LLMConfig из сохранённых provider_configs.

        Используется когда config не передан явно — берёт API key и base_url
        из конфигурации провайдера (загруженной из TOML/env/CLI).

        Args:
            provider_id: Идентификатор провайдера
            model_id: Идентификатор модели

        Returns:
            LLMConfig с API key и base_url из конфигурации
        """
        pc = self._provider_configs.get(provider_id)
        if pc is not None:
            return LLMConfig(
                api_key=pc.api_key,
                model=model_id,
                base_url=pc.base_url,
                timeout=LLMTimeoutConfig(
                    connect=pc.timeout.connect,
                    read=pc.timeout.read,
                    write=pc.timeout.write,
                    pool=pc.timeout.pool,
                ),
            )
        # Fallback: только model_id, без API key
        return LLMConfig(model=model_id)

    async def resolve_from_session(
        self,
        session_provider: str,
        session_model: str,
        config: LLMConfig | None = None,
    ) -> tuple[LLMProvider, str]:
        """Резолвить модель из session config.

        Args:
            session_provider: Провайдер из session config
            session_model: Модель из session config
            config: Глобальная конфигурация для API ключей

        Returns:
            Кортеж (LLMProvider, model_id)
        """
        ref = ModelRef(provider_id=session_provider, model_id=session_model)
        return await self.resolve(ref, config)

"""Resolver для моделей LLM.

ModelRef — представление ссылки на модель в формате "provider/model".
ModelResolver — резолвит ModelRef в конкретный LLMProvider.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from codelab.server.llm.base import LLMConfig, LLMProvider
from codelab.server.llm.errors import ModelNotFoundError, ProviderNotFoundError
from codelab.server.llm.registry import LLMProviderRegistry

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

    Пример использования:
        registry = LLMProviderRegistry()
        registry.register("openai", lambda: OpenAIProvider())

        resolver = ModelResolver(registry, default_provider="openai")
        provider, model_id = await resolver.resolve("openai/gpt-4o")
        # provider — экземпляр OpenAIProvider, model_id = "gpt-4o"
    """

    def __init__(
        self,
        registry: LLMProviderRegistry,
        default_provider: str = "openai",
    ) -> None:
        """Инициализация резолвера.

        Args:
            registry: Реестр провайдеров
            default_provider: Провайдер по умолчанию для ссылок без provider_id
        """
        self._registry = registry
        self._default_provider = default_provider

    @property
    def default_provider(self) -> str:
        """Провайдер по умолчанию."""
        return self._default_provider

    @default_provider.setter
    def default_provider(self, value: str) -> None:
        """Установить провайдер по умолчанию."""
        self._default_provider = value

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

        # Создать и инициализировать провайдер
        if config:
            # Обновить model в config
            provider_config = LLMConfig(
                api_key=config.api_key,
                model=ref.model_id,
                base_url=config.base_url,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                extra=config.extra,
            )
            provider = await self._registry.create_provider(provider_id, provider_config)
        else:
            provider = await self._registry.get_provider(provider_id)

        logger.debug(
            "model resolved",
            provider_id=provider_id,
            model_id=ref.model_id,
        )

        return provider, ref.model_id

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

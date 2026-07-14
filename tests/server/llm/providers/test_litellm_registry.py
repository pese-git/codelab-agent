"""Тест регистрации LiteLLMProvider в LLMProviderRegistry."""

from __future__ import annotations

from codelab.server.llm.base import LLMConfig
from codelab.server.llm.providers.litellm_provider import LiteLLMProvider
from codelab.server.llm.registry import LLMProviderRegistry


class TestLiteLLMProviderRegistration:
    """Проверяет, что LiteLLMProvider корректно регистрируется и инициализируется."""

    async def test_register_and_get_provider(self) -> None:
        registry = LLMProviderRegistry()
        registry.register("litellm", LiteLLMProvider)

        provider = await registry.get_provider("litellm")

        assert isinstance(provider, LiteLLMProvider)
        assert provider.name == "litellm"

    async def test_register_with_default_config_initializes(self) -> None:
        registry = LLMProviderRegistry()
        registry.set_default_config(
            LLMConfig(
                api_key="k",
                model="openai/gpt-4o",
                base_url="https://proxy.example.com",
            )
        )
        registry.register("litellm", LiteLLMProvider)

        provider = await registry.get_provider("litellm")

        assert provider._config is not None
        assert provider._config.api_key == "k"
        assert provider._config.model == "openai/gpt-4o"
        assert provider._config.base_url == "https://proxy.example.com"

    async def test_is_registered(self) -> None:
        registry = LLMProviderRegistry()
        registry.register("litellm", LiteLLMProvider)
        assert registry.is_registered("litellm")
        assert "litellm" in registry.get_registered_providers()

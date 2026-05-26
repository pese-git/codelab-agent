"""Тесты для LLMProviderRegistry."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.llm.base import LLMConfig
from codelab.server.llm.errors import ModelNotFoundError, ProviderNotFoundError
from codelab.server.llm.models import ModelInfo, ProviderInfo
from codelab.server.llm.registry import LLMProviderRegistry


@pytest.fixture
def mock_provider() -> MagicMock:
    """Создать mock провайдер."""
    provider = MagicMock()
    provider.initialize = AsyncMock()
    return provider


@pytest.fixture
def registry() -> LLMProviderRegistry:
    """Создать registry с тестовыми провайдерами."""
    reg = LLMProviderRegistry()

    # Зарегистрировать тестовые провайдеры
    mock_openai = MagicMock()
    mock_openai.initialize = AsyncMock()
    mock_openai.name = "openai"

    mock_anthropic = MagicMock()
    mock_anthropic.initialize = AsyncMock()
    mock_anthropic.name = "anthropic"

    reg.register(
        "openai",
        lambda: mock_openai,
        ProviderInfo(
            id="openai",
            name="OpenAI",
            models=[
                ModelInfo(id="gpt-4o", provider_id="openai"),
                ModelInfo(id="o3", provider_id="openai"),
            ],
        ),
    )
    reg.register(
        "anthropic",
        lambda: mock_anthropic,
        ProviderInfo(
            id="anthropic",
            name="Anthropic",
            models=[
                ModelInfo(id="claude-sonnet-4", provider_id="anthropic"),
            ],
        ),
    )

    return reg


class TestLLMProviderRegistry:
    """Тесты для LLMProviderRegistry."""

    def test_register_provider(self) -> None:
        """Проверить регистрацию провайдера."""
        reg = LLMProviderRegistry()
        mock_factory = MagicMock()
        reg.register("test", mock_factory)
        assert reg.is_registered("test")
        assert "test" in reg.get_registered_providers()

    def test_register_provider_with_info(self) -> None:
        """Проверить регистрацию провайдера с информацией."""
        reg = LLMProviderRegistry()
        info = ProviderInfo(id="test", name="Test Provider")
        reg.register("test", MagicMock(), info)
        assert reg.get_provider_info("test") == info

    def test_is_registered(self) -> None:
        """Проверить проверку регистрации."""
        reg = LLMProviderRegistry()
        reg.register("test", MagicMock())
        assert reg.is_registered("test")
        assert not reg.is_registered("unknown")

    def test_get_registered_providers(self, registry: LLMProviderRegistry) -> None:
        """Проверить получение списка провайдеров."""
        providers = registry.get_registered_providers()
        assert "openai" in providers
        assert "anthropic" in providers
        assert len(providers) == 2

    @pytest.mark.asyncio
    async def test_get_provider(
        self,
        registry: LLMProviderRegistry,
        mock_provider: MagicMock,
    ) -> None:
        """Проверить получение провайдера."""
        # Зарегистрировать mock
        registry.register("mock", lambda: mock_provider)
        provider = await registry.get_provider("mock")
        assert provider == mock_provider

    @pytest.mark.asyncio
    async def test_get_provider_cached(self, registry: LLMProviderRegistry) -> None:
        """Проверить кэширование провайдера."""
        provider1 = await registry.get_provider("openai")
        provider2 = await registry.get_provider("openai")
        assert provider1 is provider2

    @pytest.mark.asyncio
    async def test_get_provider_not_found(self, registry: LLMProviderRegistry) -> None:
        """Проверить ошибку при отсутствии провайдера."""
        with pytest.raises(ProviderNotFoundError):
            await registry.get_provider("unknown")

    @pytest.mark.asyncio
    async def test_create_provider(
        self,
        registry: LLMProviderRegistry,
        mock_provider: MagicMock,
    ) -> None:
        """Проверить создание и инициализацию провайдера.

        create_provider создаёт НОВЫЙ экземпляр каждый раз (не из кэша).
        """
        registry.register("mock", lambda: mock_provider)
        config = LLMConfig(api_key="test", model="test-model")
        provider = await registry.create_provider("mock", config)
        # Новый экземпляр создан factory-функцией
        mock_provider.initialize.assert_called_once_with(config)
        # Провайдер инициализирован
        assert provider is not None

    @pytest.mark.asyncio
    async def test_create_provider_not_found(self, registry: LLMProviderRegistry) -> None:
        """Проверить ошибку при создании несуществующего провайдера."""
        with pytest.raises(ProviderNotFoundError):
            await registry.create_provider("unknown", LLMConfig())

    def test_list_all_models(self, registry: LLMProviderRegistry) -> None:
        """Проверить получение всех моделей."""
        models = registry.list_all_models()
        assert len(models) == 3
        model_ids = {m.id for m in models}
        assert "gpt-4o" in model_ids
        assert "o3" in model_ids
        assert "claude-sonnet-4" in model_ids

    def test_get_provider_info(self, registry: LLMProviderRegistry) -> None:
        """Проверить получение информации о провайдере."""
        info = registry.get_provider_info("openai")
        assert info.id == "openai"
        assert info.name == "OpenAI"
        assert len(info.models) == 2

    def test_get_provider_info_not_found(self, registry: LLMProviderRegistry) -> None:
        """Проверить ошибку при отсутствии информации."""
        with pytest.raises(ProviderNotFoundError):
            registry.get_provider_info("unknown")

    def test_get_model_info(self, registry: LLMProviderRegistry) -> None:
        """Проверить получение информации о модели."""
        model = registry.get_model_info("openai", "gpt-4o")
        assert model.id == "gpt-4o"
        assert model.provider_id == "openai"

    def test_get_model_info_not_found(self, registry: LLMProviderRegistry) -> None:
        """Проверить ошибку при отсутствии модели."""
        with pytest.raises(ModelNotFoundError):
            registry.get_model_info("openai", "unknown-model")

    def test_get_model_info_provider_not_found(self, registry: LLMProviderRegistry) -> None:
        """Проверить ошибку при отсутствии провайдера."""
        with pytest.raises(ProviderNotFoundError):
            registry.get_model_info("unknown", "gpt-4o")

    def test_update_provider_info(self, registry: LLMProviderRegistry) -> None:
        """Проверить обновление информации о провайдере."""
        new_info = ProviderInfo(
            id="openai",
            name="OpenAI Updated",
            models=[ModelInfo(id="gpt-5", provider_id="openai")],
        )
        registry.update_provider_info("openai", new_info)
        info = registry.get_provider_info("openai")
        assert info.name == "OpenAI Updated"
        assert len(info.models) == 1
        assert info.models[0].id == "gpt-5"

    def test_clear(self, registry: LLMProviderRegistry) -> None:
        """Проверить очистку реестра."""
        registry.clear()
        assert registry.get_registered_providers() == []
        assert registry.list_all_models() == []

    def test_empty_registry(self) -> None:
        """Проверить пустой реестр."""
        reg = LLMProviderRegistry()
        assert reg.get_registered_providers() == []
        assert reg.list_all_models() == []

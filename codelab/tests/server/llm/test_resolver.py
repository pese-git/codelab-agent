"""Тесты для ModelResolver."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.llm.base import LLMConfig
from codelab.server.llm.errors import ProviderNotFoundError
from codelab.server.llm.models import ModelInfo, ProviderInfo
from codelab.server.llm.registry import LLMProviderRegistry
from codelab.server.llm.resolver import ModelRef, ModelResolver


class TestModelRef:
    """Тесты для ModelRef."""

    def test_parse_full_ref(self) -> None:
        """Проверить парсинг полного ref."""
        ref = ModelRef.parse("openai/gpt-4o")
        assert ref.provider_id == "openai"
        assert ref.model_id == "gpt-4o"

    def test_parse_model_only(self) -> None:
        """Проверить парсинг только model_id."""
        ref = ModelRef.parse("gpt-4o")
        assert ref.provider_id == ""
        assert ref.model_id == "gpt-4o"

    def test_parse_with_slash_in_model(self) -> None:
        """Проверить парсинг модели со слэшем."""
        ref = ModelRef.parse("ollama/llama3.1:70b")
        assert ref.provider_id == "ollama"
        assert ref.model_id == "llama3.1:70b"

    def test_str_full_ref(self) -> None:
        """Проверить строковое представление полного ref."""
        ref = ModelRef(provider_id="openai", model_id="gpt-4o")
        assert str(ref) == "openai/gpt-4o"

    def test_str_model_only(self) -> None:
        """Проверить строковое представление model-only ref."""
        ref = ModelRef(provider_id="", model_id="gpt-4o")
        assert str(ref) == "gpt-4o"

    def test_is_fully_qualified(self) -> None:
        """Проверить is_fully_qualified."""
        assert ModelRef(provider_id="openai", model_id="gpt-4o").is_fully_qualified() is True
        assert ModelRef(provider_id="", model_id="gpt-4o").is_fully_qualified() is False


class TestModelResolver:
    """Тесты для ModelResolver."""

    @pytest.fixture
    def registry(self) -> LLMProviderRegistry:
        """Создать registry с тестовыми провайдерами."""
        reg = LLMProviderRegistry()

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

    @pytest.fixture
    def resolver(self, registry: LLMProviderRegistry) -> ModelResolver:
        """Создать resolver."""
        return ModelResolver(registry, default_provider="openai")

    @pytest.mark.asyncio
    async def test_resolve_full_ref(
        self,
        resolver: ModelResolver,
    ) -> None:
        """Проверить разрешение полного ref."""
        provider, model_id = await resolver.resolve("openai/gpt-4o")
        assert model_id == "gpt-4o"
        assert provider.name == "openai"

    @pytest.mark.asyncio
    async def test_resolve_with_config(
        self,
        resolver: ModelResolver,
    ) -> None:
        """Проверить разрешение с конфигурацией."""
        config = LLMConfig(api_key="test-key", model="gpt-4o", temperature=0.5)
        provider, model_id = await resolver.resolve("openai/gpt-4o", config)
        assert model_id == "gpt-4o"
        # Проверить что initialize был вызван с правильным config
        provider.initialize.assert_called_once()
        call_config = provider.initialize.call_args[0][0]
        assert call_config.model == "gpt-4o"
        assert call_config.api_key == "test-key"
        assert call_config.temperature == 0.5

    @pytest.mark.asyncio
    async def test_resolve_default_provider(
        self,
        resolver: ModelResolver,
    ) -> None:
        """Проверить использование default provider."""
        # Ref без provider_id должен использовать default_provider
        provider, model_id = await resolver.resolve("gpt-4o")
        assert model_id == "gpt-4o"
        assert provider.name == "openai"

    @pytest.mark.asyncio
    async def test_resolve_model_ref_object(
        self,
        resolver: ModelResolver,
    ) -> None:
        """Проверить разрешение ModelRef объекта."""
        ref = ModelRef(provider_id="anthropic", model_id="claude-sonnet-4")
        provider, model_id = await resolver.resolve(ref)
        assert model_id == "claude-sonnet-4"
        assert provider.name == "anthropic"

    @pytest.mark.asyncio
    async def test_resolve_provider_not_found(
        self,
        resolver: ModelResolver,
    ) -> None:
        """Проверить ошибку при отсутствии провайдера."""
        with pytest.raises(ProviderNotFoundError):
            await resolver.resolve("unknown/model")

    @pytest.mark.asyncio
    async def test_default_provider_property(
        self,
        resolver: ModelResolver,
    ) -> None:
        """Проверить default_provider property."""
        assert resolver.default_provider == "openai"

    def test_default_provider_setter(
        self,
        resolver: ModelResolver,
    ) -> None:
        """Проверить default_provider setter."""
        resolver.default_provider = "anthropic"
        assert resolver.default_provider == "anthropic"

    @pytest.mark.asyncio
    async def test_resolve_from_session(
        self,
        resolver: ModelResolver,
    ) -> None:
        """Проверить разрешение из session config."""
        provider, model_id = await resolver.resolve_from_session(
            session_provider="openai",
            session_model="gpt-4o",
        )
        assert model_id == "gpt-4o"
        assert provider.name == "openai"

    @pytest.mark.asyncio
    async def test_resolve_from_session_with_config(
        self,
        resolver: ModelResolver,
    ) -> None:
        """Проверить разрешение из session config с LLMConfig."""
        config = LLMConfig(api_key="session-key")
        provider, model_id = await resolver.resolve_from_session(
            session_provider="anthropic",
            session_model="claude-sonnet-4",
            config=config,
        )
        assert model_id == "claude-sonnet-4"
        provider.initialize.assert_called_once()
        call_config = provider.initialize.call_args[0][0]
        assert call_config.api_key == "session-key"
        assert call_config.model == "claude-sonnet-4"


class TestModelResolverSessionCache:
    """Тесты для кэширования провайдеров на уровне сессии."""

    @pytest.fixture
    def registry(self) -> LLMProviderRegistry:
        """Создать registry с тестовыми провайдерами."""
        reg = LLMProviderRegistry()

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

    @pytest.fixture
    def resolver(self, registry: LLMProviderRegistry) -> ModelResolver:
        """Создать resolver."""
        return ModelResolver(registry, default_provider="openai")

    @pytest.mark.asyncio
    async def test_resolve_for_session_caches_provider(
        self,
        resolver: ModelResolver,
    ) -> None:
        """Проверить что resolve_for_session кэширует провайдер."""
        provider1, model1 = await resolver.resolve_for_session(
            "sess_1", "openai/gpt-4o"
        )
        provider2, model2 = await resolver.resolve_for_session(
            "sess_1", "openai/gpt-4o"
        )

        # Должен вернуть тот же экземпляр из кэша
        assert provider1 is provider2
        assert model1 == model2 == "gpt-4o"

    @pytest.mark.asyncio
    async def test_resolve_for_session_different_sessions(
        self,
        resolver: ModelResolver,
    ) -> None:
        """Проверить что разные сессии получают свои экземпляры."""
        provider1, _ = await resolver.resolve_for_session(
            "sess_1", "openai/gpt-4o"
        )
        provider2, _ = await resolver.resolve_for_session(
            "sess_2", "openai/gpt-4o"
        )

        # Разные сессии — разные экземпляры (первый вызов для каждой)
        # Но после кэширования должны совпадать
        provider1_again, _ = await resolver.resolve_for_session(
            "sess_1", "openai/gpt-4o"
        )
        assert provider1 is provider1_again

    @pytest.mark.asyncio
    async def test_invalidate_session_clears_cache(
        self,
        resolver: ModelResolver,
    ) -> None:
        """Проверить что invalidate_session очищает кэш."""
        provider1, _ = await resolver.resolve_for_session(
            "sess_1", "openai/gpt-4o"
        )

        # Кэш должен содержать запись
        assert "sess_1" in resolver._session_cache

        # Инвалидировать кэш
        resolver.invalidate_session("sess_1")

        # Кэш должен быть очищен
        assert "sess_1" not in resolver._session_cache

        # После инвалидации следующий вызов снова добавит в кэш
        provider2, _ = await resolver.resolve_for_session(
            "sess_1", "openai/gpt-4o"
        )
        assert "sess_1" in resolver._session_cache

    @pytest.mark.asyncio
    async def test_invalidate_nonexistent_session_noop(
        self,
        resolver: ModelResolver,
    ) -> None:
        """Проверить что invalidate для несуществующей сессии — no-op."""
        resolver.invalidate_session("nonexistent")
        # Не должно быть ошибок

    @pytest.mark.asyncio
    async def test_resolve_for_session_with_model_ref_object(
        self,
        resolver: ModelResolver,
    ) -> None:
        """Проверить resolve_for_session с ModelRef объектом."""
        ref = ModelRef(provider_id="anthropic", model_id="claude-sonnet-4")
        provider, model_id = await resolver.resolve_for_session(
            "sess_1", ref
        )
        assert model_id == "claude-sonnet-4"
        assert provider.name == "anthropic"

    @pytest.mark.asyncio
    async def test_resolve_for_session_cache_hit_with_string(
        self,
        resolver: ModelResolver,
    ) -> None:
        """Проверить что кэш работает при повторном вызове со строкой."""
        # Первый вызов — резолвит
        provider1, _ = await resolver.resolve_for_session(
            "sess_1", "openai/gpt-4o"
        )
        # Второй вызов — должен вернуть кэш
        provider2, _ = await resolver.resolve_for_session(
            "sess_1", "openai/gpt-4o"
        )
        assert provider1 is provider2

    @pytest.mark.asyncio
    async def test_resolve_for_session_cache_miss_on_different_model(
        self,
        registry: LLMProviderRegistry,
    ) -> None:
        """Проверить что смена модели приводит к новому резолвингу."""
        # Добавить вторую модель
        registry.register(
            "openai",
            lambda: MagicMock(initialize=AsyncMock(), name="openai"),
            ProviderInfo(
                id="openai",
                name="OpenAI",
                models=[
                    ModelInfo(id="gpt-4o", provider_id="openai"),
                    ModelInfo(id="gpt-4o-mini", provider_id="openai"),
                ],
            ),
        )

        resolver = ModelResolver(registry, default_provider="openai")

        provider1, model1 = await resolver.resolve_for_session(
            "sess_1", "openai/gpt-4o"
        )
        # Смена модели — должен резолвить заново
        provider2, model2 = await resolver.resolve_for_session(
            "sess_1", "openai/gpt-4o-mini"
        )

        assert model1 == "gpt-4o"
        assert model2 == "gpt-4o-mini"

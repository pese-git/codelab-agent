"""Тесты для AgentFactory."""

from unittest.mock import MagicMock

import pytest

from codelab.server.agent.config.models import AgentRole, ResolvedAgent
from codelab.server.agent.factory import AgentFactory
from codelab.server.llm.base import LLMProvider
from codelab.server.llm.registry import LLMProviderRegistry
from codelab.server.observability.tracer import Tracer
from codelab.server.tools.base import ToolRegistry


@pytest.fixture
def mock_llm_registry():
    from unittest.mock import AsyncMock
    registry = MagicMock(spec=LLMProviderRegistry)
    mock_provider = MagicMock(spec=LLMProvider)
    mock_provider.name = "openai"
    registry.get_provider = AsyncMock(return_value=mock_provider)
    registry.get_registered_providers.return_value = ["openai"]
    return registry


@pytest.fixture
def mock_tool_registry():
    return MagicMock(spec=ToolRegistry)


@pytest.fixture
def mock_tracer():
    return Tracer(debug=True)


@pytest.fixture
def factory(mock_llm_registry, mock_tool_registry, mock_tracer):
    return AgentFactory(
        llm_registry=mock_llm_registry,
        tool_registry=mock_tool_registry,
        tracer=mock_tracer,
    )


class TestCreateAdapter:
    """Тесты создания LLMAdapter."""

    @pytest.mark.asyncio
    async def test_creates_adapter_with_correct_model(
        self, factory, mock_llm_registry
    ):
        """Adapter создаётся с провайдером из model_ref."""
        agent = ResolvedAgent(
            name="coder",
            model="openai/gpt-4o",
            role=AgentRole.PRIMARY,
        )

        adapter = await factory.create_adapter(agent)

        # Проверяем что провайдер был резолвлен
        mock_llm_registry.get_provider.assert_called_with("openai")
        assert adapter._name == "coder"

    @pytest.mark.asyncio
    async def test_uses_default_model_if_empty(
        self, factory, mock_llm_registry
    ):
        """Если agent.model пустой — используется default_model."""
        agent = ResolvedAgent(
            name="tester",
            model="",  # пустая модель
            role=AgentRole.PRIMARY,
        )

        await factory.create_adapter(agent, default_model="openai/gpt-4o-mini")

        # ModelRef.parse("openai/gpt-4o-mini") → provider_id="openai"
        mock_llm_registry.get_provider.assert_called_with("openai")

    @pytest.mark.asyncio
    async def test_caches_adapter(self, factory, mock_llm_registry):
        """Adapter кэшируется — повторный вызов возвращает тот же экземпляр."""
        agent = ResolvedAgent(
            name="coder",
            model="openai/gpt-4o",
            role=AgentRole.PRIMARY,
        )

        adapter1 = await factory.create_adapter(agent)
        adapter2 = await factory.create_adapter(agent)

        assert adapter1 is adapter2
        # Провайдер резолвился только один раз
        assert mock_llm_registry.get_provider.call_count == 1

    @pytest.mark.asyncio
    async def test_different_agents_get_different_adapters(
        self, factory, mock_llm_registry
    ):
        """Разные агенты получают разные адаптеры."""
        agent1 = ResolvedAgent(
            name="coder",
            model="openai/gpt-4o",
            role=AgentRole.PRIMARY,
        )
        agent2 = ResolvedAgent(
            name="tester",
            model="openai/gpt-4o-mini",
            role=AgentRole.PRIMARY,
        )

        adapter1 = await factory.create_adapter(agent1)
        adapter2 = await factory.create_adapter(agent2)

        assert adapter1 is not adapter2
        assert adapter1._name == "coder"
        assert adapter2._name == "tester"


class TestGetAdapter:
    """Тесты получения кэшированного адаптера."""

    @pytest.mark.asyncio
    async def test_get_adapter_returns_cached(self, factory, mock_llm_registry):
        """get_adapter возвращает кэшированный адаптер."""
        agent = ResolvedAgent(
            name="coder",
            model="openai/gpt-4o",
            role=AgentRole.PRIMARY,
        )

        await factory.create_adapter(agent)
        cached = factory.get_adapter("coder")

        assert cached is not None
        assert cached._name == "coder"

    def test_get_adapter_returns_none_for_unknown(self, factory):
        """get_adapter возвращает None для неизвестного агента."""
        assert factory.get_adapter("nonexistent") is None


class TestClearCache:
    """Тесты очистки кэша."""

    @pytest.mark.asyncio
    async def test_clear_cache_removes_adapters(
        self, factory, mock_llm_registry
    ):
        """clear_cache удаляет все кэшированные адаптеры."""
        agent = ResolvedAgent(
            name="coder",
            model="openai/gpt-4o",
            role=AgentRole.PRIMARY,
        )

        await factory.create_adapter(agent)
        assert factory.get_adapter("coder") is not None

        factory.clear_cache()
        assert factory.get_adapter("coder") is None

    @pytest.mark.asyncio
    async def test_clear_cache_allows_recreation(
        self, factory, mock_llm_registry
    ):
        """После clear_cache adapter создаётся заново."""
        agent = ResolvedAgent(
            name="coder",
            model="openai/gpt-4o",
            role=AgentRole.PRIMARY,
        )

        adapter1 = await factory.create_adapter(agent)
        factory.clear_cache()
        adapter2 = await factory.create_adapter(agent)

        assert adapter1 is not adapter2


class TestProviderResolution:
    """Тесты резолвинга провайдеров."""

    @pytest.mark.asyncio
    async def test_fallback_to_first_provider(
        self, factory, mock_llm_registry
    ):
        """Если provider не найден — fallback на первый доступный."""
        from unittest.mock import AsyncMock

        from codelab.server.llm.errors import ProviderNotFoundError

        mock_provider2 = MagicMock(spec=LLMProvider)
        mock_provider2.name = "openai"

        # Первый вызов падает, fallback вызывает get_provider("openai")
        mock_llm_registry.get_provider = AsyncMock(
            side_effect=[
                ProviderNotFoundError("unknown"),
                mock_provider2,
            ]
        )

        agent = ResolvedAgent(
            name="coder",
            model="unknown/gpt-4o",
            role=AgentRole.PRIMARY,
        )

        adapter = await factory.create_adapter(agent)
        assert adapter is not None

    @pytest.mark.asyncio
    async def test_raises_when_no_providers_registered(
        self, mock_tool_registry, mock_tracer
    ):
        """Если нет зарегистрированных провайдеров — ValueError."""
        from unittest.mock import AsyncMock

        from codelab.server.llm.errors import ProviderNotFoundError

        empty_registry = MagicMock(spec=LLMProviderRegistry)
        empty_registry.get_provider = AsyncMock(
            side_effect=ProviderNotFoundError("unknown")
        )
        empty_registry.get_registered_providers.return_value = []

        factory = AgentFactory(
            llm_registry=empty_registry,
            tool_registry=mock_tool_registry,
            tracer=mock_tracer,
        )

        agent = ResolvedAgent(
            name="coder",
            model="unknown/gpt-4o",
            role=AgentRole.PRIMARY,
        )

        with pytest.raises(ValueError, match="No LLM providers registered"):
            await factory.create_adapter(agent)

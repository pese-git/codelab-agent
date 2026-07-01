"""Интеграционные тесты AgentRegistry и agents конфигурации с DI контейнером.

Проверяют что:
- AgentsConfig создаётся с правильными значениями по умолчанию
- AgentRegistry создаётся через DI с правильными зависимостями
- agents.strategy доступен через AppConfig
"""

from __future__ import annotations

import pytest

from codelab.server.agent.event_bus.bus import AgentEventBus
from codelab.server.agent.execution_engine import ExecutionEngine
from codelab.server.agent.factory import AgentFactory
from codelab.server.agent.registry import AgentRegistry
from codelab.server.agent.strategies.dispatcher import StrategyDispatcher
from codelab.server.config import AgentsConfig, AppConfig
from codelab.server.di import make_container
from codelab.server.storage.memory import InMemoryStorage


@pytest.fixture
def config():
    return AppConfig()


@pytest.fixture
def storage():
    return InMemoryStorage()


class TestAgentsConfig:
    """Тесты AgentsConfig."""

    def test_default_values(self):
        """AgentsConfig должен иметь правильные значения по умолчанию."""
        agents = AgentsConfig()
        assert agents.strategy == "single"
        assert agents.fallback_strategy == "single"
        # default_model=None означает "не задан явно" — выводится из config.llm
        # на уровне AppConfig (см. AppConfig._derive_agents_default_model).
        assert agents.default_model is None
        assert agents.max_steps == 7

    def test_custom_values(self):
        """AgentsConfig должен принимать кастомные значения."""
        agents = AgentsConfig(
            strategy="multi_orchestrated",
            fallback_strategy="single",
            default_model="anthropic/claude-sonnet-4-20250514",
            max_steps=10,
        )
        assert agents.strategy == "multi_orchestrated"
        assert agents.default_model == "anthropic/claude-sonnet-4-20250514"
        assert agents.max_steps == 10


class TestAppConfigWithAgents:
    """Тесты AppConfig с agents конфигурацией."""

    def test_agents_config_in_app_config(self):
        """AppConfig должен содержать agents конфигурацию."""
        config = AppConfig()
        assert isinstance(config.agents, AgentsConfig)
        assert config.agents.strategy == "single"

    def test_agents_config_custom(self):
        """AppConfig должен принимать кастомную agents конфигурацию."""
        config = AppConfig(agents=AgentsConfig(strategy="hierarchical"))
        assert config.agents.strategy == "hierarchical"


class TestAgentRegistryInDI:
    """Тесты AgentRegistry в DI контейнере."""

    @pytest.mark.asyncio
    async def test_creates_agent_registry(self, config, storage):
        container = make_container(config, storage)
        async with container() as request_container:
            registry = await request_container.get(AgentRegistry)
            assert isinstance(registry, AgentRegistry)

    @pytest.mark.asyncio
    async def test_agent_registry_is_singleton(self, config, storage):
        """AgentRegistry должен быть синглтоном (APP scope)."""
        container = make_container(config, storage)
        async with container() as request_container:
            registry1 = await request_container.get(AgentRegistry)
            registry2 = await request_container.get(AgentRegistry)
            assert registry1 is registry2

    @pytest.mark.asyncio
    async def test_agent_registry_has_event_bus(self, config, storage):
        """AgentRegistry должен иметь EventBus."""
        container = make_container(config, storage)
        async with container() as request_container:
            registry = await request_container.get(AgentRegistry)
            bus = await request_container.get(AgentEventBus)
            assert registry._event_bus is bus

    @pytest.mark.asyncio
    async def test_agent_registry_has_agent_factory(self, config, storage):
        """AgentRegistry должен иметь AgentFactory."""
        container = make_container(config, storage)
        async with container() as request_container:
            registry = await request_container.get(AgentRegistry)
            factory = await request_container.get(AgentFactory)
            assert registry._agent_factory is factory

    @pytest.mark.asyncio
    async def test_agent_registry_has_global_config(self, config, storage):
        """AgentRegistry должен иметь AgentsGlobalConfig из AppConfig."""
        container = make_container(config, storage)
        async with container() as request_container:
            registry = await request_container.get(AgentRegistry)
            assert registry._global_config is not None
            assert registry._global_config.default_model == config.agents.default_model
            assert registry._global_config.max_steps == config.agents.max_steps


class TestFullIntegration:
    """Полные интеграционные тесты."""

    @pytest.mark.asyncio
    async def test_all_multi_agent_components_connected(self, config, storage):
        """Все мультиагентные компоненты должны быть связаны через DI."""
        container = make_container(config, storage)
        async with container() as request_container:
            # Получаем все компоненты
            bus = await request_container.get(AgentEventBus)
            engine = await request_container.get(ExecutionEngine)
            factory = await request_container.get(AgentFactory)
            dispatcher = await request_container.get(StrategyDispatcher)
            registry = await request_container.get(AgentRegistry)

            # Проверяем что все созданы
            assert bus is not None
            assert engine is not None
            assert factory is not None
            assert dispatcher is not None
            assert registry is not None

            # Проверяем связи
            assert registry._event_bus is bus
            assert registry._agent_factory is factory
            # StrategyDispatcher теперь использует StrategyRegistry и StrategyDependencies
            assert dispatcher._strategy_registry is not None
            assert dispatcher._agent_registry is registry
            assert dispatcher._deps.event_bus is bus
            assert dispatcher._deps.execution_engine is engine

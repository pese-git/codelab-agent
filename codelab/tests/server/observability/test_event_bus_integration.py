"""Интеграционные тесты EventBus и MultiAgent компонентов с DI контейнером.

Проверяют что:
- EventBusProvider создаёт AgentEventBus с подключёнными observability
- MultiAgentProvider создаёт ExecutionEngine, AgentFactory, StrategyDispatcher
- Observability компоненты автоматически подписываются на EventBus
"""

from __future__ import annotations

import pytest

from codelab.server.agent.event_bus.bus import AgentEventBus
from codelab.server.agent.execution_engine import ExecutionEngine
from codelab.server.agent.factory import AgentFactory
from codelab.server.agent.strategies.dispatcher import StrategyDispatcher
from codelab.server.config import AppConfig
from codelab.server.di import make_container
from codelab.server.observability import EventTimeline, MetricsTracker, Tracer
from codelab.server.storage.memory import InMemoryStorage


@pytest.fixture
def config():
    return AppConfig()


@pytest.fixture
def storage():
    return InMemoryStorage()


class TestEventBusProvider:
    """Тесты EventBusProvider."""

    @pytest.mark.asyncio
    async def test_creates_event_bus(self, config, storage):
        container = make_container(config, storage)
        async with container() as request_container:
            bus = await request_container.get(AgentEventBus)
            assert isinstance(bus, AgentEventBus)

    @pytest.mark.asyncio
    async def test_event_bus_is_singleton(self, config, storage):
        """EventBus должен быть синглтоном (APP scope)."""
        container = make_container(config, storage)
        async with container() as request_container:
            bus1 = await request_container.get(AgentEventBus)
            bus2 = await request_container.get(AgentEventBus)
            assert bus1 is bus2

    @pytest.mark.asyncio
    async def test_observability_subscribed_to_bus(self, config, storage):
        """EventTimeline и MetricsTracker должны быть подписаны на EventBus."""
        container = make_container(config, storage)
        async with container() as request_container:
            await request_container.get(AgentEventBus)
            timeline = await request_container.get(EventTimeline)
            metrics = await request_container.get(MetricsTracker)

            # Проверяем что подписки созданы
            assert len(timeline._subscriptions) > 0
            assert len(metrics._subscriptions) > 0


class TestMultiAgentProvider:
    """Тесты MultiAgentProvider."""

    @pytest.mark.asyncio
    async def test_creates_execution_engine(self, config, storage):
        container = make_container(config, storage)
        async with container() as request_container:
            engine = await request_container.get(ExecutionEngine)
            assert isinstance(engine, ExecutionEngine)

    @pytest.mark.asyncio
    async def test_creates_agent_factory(self, config, storage):
        container = make_container(config, storage)
        async with container() as request_container:
            factory = await request_container.get(AgentFactory)
            assert isinstance(factory, AgentFactory)

    @pytest.mark.asyncio
    async def test_creates_strategy_dispatcher(self, config, storage):
        container = make_container(config, storage)
        async with container() as request_container:
            dispatcher = await request_container.get(StrategyDispatcher)
            assert isinstance(dispatcher, StrategyDispatcher)

    @pytest.mark.asyncio
    async def test_strategy_dispatcher_has_event_bus(self, config, storage):
        """StrategyDispatcher должен иметь EventBus."""
        container = make_container(config, storage)
        async with container() as request_container:
            dispatcher = await request_container.get(StrategyDispatcher)
            bus = await request_container.get(AgentEventBus)
            assert dispatcher._event_bus is bus

    @pytest.mark.asyncio
    async def test_strategy_dispatcher_has_tracer(self, config, storage):
        """StrategyDispatcher должен иметь Tracer."""
        container = make_container(config, storage)
        async with container() as request_container:
            dispatcher = await request_container.get(StrategyDispatcher)
            tracer = await request_container.get(Tracer)
            assert dispatcher._tracer is tracer

    @pytest.mark.asyncio
    async def test_execution_engine_is_singleton(self, config, storage):
        """ExecutionEngine должен быть синглтоном (APP scope)."""
        container = make_container(config, storage)
        async with container() as request_container:
            engine1 = await request_container.get(ExecutionEngine)
            engine2 = await request_container.get(ExecutionEngine)
            assert engine1 is engine2

    @pytest.mark.asyncio
    async def test_agent_factory_is_singleton(self, config, storage):
        """AgentFactory должен быть синглтоном (APP scope)."""
        container = make_container(config, storage)
        async with container() as request_container:
            factory1 = await request_container.get(AgentFactory)
            factory2 = await request_container.get(AgentFactory)
            assert factory1 is factory2

    @pytest.mark.asyncio
    async def test_strategy_dispatcher_is_singleton(self, config, storage):
        """StrategyDispatcher должен быть синглтоном (APP scope)."""
        container = make_container(config, storage)
        async with container() as request_container:
            dispatcher1 = await request_container.get(StrategyDispatcher)
            dispatcher2 = await request_container.get(StrategyDispatcher)
            assert dispatcher1 is dispatcher2


class TestFullIntegration:
    """Полные интеграционные тесты."""

    @pytest.mark.asyncio
    async def test_all_components_connected(self, config, storage):
        """Все компоненты должны быть связаны через DI."""
        container = make_container(config, storage)
        async with container() as request_container:
            # Получаем все компоненты
            bus = await request_container.get(AgentEventBus)
            timeline = await request_container.get(EventTimeline)
            metrics = await request_container.get(MetricsTracker)
            tracer = await request_container.get(Tracer)
            engine = await request_container.get(ExecutionEngine)
            factory = await request_container.get(AgentFactory)
            dispatcher = await request_container.get(StrategyDispatcher)

            # Проверяем что все созданы
            assert bus is not None
            assert timeline is not None
            assert metrics is not None
            assert tracer is not None
            assert engine is not None
            assert factory is not None
            assert dispatcher is not None

            # Проверяем связи
            assert dispatcher._event_bus is bus
            assert dispatcher._tracer is tracer
            assert dispatcher._execution_engine is engine

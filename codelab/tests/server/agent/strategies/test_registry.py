"""Тесты для StrategyRegistry и StrategyDescriptor."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from codelab.server.agent.strategies.descriptor import (
    StrategyDependencies,
    StrategyDescriptor,
)
from codelab.server.agent.strategies.registry import StrategyRegistry


class TestStrategyDescriptor:
    """Тесты для StrategyDescriptor."""

    def test_strategy_descriptor_creation(self) -> None:
        """Создание StrategyDescriptor с валидными полями."""
        descriptor = StrategyDescriptor(
            name="test",
            display_name="Test Strategy",
            description="Test description",
            factory=lambda deps: MagicMock(),
            validator=lambda registry: True,
        )

        assert descriptor.name == "test"
        assert descriptor.display_name == "Test Strategy"
        assert descriptor.description == "Test description"
        assert callable(descriptor.factory)
        assert callable(descriptor.validator)

    def test_is_available_returns_true(self) -> None:
        """is_available возвращает True когда validator возвращает True."""
        descriptor = StrategyDescriptor(
            name="test",
            display_name="Test",
            description="Test",
            factory=lambda deps: MagicMock(),
            validator=lambda registry: True,
        )

        mock_registry = MagicMock()
        assert descriptor.is_available(mock_registry) is True

    def test_is_available_returns_false(self) -> None:
        """is_available возвращает False когда validator возвращает False."""
        descriptor = StrategyDescriptor(
            name="test",
            display_name="Test",
            description="Test",
            factory=lambda deps: MagicMock(),
            validator=lambda registry: False,
        )

        mock_registry = MagicMock()
        assert descriptor.is_available(mock_registry) is False

    def test_create_instance_calls_factory(self) -> None:
        """create_instance вызывает factory с dependencies."""
        mock_agent = MagicMock()
        mock_deps = MagicMock()

        descriptor = StrategyDescriptor(
            name="test",
            display_name="Test",
            description="Test",
            factory=lambda deps: mock_agent,
            validator=lambda registry: True,
        )

        instance = descriptor.create_instance(mock_deps)
        assert instance is mock_agent


class TestStrategyDependencies:
    """Тесты для StrategyDependencies."""

    def test_strategy_dependencies_creation(self) -> None:
        """Создание StrategyDependencies с валидными полями."""
        mock_event_bus = MagicMock()
        mock_execution_engine = MagicMock()
        mock_tracer = MagicMock()

        deps = StrategyDependencies(
            event_bus=mock_event_bus,
            execution_engine=mock_execution_engine,
            tracer=mock_tracer,
            agent_name="test_agent",
        )

        assert deps.event_bus is mock_event_bus
        assert deps.execution_engine is mock_execution_engine
        assert deps.tracer is mock_tracer
        assert deps.agent_name == "test_agent"

    def test_strategy_dependencies_defaults(self) -> None:
        """StrategyDependencies имеет правильные defaults."""
        mock_event_bus = MagicMock()
        mock_execution_engine = MagicMock()

        deps = StrategyDependencies(
            event_bus=mock_event_bus,
            execution_engine=mock_execution_engine,
        )

        assert deps.tracer is None
        assert deps.agent_name == "primary"


class TestStrategyRegistry:
    """Тесты для StrategyRegistry."""

    def test_register_strategy(self) -> None:
        """Регистрация стратегии в реестре."""
        registry = StrategyRegistry()
        descriptor = StrategyDescriptor(
            name="test",
            display_name="Test",
            description="Test",
            factory=lambda deps: MagicMock(),
            validator=lambda registry: True,
        )

        registry.register(descriptor)

        assert registry.is_registered("test")
        assert registry.get("test") is descriptor

    def test_register_duplicate_raises_error(self) -> None:
        """Регистрация дубликата вызывает ValueError."""
        registry = StrategyRegistry()
        descriptor = StrategyDescriptor(
            name="test",
            display_name="Test",
            description="Test",
            factory=lambda deps: MagicMock(),
            validator=lambda registry: True,
        )

        registry.register(descriptor)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(descriptor)

    def test_get_strategy(self) -> None:
        """Получение стратегии по имени."""
        registry = StrategyRegistry()
        descriptor = StrategyDescriptor(
            name="test",
            display_name="Test",
            description="Test",
            factory=lambda deps: MagicMock(),
            validator=lambda registry: True,
        )

        registry.register(descriptor)

        result = registry.get("test")
        assert result is descriptor

    def test_get_nonexistent_returns_none(self) -> None:
        """Получение несуществующей стратегии возвращает None."""
        registry = StrategyRegistry()

        result = registry.get("nonexistent")
        assert result is None

    def test_unregister_strategy(self) -> None:
        """Удаление стратегии из реестра."""
        registry = StrategyRegistry()
        descriptor = StrategyDescriptor(
            name="test",
            display_name="Test",
            description="Test",
            factory=lambda deps: MagicMock(),
            validator=lambda registry: True,
        )

        registry.register(descriptor)
        assert registry.is_registered("test")

        result = registry.unregister("test")
        assert result is True
        assert not registry.is_registered("test")

    def test_unregister_nonexistent_returns_false(self) -> None:
        """Удаление несуществующей стратегии возвращает False."""
        registry = StrategyRegistry()

        result = registry.unregister("nonexistent")
        assert result is False

    def test_get_available_filters_by_validator(self) -> None:
        """get_available фильтрует стратегии по validator."""
        registry = StrategyRegistry()

        # Стратегия всегда доступна
        available_descriptor = StrategyDescriptor(
            name="available",
            display_name="Available",
            description="Available",
            factory=lambda deps: MagicMock(),
            validator=lambda registry: True,
        )

        # Стратегия недоступна
        unavailable_descriptor = StrategyDescriptor(
            name="unavailable",
            display_name="Unavailable",
            description="Unavailable",
            factory=lambda deps: MagicMock(),
            validator=lambda registry: False,
        )

        registry.register(available_descriptor)
        registry.register(unavailable_descriptor)

        mock_agent_registry = MagicMock()
        available = registry.get_available(mock_agent_registry)

        assert len(available) == 1
        assert available[0].name == "available"

    def test_get_available_with_conditional_validator(self) -> None:
        """get_available с условным validator."""
        registry = StrategyRegistry()

        # Стратегия доступна только если есть агенты
        def conditional_validator(agent_registry: MagicMock) -> bool:
            return len(agent_registry.get_all()) > 0

        descriptor = StrategyDescriptor(
            name="conditional",
            display_name="Conditional",
            description="Conditional",
            factory=lambda deps: MagicMock(),
            validator=conditional_validator,
        )

        registry.register(descriptor)

        # Пустой registry — стратегия недоступна
        empty_registry = MagicMock()
        empty_registry.get_all.return_value = {}
        available = registry.get_available(empty_registry)
        assert len(available) == 0

        # Непустой registry — стратегия доступна
        non_empty_registry = MagicMock()
        non_empty_registry.get_all.return_value = {"agent1": MagicMock()}
        available = registry.get_available(non_empty_registry)
        assert len(available) == 1

    def test_create_instance(self) -> None:
        """create_instance создает экземпляр стратегии."""
        registry = StrategyRegistry()
        mock_agent = MagicMock()
        mock_deps = MagicMock()

        descriptor = StrategyDescriptor(
            name="test",
            display_name="Test",
            description="Test",
            factory=lambda deps: mock_agent,
            validator=lambda registry: True,
        )

        registry.register(descriptor)

        instance = registry.create_instance("test", mock_deps)
        assert instance is mock_agent

    def test_create_instance_nonexistent_returns_none(self) -> None:
        """create_instance для несуществующей стратегии возвращает None."""
        registry = StrategyRegistry()
        mock_deps = MagicMock()

        instance = registry.create_instance("nonexistent", mock_deps)
        assert instance is None

    def test_create_instance_factory_error_returns_none(self) -> None:
        """create_instance возвращает None при ошибке factory."""
        registry = StrategyRegistry()

        def failing_factory(deps):
            raise ValueError("Factory error")

        descriptor = StrategyDescriptor(
            name="failing",
            display_name="Failing",
            description="Failing",
            factory=failing_factory,
            validator=lambda registry: True,
        )

        registry.register(descriptor)

        mock_deps = MagicMock()
        instance = registry.create_instance("failing", mock_deps)
        assert instance is None

    def test_list_all(self) -> None:
        """list_all возвращает все зарегистрированные стратегии."""
        registry = StrategyRegistry()

        descriptor1 = StrategyDescriptor(
            name="test1",
            display_name="Test1",
            description="Test1",
            factory=lambda deps: MagicMock(),
            validator=lambda registry: True,
        )

        descriptor2 = StrategyDescriptor(
            name="test2",
            display_name="Test2",
            description="Test2",
            factory=lambda deps: MagicMock(),
            validator=lambda registry: True,
        )

        registry.register(descriptor1)
        registry.register(descriptor2)

        all_descriptors = registry.list_all()
        assert len(all_descriptors) == 2
        assert descriptor1 in all_descriptors
        assert descriptor2 in all_descriptors

    def test_is_registered(self) -> None:
        """is_registered проверяет регистрацию стратегии."""
        registry = StrategyRegistry()
        descriptor = StrategyDescriptor(
            name="test",
            display_name="Test",
            description="Test",
            factory=lambda deps: MagicMock(),
            validator=lambda registry: True,
        )

        assert not registry.is_registered("test")

        registry.register(descriptor)
        assert registry.is_registered("test")

    def test_clear(self) -> None:
        """clear очищает реестр."""
        registry = StrategyRegistry()
        descriptor = StrategyDescriptor(
            name="test",
            display_name="Test",
            description="Test",
            factory=lambda deps: MagicMock(),
            validator=lambda registry: True,
        )

        registry.register(descriptor)
        assert registry.is_registered("test")

        registry.clear()
        assert not registry.is_registered("test")
        assert len(registry.list_all()) == 0


class TestSingleStrategyDescriptor:
    """Тесты для SINGLE_STRATEGY_DESCRIPTOR."""

    def test_single_strategy_descriptor_exists(self) -> None:
        """SINGLE_STRATEGY_DESCRIPTOR существует."""
        from codelab.server.protocol.handlers.strategies.single_strategy import (
            SINGLE_STRATEGY_DESCRIPTOR,
        )

        assert SINGLE_STRATEGY_DESCRIPTOR is not None
        assert SINGLE_STRATEGY_DESCRIPTOR.name == "single"
        assert SINGLE_STRATEGY_DESCRIPTOR.display_name == "Single"
        assert "Single agent execution" in SINGLE_STRATEGY_DESCRIPTOR.description

    def test_single_strategy_validator_always_true(self) -> None:
        """Validator для SingleStrategy всегда возвращает True."""
        from codelab.server.protocol.handlers.strategies.single_strategy import (
            SINGLE_STRATEGY_DESCRIPTOR,
        )

        mock_registry = MagicMock()
        assert SINGLE_STRATEGY_DESCRIPTOR.validator(mock_registry) is True

        # Даже с пустым registry
        mock_registry.get_all.return_value = {}
        assert SINGLE_STRATEGY_DESCRIPTOR.validator(mock_registry) is True

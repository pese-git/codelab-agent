"""Тесты для _build_active_strategy_config_spec в ACPProtocol."""

from __future__ import annotations

from unittest.mock import MagicMock

from codelab.server.agent.strategies.descriptor import StrategyDescriptor
from codelab.server.protocol.config_spec_builder import ConfigSpecBuilder


class TestBuildActiveStrategyConfigSpec:
    """Тесты для _build_active_strategy_config_spec."""

    def test_build_active_strategy_config_spec_no_registry(self) -> None:
        """Без StrategyRegistry возвращается fallback с только 'single'."""
        spec = ConfigSpecBuilder()._build_strategy_spec()

        assert spec["id"] == "_active_strategy"
        assert spec["name"] == "Strategy"
        assert spec["category"] == "strategy"
        assert spec["type"] == "select"
        assert spec["default"] == "single"
        assert len(spec["options"]) == 1
        assert spec["options"][0]["value"] == "single"

    def test_build_active_strategy_config_spec_with_registry(self) -> None:
        """Со StrategyRegistry возвращаются доступные стратегии."""
        # Создаём mock StrategyRegistry
        strategy_registry = MagicMock()
        agent_registry = MagicMock()
        agent_registry.is_initialized = False  # Чтобы _build_agent_config_spec вернулся на fallback

        # Создаём descriptors для доступных стратегий
        single_descriptor = MagicMock(spec=StrategyDescriptor)
        single_descriptor.name = "single"
        single_descriptor.display_name = "Single"
        single_descriptor.description = "Single agent execution"

        hierarchical_descriptor = MagicMock(spec=StrategyDescriptor)
        hierarchical_descriptor.name = "hierarchical"
        hierarchical_descriptor.display_name = "Hierarchical"
        hierarchical_descriptor.description = "Primary delegates to subagents"

        strategy_registry.get_available.return_value = [
            single_descriptor,
            hierarchical_descriptor,
        ]

        spec = ConfigSpecBuilder(
            strategy_registry=strategy_registry,
            agent_registry=agent_registry,
        )._build_strategy_spec()

        assert spec["id"] == "_active_strategy"
        assert spec["name"] == "Strategy"
        assert spec["category"] == "strategy"
        assert spec["default"] == "single"
        assert len(spec["options"]) == 2

        # Проверяем что опции содержат правильные значения
        option_values = [opt["value"] for opt in spec["options"]]
        assert "single" in option_values
        assert "hierarchical" in option_values

    def test_build_active_strategy_config_spec_empty_available(self) -> None:
        """Если нет доступных стратегий, возвращается fallback с 'single'."""
        strategy_registry = MagicMock()
        agent_registry = MagicMock()
        agent_registry.is_initialized = False
        strategy_registry.get_available.return_value = []

        spec = ConfigSpecBuilder(
            strategy_registry=strategy_registry,
            agent_registry=agent_registry,
        )._build_strategy_spec()

        assert spec["default"] == "single"
        assert len(spec["options"]) == 1
        assert spec["options"][0]["value"] == "single"

    def test_build_active_strategy_config_spec_uses_metadata(self) -> None:
        """Используются display_name и description из metadata."""
        strategy_registry = MagicMock()
        agent_registry = MagicMock()
        agent_registry.is_initialized = False

        descriptor = MagicMock(spec=StrategyDescriptor)
        descriptor.name = "hierarchical"
        descriptor.display_name = "Custom Hierarchical"
        descriptor.description = "Custom description"

        strategy_registry.get_available.return_value = [descriptor]

        spec = ConfigSpecBuilder(
            strategy_registry=strategy_registry,
            agent_registry=agent_registry,
        )._build_strategy_spec()

        # Должны использоваться значения из strategy_metadata, а не из descriptor
        hierarchical_option = next(
            opt for opt in spec["options"] if opt["value"] == "hierarchical"
        )
        assert hierarchical_option["name"] == "Hierarchical"  # из metadata
        assert hierarchical_option["description"] == "Primary delegates to subagents"  # из metadata

    def test_build_active_strategy_config_spec_registry_error(self) -> None:
        """При ошибке Registry возвращается fallback."""
        strategy_registry = MagicMock()
        agent_registry = MagicMock()
        agent_registry.is_initialized = False
        strategy_registry.get_available.side_effect = Exception("Registry error")

        spec = ConfigSpecBuilder(
            strategy_registry=strategy_registry,
            agent_registry=agent_registry,
        )._build_strategy_spec()

        # Должен вернуться fallback
        assert spec["default"] == "single"
        assert len(spec["options"]) == 1


class TestBuildConfigSpecsWithActiveStrategy:
    """Тесты для _build_config_specs с _active_strategy."""

    def test_build_config_specs_includes_active_strategy(self) -> None:
        """_build_config_specs включает _active_strategy."""
        specs = ConfigSpecBuilder().build()

        assert "_active_strategy" in specs
        assert specs["_active_strategy"]["id"] == "_active_strategy"

    def test_build_config_specs_active_strategy_with_registry(self) -> None:
        """_active_strategy формируется из StrategyRegistry."""
        strategy_registry = MagicMock()
        agent_registry = MagicMock()
        agent_registry.is_initialized = False

        descriptor = MagicMock(spec=StrategyDescriptor)
        descriptor.name = "single"
        descriptor.display_name = "Single"
        descriptor.description = "Single agent execution"

        strategy_registry.get_available.return_value = [descriptor]

        specs = ConfigSpecBuilder(
            strategy_registry=strategy_registry,
            agent_registry=agent_registry,
        ).build()

        assert "_active_strategy" in specs
        assert len(specs["_active_strategy"]["options"]) == 1
        assert specs["_active_strategy"]["options"][0]["value"] == "single"

"""Тесты покрытия для ViewModelProvider.

Проверяет создание ViewModels, ранее непокрытых тестами:
- ModelSelectorViewModel
- ModeSelectorViewModel
- AgentSelectorViewModel
- StrategySelectorViewModel
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from codelab.client.infrastructure.view_model_provider import ViewModelProvider
from codelab.client.presentation.config_option_selector_view_model import (
    AgentSelectorViewModel,
    ModeSelectorViewModel,
    StrategySelectorViewModel,
)
from codelab.client.presentation.model_selector_view_model import ModelSelectorViewModel


@pytest.fixture
def provider() -> ViewModelProvider:
    """Создаёт экземпляр провайдера ViewModels."""
    return ViewModelProvider()


@pytest.fixture
def coordinator() -> MagicMock:
    """Создаёт mock SessionCoordinator."""
    return MagicMock()


@pytest.fixture
def event_bus() -> MagicMock:
    """Создаёт mock EventBus."""
    return MagicMock()


@pytest.fixture
def logger() -> MagicMock:
    """Создаёт mock logger."""
    return MagicMock()


class TestViewModelProviderSelectors:
    """Тесты для selector ViewModels."""

    def test_get_model_selector_vm(
        self,
        provider: ViewModelProvider,
        coordinator: MagicMock,
        event_bus: MagicMock,
        logger: MagicMock,
    ) -> None:
        """get_model_selector_vm возвращает ModelSelectorViewModel."""
        vm = provider.get_model_selector_vm(coordinator, event_bus, logger)

        assert isinstance(vm, ModelSelectorViewModel)
        assert vm.coordinator is coordinator

    def test_get_mode_selector_vm(
        self,
        provider: ViewModelProvider,
        coordinator: MagicMock,
        event_bus: MagicMock,
        logger: MagicMock,
    ) -> None:
        """get_mode_selector_vm возвращает ModeSelectorViewModel."""
        vm = provider.get_mode_selector_vm(coordinator, event_bus, logger)

        assert isinstance(vm, ModeSelectorViewModel)
        assert vm.coordinator is coordinator
        assert vm.config_id == "mode"

    def test_get_agent_selector_vm(
        self,
        provider: ViewModelProvider,
        coordinator: MagicMock,
        event_bus: MagicMock,
        logger: MagicMock,
    ) -> None:
        """get_agent_selector_vm возвращает AgentSelectorViewModel."""
        vm = provider.get_agent_selector_vm(coordinator, event_bus, logger)

        assert isinstance(vm, AgentSelectorViewModel)
        assert vm.coordinator is coordinator
        assert vm.config_id == "_agent"

    def test_get_strategy_selector_vm(
        self,
        provider: ViewModelProvider,
        coordinator: MagicMock,
        event_bus: MagicMock,
        logger: MagicMock,
    ) -> None:
        """get_strategy_selector_vm возвращает StrategySelectorViewModel."""
        vm = provider.get_strategy_selector_vm(coordinator, event_bus, logger)

        assert isinstance(vm, StrategySelectorViewModel)
        assert vm.coordinator is coordinator
        assert vm.config_id == "_active_strategy"

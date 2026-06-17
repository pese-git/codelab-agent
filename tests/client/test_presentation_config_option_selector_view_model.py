"""Тесты для ConfigOptionSelectorViewModel."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.client.presentation.config_option_selector_view_model import (
    AgentSelectorViewModel,
    ConfigOption,
    ConfigOptionSelectorViewModel,
    ModeSelectorViewModel,
    StrategySelectorViewModel,
)


class TestConfigOptionSelectorViewModel:
    """Тесты для универсального ConfigOptionSelectorViewModel."""

    def test_init_with_config_id(self) -> None:
        """ViewModel инициализируется с config_id и title."""
        coordinator = MagicMock()
        vm = ConfigOptionSelectorViewModel(
            config_id="test_config",
            title="Test Config",
            coordinator=coordinator,
        )

        assert vm.config_id == "test_config"
        assert vm.title == "Test Config"
        assert vm.current_value.value is None
        assert vm.available_options.value == []

    def test_update_from_config_finds_correct_option(self) -> None:
        """update_from_config находит нужный config option по id."""
        coordinator = MagicMock()
        vm = ConfigOptionSelectorViewModel(
            config_id="mode",
            title="Режим",
            coordinator=coordinator,
        )

        config_options = [
            {
                "id": "model",
                "currentValue": "gpt-4",
                "options": [{"value": "gpt-4", "name": "GPT-4"}],
            },
            {
                "id": "mode",
                "currentValue": "code",
                "options": [
                    {"value": "ask", "name": "Ask"},
                    {"value": "code", "name": "Code"},
                ],
            },
        ]

        vm.update_from_config(config_options, session_id="test_session")

        assert vm.current_value.value == "code"
        assert len(vm.available_options.value) == 2
        assert vm.available_options.value[0].value == "ask"
        assert vm.available_options.value[1].value == "code"

    def test_update_from_config_uses_default_when_no_current(self) -> None:
        """update_from_config использует default если нет currentValue."""
        coordinator = MagicMock()
        vm = ConfigOptionSelectorViewModel(
            config_id="mode",
            title="Режим",
            coordinator=coordinator,
        )

        config_options = [
            {
                "id": "mode",
                "default": "ask",
                "options": [
                    {"value": "ask", "name": "Ask"},
                    {"value": "code", "name": "Code"},
                ],
            },
        ]

        vm.update_from_config(config_options, session_id="test_session")

        assert vm.current_value.value == "ask"

    def test_update_from_config_config_not_found(self) -> None:
        """update_from_config не обновляет если config_id не найден."""
        coordinator = MagicMock()
        vm = ConfigOptionSelectorViewModel(
            config_id="nonexistent",
            title="Nonexistent",
            coordinator=coordinator,
        )

        config_options = [
            {
                "id": "mode",
                "currentValue": "code",
                "options": [{"value": "code", "name": "Code"}],
            },
        ]

        vm.update_from_config(config_options, session_id="test_session")

        assert vm.current_value.value is None
        assert vm.available_options.value == []

    def test_get_current_label_returns_label(self) -> None:
        """get_current_label возвращает label текущего значения."""
        coordinator = MagicMock()
        vm = ConfigOptionSelectorViewModel(
            config_id="mode",
            title="Режим",
            coordinator=coordinator,
        )

        config_options = [
            {
                "id": "mode",
                "currentValue": "code",
                "options": [
                    {"value": "ask", "name": "Ask Mode"},
                    {"value": "code", "name": "Code Mode"},
                ],
            },
        ]

        vm.update_from_config(config_options, session_id="test_session")

        assert vm.get_current_label() == "Code Mode"

    def test_get_current_label_returns_value_if_not_found(self) -> None:
        """get_current_label возвращает value если option не найден."""
        coordinator = MagicMock()
        vm = ConfigOptionSelectorViewModel(
            config_id="mode",
            title="Режим",
            coordinator=coordinator,
        )

        vm.current_value.value = "unknown_value"

        assert vm.get_current_label() == "unknown_value"

    def test_get_current_label_returns_not_selected_if_none(self) -> None:
        """get_current_label возвращает 'Не выбрано' если current_value is None."""
        coordinator = MagicMock()
        vm = ConfigOptionSelectorViewModel(
            config_id="mode",
            title="Режим",
            coordinator=coordinator,
        )

        assert vm.get_current_label() == "Не выбрано"

    @pytest.mark.asyncio
    async def test_select_option_calls_coordinator(self) -> None:
        """select_option_cmd вызывает coordinator.set_config_option."""
        coordinator = MagicMock()
        coordinator.set_config_option = AsyncMock(
            return_value={"configOptions": []},
        )
        vm = ConfigOptionSelectorViewModel(
            config_id="mode",
            title="Режим",
            coordinator=coordinator,
        )

        # Добавляем доступные опции
        vm.available_options.value = [
            ConfigOption(value="ask", label="Ask"),
            ConfigOption(value="code", label="Code"),
        ]

        await vm.select_option_cmd.execute(
            session_id="test_session",
            value="code",
        )

        coordinator.set_config_option.assert_called_once_with(
            session_id="test_session",
            config_id="mode",
            value="code",
        )
        assert vm.current_value.value == "code"

    @pytest.mark.asyncio
    async def test_select_option_raises_if_not_available(self) -> None:
        """select_option_cmd raises если опция недоступна."""
        coordinator = MagicMock()
        vm = ConfigOptionSelectorViewModel(
            config_id="mode",
            title="Режим",
            coordinator=coordinator,
        )

        vm.available_options.value = [
            ConfigOption(value="ask", label="Ask"),
        ]

        with pytest.raises(ValueError, match="not available"):
            await vm.select_option_cmd.execute(
                session_id="test_session",
                value="nonexistent",
            )

    def test_parse_options_with_extra_data(self) -> None:
        """_parse_options извлекает extra данные (pricing и т.д.)."""
        raw_options = [
            {
                "value": "gpt-4",
                "name": "GPT-4",
                "description": "Most capable model",
                "_pricing": "$0.03/1K tokens",
            },
        ]

        options = ConfigOptionSelectorViewModel._parse_options(raw_options)

        assert len(options) == 1
        assert options[0].value == "gpt-4"
        assert options[0].label == "GPT-4"
        assert options[0].description == "Most capable model"
        assert options[0].extra["pricing"] == "$0.03/1K tokens"


class TestModeSelectorViewModel:
    """Тесты для ModeSelectorViewModel."""

    def test_init_sets_correct_config_id(self) -> None:
        """ModeSelectorViewModel инициализируется с config_id='mode'."""
        coordinator = MagicMock()
        vm = ModeSelectorViewModel(coordinator=coordinator)

        assert vm.config_id == "mode"
        assert vm.title == "Режим"


class TestAgentSelectorViewModel:
    """Тесты для AgentSelectorViewModel."""

    def test_init_sets_correct_config_id(self) -> None:
        """AgentSelectorViewModel инициализируется с config_id='_agent'."""
        coordinator = MagicMock()
        vm = AgentSelectorViewModel(coordinator=coordinator)

        assert vm.config_id == "_agent"
        assert vm.title == "Агент"


class TestStrategySelectorViewModel:
    """Тесты для StrategySelectorViewModel."""

    def test_init_sets_correct_config_id(self) -> None:
        """StrategySelectorViewModel инициализируется с config_id='_active_strategy'."""
        coordinator = MagicMock()
        vm = StrategySelectorViewModel(coordinator=coordinator)

        assert vm.config_id == "_active_strategy"
        assert vm.title == "Стратегия"


class TestConfigOptionSelectorAdditionalCoverage:
    """Дополнительные тесты для непокрытых строк."""

    def test_update_current_value(self) -> None:
        """update_current_value обновляет current_value."""
        coordinator = MagicMock()
        vm = ConfigOptionSelectorViewModel(
            coordinator=coordinator,
            config_id="test",
            title="Test",
        )
        vm.update_current_value("new_value")
        assert vm.current_value.value == "new_value"

    @pytest.mark.asyncio
    async def test_open_modal(self) -> None:
        """_open_modal устанавливает is_modal_open=True."""
        coordinator = MagicMock()
        vm = ConfigOptionSelectorViewModel(
            coordinator=coordinator,
            config_id="test",
            title="Test",
        )
        await vm._open_modal()
        assert vm.is_modal_open.value is True

    @pytest.mark.asyncio
    async def test_close_modal(self) -> None:
        """_close_modal устанавливает is_modal_open=False."""
        coordinator = MagicMock()
        vm = ConfigOptionSelectorViewModel(
            coordinator=coordinator,
            config_id="test",
            title="Test",
        )
        vm.is_modal_open.value = True
        await vm._close_modal()
        assert vm.is_modal_open.value is False

    def test_parse_options_non_dict(self) -> None:
        """_parse_options пропускает non-dict элементы."""
        raw_options = ["not a dict", 123, None]
        options = ConfigOptionSelectorViewModel._parse_options(raw_options)
        assert len(options) == 0

    def test_parse_options_empty_value(self) -> None:
        """_parse_options пропускает options с пустым value."""
        raw_options = [{"value": "", "name": "Empty"}]
        options = ConfigOptionSelectorViewModel._parse_options(raw_options)
        assert len(options) == 0

    def test_parse_options_with_pricing(self) -> None:
        """_parse_options извлекает pricing из option."""
        raw_options = [
            {
                "value": "gpt-4",
                "name": "GPT-4",
                "pricing": {"input": 0.03, "output": 0.06},
            },
        ]
        options = ConfigOptionSelectorViewModel._parse_options(raw_options)
        assert len(options) == 1
        assert options[0].extra["pricing"] == {"input": 0.03, "output": 0.06}

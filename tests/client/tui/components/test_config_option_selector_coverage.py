"""Тесты покрытия для ConfigOptionSelector компонента.

Проверяют непокрытые строки в:
- ConfigOptionItem
- ConfigOptionSelectorModal
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from textual.app import App
from textual.widgets import Input, Label

from codelab.client.presentation.config_option_selector_view_model import (
    ConfigOption,
    ConfigOptionSelectorViewModel,
)
from codelab.client.tui.components.config_option_selector import (
    ConfigOptionItem,
    ConfigOptionSelectorModal,
)
from codelab.client.tui.components.keyboard_manager import KeyboardManager


def _make_view_model(options: list[ConfigOption] | None = None) -> ConfigOptionSelectorViewModel:
    """Создает ViewModel с заданным списком опций."""
    coordinator = MagicMock()
    vm = ConfigOptionSelectorViewModel(
        config_id="model",
        title="Модель",
        coordinator=coordinator,
    )
    vm.available_options.value = options or []
    vm.current_value.value = None
    return vm


class TestConfigOptionItem:
    """Тесты для ConfigOptionItem."""

    def test_option_property(self) -> None:
        """Свойство option возвращает исходные данные."""
        option = ConfigOption(value="test", label="Test")
        item = ConfigOptionItem(option)
        assert item.option is option

    def test_compose_selected_and_current(self) -> None:
        """Выбранная и текущая опция получают CSS классы."""
        option = ConfigOption(value="test", label="Test")
        item = ConfigOptionItem(option, selected=True, is_current=True)
        children = list(item.compose())
        assert item.has_class("-selected")
        assert item.has_class("-current")
        assert any(isinstance(child, Label) for child in children)

    def test_compose_with_description_and_pricing(self) -> None:
        """Элемент отображает описание и pricing."""
        option = ConfigOption(
            value="test",
            label="Test",
            description="Описание",
            extra={"pricing": "$1"},
        )
        item = ConfigOptionItem(option)
        labels = [child for child in item.compose() if isinstance(child, Label)]
        text = str(labels[1].render()) if len(labels) > 1 else ""
        assert "Описание" in text
        assert "$1" in text

    def test_compose_without_details(self) -> None:
        """Элемент без деталей содержит только название."""
        option = ConfigOption(value="test", label="Test")
        item = ConfigOptionItem(option)
        labels = [child for child in item.compose() if isinstance(child, Label)]
        assert len(labels) == 1

    def test_on_click_posts_selected(self) -> None:
        """Клик по опции отправляет сообщение Selected."""
        option = ConfigOption(value="test", label="Test")
        item = ConfigOptionItem(option)
        posted: list[ConfigOptionItem.Selected] = []
        item.post_message = posted.append
        item.on_click()
        assert len(posted) == 1
        assert posted[0].option is option


class TestConfigOptionSelectorModal:
    """Тесты для ConfigOptionSelectorModal."""

    def test_init_defaults(self) -> None:
        """Инициализация с значениями по умолчанию."""
        vm = _make_view_model()
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")
        assert modal._view_model is vm
        assert modal._session_id == "session_1"
        assert isinstance(modal._keyboard_manager, KeyboardManager)
        assert modal._filtered_options == []
        assert modal._selected_index == 0

    def test_init_custom_keyboard_manager(self) -> None:
        """Можно передать собственный KeyboardManager."""
        vm = _make_view_model()
        manager = KeyboardManager()
        modal = ConfigOptionSelectorModal(vm, session_id="session_1", keyboard_manager=manager)
        assert modal._keyboard_manager is manager

    async def test_compose_in_app(self) -> None:
        """Модальное окно монтируется в приложении с ожидаемой структурой."""
        option = ConfigOption(value="openai/gpt-4o", label="GPT-4o")
        vm = _make_view_model(options=[option])
        vm.current_value.value = "openai/gpt-4o"
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")

        class TestApp(App):
            def compose(self):
                yield modal

        async with TestApp().run_test() as pilot:
            assert pilot.app.query_one("#option-search", Input)
            assert pilot.app.query_one(".options-scroll")
            assert pilot.app.query_one(".modal-title")
            assert pilot.app.query_one(".current-option")

    def test_render_options_with_data(self) -> None:
        """Рендер списка опций возвращает элементы."""
        option = ConfigOption(value="openai/gpt-4o", label="GPT-4o")
        vm = _make_view_model(options=[option])
        vm.current_value.value = "openai/gpt-4o"
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")
        children = list(modal._render_options())
        assert any(isinstance(child, ConfigOptionItem) for child in children)

    def test_render_options_empty_available(self) -> None:
        """При пустом списке доступных опций показывается сообщение."""
        vm = _make_view_model()
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")
        children = list(modal._render_options())
        assert any("недоступен" in str(child.render()).lower() for child in children)

    def test_on_mount_focuses_input(self) -> None:
        """При открытии фокус на поле поиска."""
        vm = _make_view_model()
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")
        input_mock = MagicMock()
        with patch.object(modal, "query_one", return_value=input_mock):
            modal.on_mount()
        input_mock.focus.assert_called_once()

    def test_filter_options_empty_query(self) -> None:
        """Пустой запрос сбрасывает фильтр."""
        option = ConfigOption(value="openai/gpt-4o", label="GPT-4o")
        vm = _make_view_model(options=[option])
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")
        modal._filter_options("")
        assert modal._filtered_options == [option]
        assert modal._selected_index == 0

    def test_filter_options_non_empty(self) -> None:
        """Фильтр оставляет только подходящие опции."""
        option1 = ConfigOption(value="openai/gpt-4o", label="GPT-4o")
        option2 = ConfigOption(value="anthropic/claude", label="Claude")
        vm = _make_view_model(options=[option1, option2])
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")
        modal._filter_options("gpt")
        assert modal._filtered_options == [option1]
        assert modal._selected_index == 0

    def test_filter_options_no_results(self) -> None:
        """При отсутствии совпадений список пуст."""
        option = ConfigOption(value="openai/gpt-4o", label="GPT-4o")
        vm = _make_view_model(options=[option])
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")
        modal._filter_options("xyznoexist")
        assert modal._filtered_options == []
        assert modal._selected_index == 0

    def test_fuzzy_match(self) -> None:
        """Fuzzy match работает по порядку символов."""
        vm = _make_view_model()
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")
        assert modal._fuzzy_match("abc", "abc") is True
        assert modal._fuzzy_match("abc", "aabbcc") is True
        assert modal._fuzzy_match("abc", "cba") is False
        assert modal._fuzzy_match("", "text") is True

    def test_update_selection(self) -> None:
        """Обновление выделения меняет класс у найденных элементов."""
        option = ConfigOption(value="openai/gpt-4o", label="GPT-4o")
        vm = _make_view_model(options=[option])
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")
        modal._selected_index = 0
        item_mock = MagicMock()
        with patch.object(modal, "query_one", return_value=item_mock):
            modal._update_selection()
        item_mock.set_class.assert_called_with(True, "-selected")

    def test_update_selection_exception_suppressed(self) -> None:
        """Исключения при обновлении выделения подавляются."""
        vm = _make_view_model()
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")
        with patch.object(modal, "query_one", side_effect=Exception("boom")):
            modal._update_selection()

    @pytest.mark.asyncio
    async def test_refresh_options(self) -> None:
        """Пересоздание списка опций работает."""
        vm = _make_view_model()
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")
        scroll_mock = AsyncMock()
        with patch.object(modal, "query_one", return_value=scroll_mock):
            await modal._refresh_options()
        scroll_mock.remove_children.assert_called_once()
        scroll_mock.mount.assert_called_once()

    @pytest.mark.asyncio
    async def test_input_changed(self) -> None:
        """Изменение ввода фильтрует и обновляет список."""
        option = ConfigOption(value="openai/gpt-4o", label="GPT-4o")
        vm = _make_view_model(options=[option])
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")
        event_mock = MagicMock()
        event_mock.value = "gpt"
        with patch.object(modal, "_refresh_options") as refresh_mock:
            await modal.on_input_changed(event_mock)
        assert modal._filtered_options == [option]
        refresh_mock.assert_awaited_once()

    def test_action_close(self) -> None:
        """Закрытие модального окна возвращает None."""
        vm = _make_view_model()
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")
        dismissed: list[object] = []
        modal.dismiss = dismissed.append  # type: ignore[method-assign]
        modal.action_close()
        assert dismissed == [None]

    def test_action_previous(self) -> None:
        """Переход к предыдущей опции уменьшает индекс."""
        option1 = ConfigOption(value="a", label="A")
        option2 = ConfigOption(value="b", label="B")
        vm = _make_view_model(options=[option1, option2])
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")
        modal._selected_index = 1
        with patch.object(modal, "_update_selection") as update_mock:
            modal.action_previous()
        assert modal._selected_index == 0
        update_mock.assert_called_once()

    def test_action_previous_at_zero(self) -> None:
        """Переход вверх из нулевого индекса не меняет его."""
        vm = _make_view_model(options=[ConfigOption(value="a", label="A")])
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")
        modal._selected_index = 0
        with patch.object(modal, "_update_selection") as update_mock:
            modal.action_previous()
        assert modal._selected_index == 0
        update_mock.assert_not_called()

    def test_action_previous_no_options(self) -> None:
        """Переход вверх без опций не падает."""
        vm = _make_view_model()
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")
        modal.action_previous()
        assert modal._selected_index == 0

    def test_action_next(self) -> None:
        """Переход к следующей опции увеличивает индекс."""
        option1 = ConfigOption(value="a", label="A")
        option2 = ConfigOption(value="b", label="B")
        vm = _make_view_model(options=[option1, option2])
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")
        with patch.object(modal, "_update_selection") as update_mock:
            modal.action_next()
        assert modal._selected_index == 1
        update_mock.assert_called_once()

    def test_action_next_at_end(self) -> None:
        """Переход вниз из последнего индекса не меняет его."""
        option = ConfigOption(value="a", label="A")
        vm = _make_view_model(options=[option])
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")
        modal._selected_index = 0
        with patch.object(modal, "_update_selection") as update_mock:
            modal.action_next()
        assert modal._selected_index == 0
        update_mock.assert_not_called()

    def test_action_next_no_options(self) -> None:
        """Переход вниз без опций не падает."""
        vm = _make_view_model()
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")
        modal.action_next()
        assert modal._selected_index == 0

    def test_action_select(self) -> None:
        """Выбор опции закрывает окно со значением."""
        option = ConfigOption(value="openai/gpt-4o", label="GPT-4o")
        vm = _make_view_model(options=[option])
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")
        dismissed: list[object] = []
        modal.dismiss = dismissed.append  # type: ignore[method-assign]
        modal.action_select()
        assert dismissed == ["openai/gpt-4o"]

    def test_action_select_index_out_of_range(self) -> None:
        """Выбор с невалидным индексом ничего не делает."""
        vm = _make_view_model()
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")
        modal._selected_index = -1
        dismissed: list[object] = []
        modal.dismiss = dismissed.append  # type: ignore[method-assign]
        modal.action_select()
        assert dismissed == []

    def test_on_config_option_item_selected(self) -> None:
        """Выбор через ConfigOptionItem закрывает окно со значением."""
        option = ConfigOption(value="openai/gpt-4o", label="GPT-4o")
        vm = _make_view_model()
        modal = ConfigOptionSelectorModal(vm, session_id="session_1")
        dismissed: list[object] = []
        modal.dismiss = dismissed.append  # type: ignore[method-assign]
        modal.on_config_option_item_selected(ConfigOptionItem.Selected(option))
        assert dismissed == ["openai/gpt-4o"]

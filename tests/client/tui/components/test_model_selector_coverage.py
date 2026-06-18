"""Тесты покрытия для ModelSelector компонента.

Проверяют непокрытые строки в:
- ModelItem
- ModelSelectorModal
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from textual.app import App
from textual.widgets import Input, Label

from codelab.client.presentation.model_selector_view_model import (
    ModelOption,
    ModelSelectorViewModel,
)
from codelab.client.tui.components.keyboard_manager import KeyboardManager
from codelab.client.tui.components.model_selector import ModelItem, ModelSelectorModal


def _make_view_model(models: list[ModelOption] | None = None) -> ModelSelectorViewModel:
    """Создает ViewModel с заданным списком моделей."""
    coordinator = MagicMock()
    vm = ModelSelectorViewModel(coordinator=coordinator)
    vm.available_models.value = models or []
    vm.current_model.value = None
    return vm


class TestModelItem:
    """Тесты для ModelItem."""

    def test_model_property(self) -> None:
        """Свойство model возвращает исходные данные."""
        model = ModelOption(value="openai/gpt-4o", label="GPT-4o")
        item = ModelItem(model)
        assert item.model is model

    def test_compose_selected_and_current(self) -> None:
        """Выбранная и текущая модель получают CSS классы."""
        model = ModelOption(value="openai/gpt-4o", label="GPT-4o")
        item = ModelItem(model, selected=True, is_current=True)
        children = list(item.compose())
        assert item.has_class("-selected")
        assert item.has_class("-current")
        assert any(isinstance(child, Label) for child in children)

    def test_compose_with_provider_description_pricing(self) -> None:
        """Элемент отображает провайдера, описание и стоимость."""
        model = ModelOption(
            value="openai/gpt-4o",
            label="GPT-4o",
            description="128K context",
            pricing="$1",
        )
        item = ModelItem(model)
        labels = [child for child in item.compose() if isinstance(child, Label)]
        second_text = str(labels[1].render()) if len(labels) > 1 else ""
        assert item._model.provider_id == "openai"
        assert "128K context" in second_text
        assert "$1" in second_text

    def test_compose_without_details(self) -> None:
        """Элемент без деталей содержит только название."""
        model = ModelOption(value="openai/gpt-4o", label="GPT-4o")
        item = ModelItem(model)
        labels = [child for child in item.compose() if isinstance(child, Label)]
        assert len(labels) == 1

    def test_on_click_posts_selected(self) -> None:
        """Клик по модели отправляет сообщение Selected."""
        model = ModelOption(value="openai/gpt-4o", label="GPT-4o")
        item = ModelItem(model)
        posted: list[ModelItem.Selected] = []
        item.post_message = posted.append
        item.on_click()
        assert len(posted) == 1
        assert posted[0].model is model


class TestModelSelectorModal:
    """Тесты для ModelSelectorModal."""

    def test_init_defaults(self) -> None:
        """Инициализация с значениями по умолчанию."""
        vm = _make_view_model()
        modal = ModelSelectorModal(vm, session_id="session_1")
        assert modal._view_model is vm
        assert modal._session_id == "session_1"
        assert isinstance(modal._keyboard_manager, KeyboardManager)
        assert modal._filtered_models == []
        assert modal._selected_index == 0

    def test_init_custom_keyboard_manager(self) -> None:
        """Можно передать собственный KeyboardManager."""
        vm = _make_view_model()
        manager = KeyboardManager()
        modal = ModelSelectorModal(vm, session_id="session_1", keyboard_manager=manager)
        assert modal._keyboard_manager is manager

    async def test_compose_in_app(self) -> None:
        """Модальное окно монтируется в приложении с ожидаемой структурой."""
        model = ModelOption(value="openai/gpt-4o", label="GPT-4o")
        vm = _make_view_model(models=[model])
        vm.current_model.value = "openai/gpt-4o"
        modal = ModelSelectorModal(vm, session_id="session_1")

        class TestApp(App):
            def compose(self):
                yield modal

        async with TestApp().run_test() as pilot:
            assert pilot.app.query_one("#model-search", Input)
            assert pilot.app.query_one(".models-scroll")
            assert pilot.app.query_one(".modal-title")
            assert pilot.app.query_one(".current-model")

    def test_render_models_with_data(self) -> None:
        """Рендер списка моделей возвращает элементы."""
        model = ModelOption(value="openai/gpt-4o", label="GPT-4o")
        vm = _make_view_model(models=[model])
        vm.current_model.value = "openai/gpt-4o"
        modal = ModelSelectorModal(vm, session_id="session_1")
        children = list(modal._render_models())
        assert any(isinstance(child, ModelItem) for child in children)

    def test_render_models_no_results(self) -> None:
        """При пустом списке моделей показывается сообщение."""
        vm = _make_view_model()
        modal = ModelSelectorModal(vm, session_id="session_1")
        children = list(modal._render_models())
        assert any("недоступен" in str(child.render()).lower() for child in children)

    def test_on_mount_focuses_input(self) -> None:
        """При открытии фокус на поле поиска."""
        vm = _make_view_model()
        modal = ModelSelectorModal(vm, session_id="session_1")
        input_mock = MagicMock()
        with patch.object(modal, "query_one", return_value=input_mock):
            modal.on_mount()
        input_mock.focus.assert_called_once()

    def test_filter_models_empty_query(self) -> None:
        """Пустой запрос сбрасывает фильтр."""
        model = ModelOption(value="openai/gpt-4o", label="GPT-4o")
        vm = _make_view_model(models=[model])
        modal = ModelSelectorModal(vm, session_id="session_1")
        modal._filter_models("")
        assert modal._filtered_models == [model]
        assert modal._selected_index == 0

    def test_filter_models_non_empty(self) -> None:
        """Фильтр оставляет только подходящие модели."""
        model1 = ModelOption(value="openai/gpt-4o", label="GPT-4o")
        model2 = ModelOption(value="anthropic/claude", label="Claude")
        vm = _make_view_model(models=[model1, model2])
        modal = ModelSelectorModal(vm, session_id="session_1")
        modal._filter_models("gpt")
        assert modal._filtered_models == [model1]
        assert modal._selected_index == 0

    def test_filter_models_by_provider(self) -> None:
        """Фильтр работает по провайдеру."""
        model1 = ModelOption(value="openai/gpt-4o", label="GPT-4o")
        model2 = ModelOption(value="anthropic/claude", label="Claude")
        vm = _make_view_model(models=[model1, model2])
        modal = ModelSelectorModal(vm, session_id="session_1")
        modal._filter_models("openai")
        assert modal._filtered_models == [model1]

    def test_filter_models_no_results(self) -> None:
        """При отсутствии совпадений список пуст."""
        model = ModelOption(value="openai/gpt-4o", label="GPT-4o")
        vm = _make_view_model(models=[model])
        modal = ModelSelectorModal(vm, session_id="session_1")
        modal._filter_models("xyznoexist")
        assert modal._filtered_models == []
        assert modal._selected_index == 0

    def test_fuzzy_match(self) -> None:
        """Fuzzy match работает по порядку символов."""
        vm = _make_view_model()
        modal = ModelSelectorModal(vm, session_id="session_1")
        assert modal._fuzzy_match("abc", "abc") is True
        assert modal._fuzzy_match("abc", "aabbcc") is True
        assert modal._fuzzy_match("abc", "cba") is False
        assert modal._fuzzy_match("", "text") is True

    def test_update_selection(self) -> None:
        """Обновление выделения меняет класс у найденных элементов."""
        model = ModelOption(value="openai/gpt-4o", label="GPT-4o")
        vm = _make_view_model(models=[model])
        modal = ModelSelectorModal(vm, session_id="session_1")
        modal._selected_index = 0
        item_mock = MagicMock()
        with patch.object(modal, "query_one", return_value=item_mock):
            modal._update_selection()
        item_mock.set_class.assert_called_with(True, "-selected")

    def test_update_selection_exception_suppressed(self) -> None:
        """Исключения при обновлении выделения подавляются."""
        vm = _make_view_model()
        modal = ModelSelectorModal(vm, session_id="session_1")
        with patch.object(modal, "query_one", side_effect=Exception("boom")):
            modal._update_selection()

    @pytest.mark.asyncio
    async def test_refresh_models(self) -> None:
        """Пересоздание списка моделей работает."""
        vm = _make_view_model()
        modal = ModelSelectorModal(vm, session_id="session_1")
        scroll_mock = AsyncMock()
        with patch.object(modal, "query_one", return_value=scroll_mock):
            await modal._refresh_models()
        scroll_mock.remove_children.assert_called_once()
        scroll_mock.mount.assert_called_once()

    @pytest.mark.asyncio
    async def test_input_changed(self) -> None:
        """Изменение ввода фильтрует и обновляет список."""
        model = ModelOption(value="openai/gpt-4o", label="GPT-4o")
        vm = _make_view_model(models=[model])
        modal = ModelSelectorModal(vm, session_id="session_1")
        event_mock = MagicMock()
        event_mock.value = "gpt"
        with patch.object(modal, "_refresh_models") as refresh_mock:
            await modal.on_input_changed(event_mock)
        assert modal._filtered_models == [model]
        refresh_mock.assert_awaited_once()

    def test_action_close(self) -> None:
        """Закрытие модального окна возвращает None."""
        vm = _make_view_model()
        modal = ModelSelectorModal(vm, session_id="session_1")
        dismissed: list[object] = []
        modal.dismiss = dismissed.append  # type: ignore[method-assign]
        modal.action_close()
        assert dismissed == [None]

    def test_action_previous(self) -> None:
        """Переход к предыдущей модели уменьшает индекс."""
        model1 = ModelOption(value="a", label="A")
        model2 = ModelOption(value="b", label="B")
        vm = _make_view_model(models=[model1, model2])
        modal = ModelSelectorModal(vm, session_id="session_1")
        modal._selected_index = 1
        with patch.object(modal, "_update_selection") as update_mock:
            modal.action_previous()
        assert modal._selected_index == 0
        update_mock.assert_called_once()

    def test_action_previous_at_zero(self) -> None:
        """Переход вверх из нулевого индекса не меняет его."""
        vm = _make_view_model(models=[ModelOption(value="a", label="A")])
        modal = ModelSelectorModal(vm, session_id="session_1")
        modal._selected_index = 0
        with patch.object(modal, "_update_selection") as update_mock:
            modal.action_previous()
        assert modal._selected_index == 0
        update_mock.assert_not_called()

    def test_action_previous_no_models(self) -> None:
        """Переход вверх без моделей не падает."""
        vm = _make_view_model()
        modal = ModelSelectorModal(vm, session_id="session_1")
        modal.action_previous()
        assert modal._selected_index == 0

    def test_action_next(self) -> None:
        """Переход к следующей модели увеличивает индекс."""
        model1 = ModelOption(value="a", label="A")
        model2 = ModelOption(value="b", label="B")
        vm = _make_view_model(models=[model1, model2])
        modal = ModelSelectorModal(vm, session_id="session_1")
        with patch.object(modal, "_update_selection") as update_mock:
            modal.action_next()
        assert modal._selected_index == 1
        update_mock.assert_called_once()

    def test_action_next_at_end(self) -> None:
        """Переход вниз из последнего индекса не меняет его."""
        vm = _make_view_model(models=[ModelOption(value="a", label="A")])
        modal = ModelSelectorModal(vm, session_id="session_1")
        modal._selected_index = 0
        with patch.object(modal, "_update_selection") as update_mock:
            modal.action_next()
        assert modal._selected_index == 0
        update_mock.assert_not_called()

    def test_action_next_no_models(self) -> None:
        """Переход вниз без моделей не падает."""
        vm = _make_view_model()
        modal = ModelSelectorModal(vm, session_id="session_1")
        modal.action_next()
        assert modal._selected_index == 0

    def test_action_select(self) -> None:
        """Выбор модели закрывает окно со значением."""
        model = ModelOption(value="openai/gpt-4o", label="GPT-4o")
        vm = _make_view_model(models=[model])
        modal = ModelSelectorModal(vm, session_id="session_1")
        dismissed: list[object] = []
        modal.dismiss = dismissed.append  # type: ignore[method-assign]
        modal.action_select()
        assert dismissed == ["openai/gpt-4o"]

    def test_action_select_index_out_of_range(self) -> None:
        """Выбор с невалидным индексом ничего не делает."""
        vm = _make_view_model()
        modal = ModelSelectorModal(vm, session_id="session_1")
        modal._selected_index = -1
        dismissed: list[object] = []
        modal.dismiss = dismissed.append  # type: ignore[method-assign]
        modal.action_select()
        assert dismissed == []

    def test_on_model_item_selected(self) -> None:
        """Выбор через ModelItem закрывает окно со значением."""
        model = ModelOption(value="openai/gpt-4o", label="GPT-4o")
        vm = _make_view_model()
        modal = ModelSelectorModal(vm, session_id="session_1")
        dismissed: list[object] = []
        modal.dismiss = dismissed.append  # type: ignore[method-assign]
        modal.on_model_item_selected(ModelItem.Selected(model))
        assert dismissed == ["openai/gpt-4o"]

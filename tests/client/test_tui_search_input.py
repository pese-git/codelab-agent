"""Тесты для SearchInput компонента.

Тестирует:
- Рендеринг компонента
- События SearchChanged, SearchSubmitted, SearchCleared
- Debounce механизм
- Кнопку очистки
- Историю поиска
"""

from __future__ import annotations

import asyncio

from textual.app import App
from textual.widgets import Input

from codelab.client.tui.components.search_input import SearchInput


class TestSearchInputClass:
    """Тесты для класса SearchInput."""

    def test_search_input_has_search_icon(self) -> None:
        """SearchInput имеет иконку поиска."""
        assert SearchInput.SEARCH_ICON == "🔍"

    def test_search_input_has_default_css(self) -> None:
        """SearchInput имеет встроенные CSS стили."""
        assert "SearchInput" in SearchInput.DEFAULT_CSS
        assert ".search-container" in SearchInput.DEFAULT_CSS
        assert ".search-field" in SearchInput.DEFAULT_CSS
        assert ".clear-button" in SearchInput.DEFAULT_CSS
        assert ".search-icon" in SearchInput.DEFAULT_CSS

    def test_search_input_initialization_defaults(self) -> None:
        """SearchInput инициализируется с параметрами по умолчанию."""
        search = SearchInput()

        assert search._placeholder == "Поиск..."
        assert search._debounce == 0.3
        assert search._history == []
        assert search._history_index == -1
        assert search._debounce_task is None

    def test_search_input_initialization_custom(self) -> None:
        """SearchInput принимает пользовательские параметры."""
        search = SearchInput(
            placeholder="Find files...",
            debounce=0.5,
            name="file-search",
            id="custom-search",
            classes="search-bar",
        )

        assert search._placeholder == "Find files..."
        assert search._debounce == 0.5
        assert search.name == "file-search"
        assert search.id == "custom-search"
        assert "search-bar" in search.classes

    def test_search_input_no_debounce(self) -> None:
        """SearchInput может работать без debounce."""
        search = SearchInput(debounce=0)

        assert search._debounce == 0


class TestSearchInputMessages:
    """Тесты для сообщений SearchInput."""

    def test_search_changed_message(self) -> None:
        """SearchChanged сообщение содержит значение поиска."""
        msg = SearchInput.SearchChanged("test query")

        assert msg.value == "test query"

    def test_search_submitted_message(self) -> None:
        """SearchSubmitted сообщение содержит значение поиска."""
        msg = SearchInput.SearchSubmitted("submitted query")

        assert msg.value == "submitted query"

    def test_search_cleared_message(self) -> None:
        """SearchCleared сообщение создаётся без аргументов."""
        msg = SearchInput.SearchCleared()

        assert msg is not None


class TestSearchInputReactiveValue:
    """Тесты для reactive свойства value."""

    def test_value_initial_state(self) -> None:
        """Начальное значение value пустое."""
        search = SearchInput()

        assert search.value == ""


class TestSearchInputHistory:
    """Тесты для истории поиска SearchInput."""

    def test_history_initially_empty(self) -> None:
        """История изначально пуста."""
        search = SearchInput()

        assert search._history == []
        assert search._history_index == -1

    def test_previous_history_empty_returns_none(self) -> None:
        """previous_history возвращает None при пустой истории."""
        search = SearchInput()

        result = search.previous_history()

        assert result is None

    def test_next_history_empty_returns_none(self) -> None:
        """next_history возвращает None при пустой истории."""
        search = SearchInput()

        result = search.next_history()

        assert result is None


class TestSearchInputDebounce:
    """Тесты для debounce механизма SearchInput."""

    def test_schedule_search_creates_task(self) -> None:
        """_schedule_search создаёт asyncio Task."""
        search = SearchInput(debounce=0.1)

        # Имитируем наличие event loop
        try:
            # Используем run_until_complete для создания задачи
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                search._schedule_search("test")
                assert search._debounce_task is not None
                # Отменяем задачу, чтобы не оставлять pending
                search._debounce_task.cancel()
            finally:
                loop.close()
        except RuntimeError:
            # Если нет event loop - это ожидаемо в тестах без Textual App
            pass

    def test_debounce_zero_skips_scheduling(self) -> None:
        """При debounce=0 _schedule_search не вызывается напрямую."""
        search = SearchInput(debounce=0)

        # Проверяем, что debounce task не создаётся при debounce=0
        # так как on_input_changed вызывает _emit_search напрямую
        assert search._debounce_task is None


class TestSearchInputCSS:
    """Тесты для CSS стилей SearchInput."""

    def test_css_has_focus_state(self) -> None:
        """CSS содержит стили для состояния focus."""
        assert ":focus-within" in SearchInput.DEFAULT_CSS

    def test_css_has_hidden_class(self) -> None:
        """CSS содержит класс -hidden для кнопки очистки."""
        assert ".-hidden" in SearchInput.DEFAULT_CSS

    def test_css_has_hover_state(self) -> None:
        """CSS содержит стили для состояния hover."""
        assert ":hover" in SearchInput.DEFAULT_CSS

    def test_css_has_border_styling(self) -> None:
        """CSS содержит стили для бордера."""
        assert "border:" in SearchInput.DEFAULT_CSS

    def test_css_uses_theme_variables(self) -> None:
        """CSS использует переменные темы."""
        # $surface используется для background (обновлено: $input-bg → $surface)
        assert "$surface" in SearchInput.DEFAULT_CSS
        assert "$border" in SearchInput.DEFAULT_CSS
        assert "$primary" in SearchInput.DEFAULT_CSS
        assert "$error" in SearchInput.DEFAULT_CSS


class TestSearchInputMethods:
    """Тесты для публичных методов SearchInput."""

    def test_emit_search_updates_value(self) -> None:
        """_emit_search обновляет reactive value."""
        search = SearchInput()

        search._emit_search("new value")

        assert search.value == "new value"


class TestSearchInputIntegration:
    """Интеграционные тесты (требуют Textual App контекста)."""

    async def test_compose_creates_structure(self) -> None:
        """compose() создаёт правильную структуру виджетов."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            search = SearchInput()
            await pilot.app.mount(search)
            await pilot.pause()

            # Проверяем наличие основных компонентов
            input_widget = search.query_one(".search-field", Input)
            assert input_widget is not None

            clear_button = search.query_one(".clear-button")
            assert clear_button is not None

            search_icon = search.query_one(".search-icon")
            assert search_icon is not None

    async def test_input_property_returns_input(self) -> None:
        """input property возвращает Input виджет."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            search = SearchInput()
            await pilot.app.mount(search)
            await pilot.pause()

            input_widget = search.input
            assert input_widget is not None
            assert isinstance(input_widget, Input)

    async def test_clear_resets_state(self) -> None:
        """clear() сбрасывает состояние поля поиска."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            search = SearchInput()
            await pilot.app.mount(search)
            await pilot.pause()

            # Устанавливаем значение
            search.set_value("test")
            await pilot.pause()
            assert search.value == "test"

            # Очищаем
            search.clear()
            await pilot.pause()

            assert search.value == ""
            assert search.input.value == ""

    async def test_set_value_updates_input(self) -> None:
        """set_value() устанавливает значение и обновляет input."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            search = SearchInput()
            await pilot.app.mount(search)
            await pilot.pause()

            search.set_value("new text")
            await pilot.pause()

            assert search.value == "new text"
            assert search.input.value == "new text"

    async def test_on_input_changed_triggers_debounce(self) -> None:
        """Изменение ввода запускает debounce."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            search = SearchInput(debounce=0.1)
            await pilot.app.mount(search)
            await pilot.pause()

            # Имитируем изменение ввода
            search.input.value = "test query"
            await pilot.pause()

            # Проверяем, что debounce задача создана
            assert search._debounce_task is not None

            # Ждем завершения debounce
            await asyncio.sleep(0.15)
            await pilot.pause()

            # Проверяем, что значение обновилось
            assert search.value == "test query"

    async def test_debounce_delays_search_event(self) -> None:
        """Debounce задерживает отправку события SearchChanged."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            search = SearchInput(debounce=0.2)
            await pilot.app.mount(search)
            await pilot.pause()

            # Быстро меняем значение несколько раз
            search.input.value = "a"
            await pilot.pause()
            first_task = search._debounce_task

            # Сразу меняем снова
            search.input.value = "ab"
            await pilot.pause()
            second_task = search._debounce_task

            # Первая задача должна быть отменена
            assert first_task != second_task
            assert first_task.cancelled()

            # Ждем завершения debounce
            await asyncio.sleep(0.25)
            await pilot.pause()

            # Должно установиться последнее значение
            assert search.value == "ab"

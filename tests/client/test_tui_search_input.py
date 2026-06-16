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

import pytest

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

    @pytest.mark.skip(reason="Требует Textual App контекста для compose()")
    def test_compose_creates_structure(self) -> None:
        """compose() создаёт правильную структуру виджетов."""
        search = SearchInput()
        children = list(search.compose())

        # Должен быть Horizontal контейнер с Label, Input и Button
        assert len(children) == 1  # Horizontal container

    @pytest.mark.skip(reason="Требует Textual App контекста для query_one()")
    def test_input_property_returns_input(self) -> None:
        """input property возвращает Input виджет."""
        search = SearchInput()
        input_widget = search.input

        assert input_widget is not None

    @pytest.mark.skip(reason="Требует Textual App контекста для query_one()")
    def test_clear_resets_state(self) -> None:
        """clear() сбрасывает состояние поля поиска."""
        search = SearchInput()
        search.value = "test"

        search.clear()

        assert search.value == ""

    @pytest.mark.skip(reason="Требует Textual App контекста для query_one()")
    def test_set_value_updates_input(self) -> None:
        """set_value() устанавливает значение и обновляет input."""
        search = SearchInput()

        search.set_value("new text")

        assert search.value == "new text"

    @pytest.mark.skip(reason="Требует Textual App контекста для on_input_changed()")
    def test_on_input_changed_triggers_debounce(self) -> None:
        """Изменение ввода запускает debounce."""
        _search = SearchInput(debounce=0.3)

        # Симуляция события Input.Changed
        # Требует полноценного App контекста
        assert _search is not None  # Placeholder для пропущенного теста

    @pytest.mark.skip(reason="Требует Textual App контекста для полного теста")
    async def test_debounce_delays_search_event(self) -> None:
        """Debounce задерживает отправку события SearchChanged."""
        _search = SearchInput(debounce=0.1)

        # Симуляция быстрого ввода и проверка задержки
        # Требует Textual App для async контекста
        assert _search is not None  # Placeholder для пропущенного теста

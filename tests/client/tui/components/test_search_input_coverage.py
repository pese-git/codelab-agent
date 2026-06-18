"""Тесты покрытия для SearchInput компонента.

Проверяют непокрытые строки в:
- SearchInput
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from textual.app import App
from textual.widgets import Button, Input

from codelab.client.tui.components.search_input import SearchInput


class TestSearchInputInit:
    """Тесты инициализации SearchInput."""

    def test_init_defaults(self) -> None:
        """Инициализация со значениями по умолчанию."""
        widget = SearchInput()
        assert widget._placeholder == "Поиск..."
        assert widget._debounce == 0.3
        assert widget._history == []
        assert widget._history_index == -1
        assert widget.id == "search-input"

    def test_init_custom(self) -> None:
        """Инициализация с пользовательскими параметрами."""
        widget = SearchInput(
            placeholder="Найти...",
            debounce=0.5,
            name="search",
            id="custom-search",
            classes="search-field",
        )
        assert widget._placeholder == "Найти..."
        assert widget._debounce == 0.5
        assert widget.name == "search"
        assert widget.id == "custom-search"
        assert "search-field" in widget.classes


class TestSearchInputCompose:
    """Тесты compose и свойств SearchInput."""

    async def test_compose_and_mount(self) -> None:
        """Компонент создаёт Input, Label и Button."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = SearchInput()
            await pilot.app.mount(widget)

            assert widget.input is not None
            assert isinstance(widget.input, Input)
            assert widget.clear_button is not None
            assert isinstance(widget.clear_button, Button)

    async def test_input_and_clear_button_properties(self) -> None:
        """Свойства input и clear_button возвращают виджеты."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = SearchInput()
            await pilot.app.mount(widget)

            assert widget.input.placeholder == "Поиск..."
            assert "clear-button" in widget.clear_button.classes


class TestSearchInputEvents:
    """Тесты обработки событий SearchInput."""

    async def test_on_input_changed_no_debounce(self) -> None:
        """Изменение ввода без debounce сразу отправляет SearchChanged."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = SearchInput(debounce=0.0)
            await pilot.app.mount(widget)

            with patch.object(widget, "post_message") as mock_post:
                event = MagicMock()
                event.value = "hello"
                widget.on_input_changed(event)

            assert widget.value == "hello"
            search_changed_calls = [
                call for call in mock_post.call_args_list
                if isinstance(call[0][0], SearchInput.SearchChanged)
            ]
            assert len(search_changed_calls) == 1
            assert search_changed_calls[0][0][0].value == "hello"
            assert "-hidden" not in widget.clear_button.classes

    async def test_on_input_changed_with_debounce(self) -> None:
        """Изменение ввода с debounce планирует задачу."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = SearchInput(debounce=0.1)
            await pilot.app.mount(widget)

            with patch.object(widget, "_emit_search") as mock_emit:
                with patch("asyncio.sleep", new_callable=AsyncMock):
                    event = MagicMock()
                    event.value = "query"
                    widget.on_input_changed(event)

                    task = widget._debounce_task
                    assert task is not None
                    await task

            mock_emit.assert_called_once_with("query")

    async def test_on_input_submitted_with_value(self) -> None:
        """Подтверждение ввода добавляет в историю и отправляет сообщение."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = SearchInput()
            await pilot.app.mount(widget)

            with patch.object(widget, "post_message") as mock_post:
                event = MagicMock()
                event.value = "  search text  "
                widget.on_input_submitted(event)

            assert widget.value == "search text"
            assert widget._history == ["search text"]
            submitted_calls = [
                call for call in mock_post.call_args_list
                if isinstance(call[0][0], SearchInput.SearchSubmitted)
            ]
            assert len(submitted_calls) == 1
            assert submitted_calls[0][0][0].value == "search text"

    async def test_on_input_submitted_duplicate_not_added(self) -> None:
        """Дублирующееся значение не добавляется в историю."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = SearchInput()
            await pilot.app.mount(widget)

            widget._history = ["same"]
            with patch.object(widget, "post_message"):
                event = MagicMock()
                event.value = "same"
                widget.on_input_submitted(event)

            assert widget._history == ["same"]

    async def test_on_input_submitted_empty(self) -> None:
        """Пустое значение не добавляется в историю."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = SearchInput()
            await pilot.app.mount(widget)

            with patch.object(widget, "post_message") as mock_post:
                event = MagicMock()
                event.value = "   "
                widget.on_input_submitted(event)

            assert widget._history == []
            assert widget.value == ""
            mock_post.assert_called_once()

    async def test_on_input_submitted_cancels_debounce(self) -> None:
        """Подтверждение ввода отменяет задачу debounce."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = SearchInput(debounce=0.1)
            await pilot.app.mount(widget)

            task = asyncio.create_task(asyncio.sleep(1))
            widget._debounce_task = task

            with patch.object(widget, "post_message"):
                event = MagicMock()
                event.value = "text"
                widget.on_input_submitted(event)

            await asyncio.sleep(0)
            assert task.cancelled() or task.done()
            assert widget._debounce_task is None

    async def test_on_button_pressed_clear(self) -> None:
        """Нажатие кнопки очистки вызывает clear."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = SearchInput()
            await pilot.app.mount(widget)
            widget.set_value("query")

            with patch.object(widget, "clear") as mock_clear:
                event = MagicMock()
                event.button.classes = {"clear-button"}
                widget.on_button_pressed(event)

            mock_clear.assert_called_once()

    async def test_on_button_pressed_other_button(self) -> None:
        """Нажатие другой кнопки игнорируется."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = SearchInput()
            await pilot.app.mount(widget)

            with patch.object(widget, "clear") as mock_clear:
                event = MagicMock()
                event.button.classes = {"other-button"}
                widget.on_button_pressed(event)

            mock_clear.assert_not_called()


class TestSearchInputMethods:
    """Тесты методов SearchInput."""

    async def test_schedule_search_cancels_previous(self) -> None:
        """Планирование поиска отменяет предыдущую задачу."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = SearchInput(debounce=0.1)
            await pilot.app.mount(widget)

            first_task = asyncio.create_task(asyncio.sleep(1))
            widget._debounce_task = first_task

            with patch("asyncio.sleep", new_callable=AsyncMock):
                widget._schedule_search("value")

            await asyncio.sleep(0)
            assert first_task.cancelled() or first_task.done()
            assert widget._debounce_task is not None
            assert widget._debounce_task is not first_task
            widget._debounce_task.cancel()

    def test_emit_search(self) -> None:
        """_emit_search обновляет значение и отправляет сообщение."""
        widget = SearchInput()
        with patch.object(widget, "post_message") as mock_post:
            widget._emit_search("abc")

        assert widget.value == "abc"
        mock_post.assert_called_once()
        posted = mock_post.call_args[0][0]
        assert isinstance(posted, SearchInput.SearchChanged)
        assert posted.value == "abc"

    async def test_clear(self) -> None:
        """clear очищает поле и отправляет SearchCleared."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = SearchInput()
            await pilot.app.mount(widget)
            widget.set_value("to clear")

            with patch.object(widget, "post_message") as mock_post:
                widget.clear()

            assert widget.input.value == ""
            assert widget.value == ""
            assert "-hidden" in widget.clear_button.classes
            mock_post.assert_called_once()
            assert isinstance(mock_post.call_args[0][0], SearchInput.SearchCleared)

    async def test_focus_input(self) -> None:
        """focus_input фокусирует поле ввода."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = SearchInput()
            await pilot.app.mount(widget)
            widget.focus_input()
            await pilot.pause()
            assert widget.input.has_focus

    async def test_set_value(self) -> None:
        """set_value устанавливает значение и управляет кнопкой очистки."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = SearchInput()
            await pilot.app.mount(widget)

            widget.set_value("search")
            assert widget.input.value == "search"
            assert widget.value == "search"
            assert "-hidden" not in widget.clear_button.classes

            widget.set_value("")
            assert "-hidden" in widget.clear_button.classes


class TestSearchInputHistory:
    """Тесты навигации по истории SearchInput."""

    async def test_previous_history_empty(self) -> None:
        """previous_history без истории возвращает None."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = SearchInput()
            await pilot.app.mount(widget)
            assert widget.previous_history() is None

    async def test_previous_history_navigation(self) -> None:
        """previous_history перебирает историю назад."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = SearchInput()
            await pilot.app.mount(widget)
            widget._history = ["first", "second", "third"]

            assert widget.previous_history() == "third"
            assert widget.previous_history() == "second"
            assert widget.previous_history() == "first"
            assert widget.previous_history() is None

    async def test_next_history_navigation(self) -> None:
        """next_history перебирает историю вперёд."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = SearchInput()
            await pilot.app.mount(widget)
            widget._history = ["first", "second", "third"]
            widget._history_index = 2

            assert widget.next_history() == "second"
            assert widget.next_history() == "third"

    async def test_next_history_at_top_clears(self) -> None:
        """next_history на вершине истории очищает поле."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = SearchInput()
            await pilot.app.mount(widget)
            widget._history = ["first", "second"]
            widget._history_index = 0
            widget.set_value("first")

            assert widget.next_history() == ""
            assert widget._history_index == -1

    async def test_next_history_no_history(self) -> None:
        """next_history без истории возвращает None."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = SearchInput()
            await pilot.app.mount(widget)
            assert widget.next_history() is None

"""Тесты покрытия для streaming_text компонентов.

Проверяют непокрытые строки в:
- StreamingText
- TypewriterText
- ThinkingIndicator
"""

from __future__ import annotations

from textual.app import App

from codelab.client.tui.components.streaming_text import (
    StreamingText,
    ThinkingIndicator,
    TypewriterText,
)


class TestStreamingText:
    """Тесты для StreamingText."""

    def test_init_defaults(self) -> None:
        """Инициализация с значениями по умолчанию."""
        widget = StreamingText()
        assert widget.text == ""
        assert widget.show_cursor is True
        assert widget.is_streaming is True

    def test_init_custom(self) -> None:
        """Инициализация с параметрами."""
        widget = StreamingText("hello", show_cursor=False, use_markdown=False)
        assert widget.text == "hello"
        assert widget.show_cursor is False

    async def test_compose_and_mount(self) -> None:
        """Компонент создает виджеты контента и курсора."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = StreamingText("initial")
            await pilot.app.mount(widget)
            assert widget._content_widget is not None
            assert widget._cursor_widget is not None

    async def test_compose_without_markdown(self) -> None:
        """Компонент использует Static вместо Markdown."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = StreamingText(use_markdown=False)
            await pilot.app.mount(widget)
            assert widget._content_widget is not None

    async def test_on_mount_starts_cursor(self) -> None:
        """При монтировании запускается анимация курсора."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = StreamingText(show_cursor=True)
            await pilot.app.mount(widget)
            assert widget._cursor_timer is not None

    async def test_toggle_cursor_directly(self) -> None:
        """Прямой вызов _toggle_cursor переключает символ курсора."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = StreamingText(show_cursor=True)
            await pilot.app.mount(widget)

            initial_char = widget._cursor_widget._Static__content
            widget._toggle_cursor()
            new_char = widget._cursor_widget._Static__content
            assert new_char != initial_char

    async def test_on_mount_no_cursor(self) -> None:
        """При выключенном курсоре таймер не запускается."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = StreamingText(show_cursor=False)
            await pilot.app.mount(widget)
            assert widget._cursor_timer is None

    async def test_on_unmount_stops_cursor(self) -> None:
        """При размонтировании останавливается таймер."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = StreamingText()
            await pilot.app.mount(widget)
            assert widget._cursor_timer is not None

            await widget.remove()
            await pilot.pause()
            assert widget._cursor_timer is None

    async def test_toggle_cursor(self) -> None:
        """Переключение видимости курсора."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = StreamingText()
            await pilot.app.mount(widget)

            widget.show_cursor = False
            assert "hidden" in widget._cursor_widget.classes
            assert widget._cursor_timer is None

            widget.show_cursor = True
            assert "hidden" not in widget._cursor_widget.classes
            assert widget._cursor_timer is not None

    async def test_watch_text(self) -> None:
        """Изменение текста обновляет контент."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = StreamingText()
            await pilot.app.mount(widget)

            widget.set_text("new text")
            assert widget.text == "new text"

    async def test_append_text(self) -> None:
        """Добавление текста к существующему."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = StreamingText("hello ")
            await pilot.app.mount(widget)

            widget.append_text("world")
            assert widget.text == "hello world"

    async def test_clear(self) -> None:
        """Очистка текста."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = StreamingText("hello")
            await pilot.app.mount(widget)

            widget.clear()
            assert widget.text == ""

    async def test_finalize(self) -> None:
        """Завершение streaming убирает курсор."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = StreamingText()
            await pilot.app.mount(widget)

            widget.finalize()
            assert widget.is_streaming is False
            assert widget.show_cursor is False


class TestTypewriterText:
    """Тесты для TypewriterText."""

    def test_init(self) -> None:
        """Инициализация с задержкой."""
        widget = TypewriterText(char_delay=0.01)
        assert widget._char_delay == 0.01

    async def test_type_text(self) -> None:
        """Печать текста с эффектом typewriter."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = TypewriterText(char_delay=0.001)
            await pilot.app.mount(widget)

            widget.type_text("hello")
            assert widget._target_text == "hello"
            assert widget.is_streaming is True

    async def test_skip_to_end(self) -> None:
        """Пропуск анимации показывает весь текст."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = TypewriterText(char_delay=0.001)
            await pilot.app.mount(widget)

            widget.type_text("hello world")
            widget.skip_to_end()
            assert widget.text == "hello world"
            assert widget.is_streaming is False

    async def test_stop_typing(self) -> None:
        """Остановка печати останавливает таймер."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = TypewriterText(char_delay=0.001)
            await pilot.app.mount(widget)

            widget.type_text("hello")
            widget._stop_typing()
            assert widget._typing_timer is None

    async def test_type_next_char_completion(self) -> None:
        """Печать последнего символа завершает анимацию."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = TypewriterText(char_delay=0.001)
            await pilot.app.mount(widget)

            widget._target_text = "a"
            widget._current_index = 0
            widget.text = ""
            widget._type_next_char()
            assert widget.text == "a"
            assert widget._current_index == 1

            widget._type_next_char()
            assert widget.is_streaming is False


class TestThinkingIndicator:
    """Тесты для ThinkingIndicator."""

    def test_init(self) -> None:
        """Инициализация с меткой."""
        widget = ThinkingIndicator("Thinking")
        assert widget._label == "Thinking"

    async def test_mount_and_unmount(self) -> None:
        """Монтирование запускает анимацию, размонтирование останавливает."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = ThinkingIndicator("Loading")
            await pilot.app.mount(widget)
            assert widget._timer is not None

            # on_unmount останавливает таймер
            widget.on_unmount()

    async def test_next_frame(self) -> None:
        """Смена кадра анимации."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = ThinkingIndicator("Loading")
            await pilot.app.mount(widget)

            initial_index = widget._frame_index
            widget._next_frame()
            assert widget._frame_index != initial_index

    async def test_set_label(self) -> None:
        """Установка новой метки обновляет отображение."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            widget = ThinkingIndicator("Old")
            await pilot.app.mount(widget)

            widget.set_label("New")
            assert widget._label == "New"
            assert "New" in widget._Static__content

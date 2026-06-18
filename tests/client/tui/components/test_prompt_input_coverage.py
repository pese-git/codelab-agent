"""Тесты покрытия для PromptInput компонента.

Проверяют непокрытые строки в:
- PromptTextArea
- PromptInput
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from textual.app import App

from codelab.client.presentation.observable import Observable
from codelab.client.tui.components.prompt_input import PromptInput, PromptTextArea


class FakeChatViewModel:
    """Фейковый ChatViewModel для тестов PromptInput."""

    def __init__(self) -> None:
        self.is_streaming: Observable[bool] = Observable(False)


class TestPromptTextArea:
    """Тесты для PromptTextArea."""

    async def test_ctrl_enter_submits(self) -> None:
        """Ctrl+Enter находит родительский PromptInput и вызывает submit."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            prompt_input = PromptInput(chat_vm)
            await pilot.app.mount(prompt_input)
            prompt_input._text_area.focus()

            prompt_input.action_submit = MagicMock()
            await pilot.press("ctrl+enter")
            prompt_input.action_submit.assert_called_once()

    async def test_ctrl_j_submits(self) -> None:
        """Ctrl+J находит родительский PromptInput и вызывает submit."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            prompt_input = PromptInput(chat_vm)
            await pilot.app.mount(prompt_input)
            prompt_input._text_area.focus()

            prompt_input.action_submit = MagicMock()
            await pilot.press("ctrl+j")
            prompt_input.action_submit.assert_called_once()

    async def test_other_key_calls_super(self) -> None:
        """Обычная клавиша передается родительскому обработчику."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            prompt_input = PromptInput(chat_vm)
            await pilot.app.mount(prompt_input)
            prompt_input._text_area.focus()
            # Не должно вызывать ошибок
            await pilot.press("a")

    async def test_key_without_prompt_input_parent(self) -> None:
        """Если нет PromptInput в родителях, вызывается super."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            text_area = PromptTextArea()
            await pilot.app.mount(text_area)
            text_area.focus()
            # Не должно вызывать ошибок
            await pilot.press("ctrl+enter")


class TestPromptInput:
    """Тесты для PromptInput."""

    def test_text_property_without_text_area(self) -> None:
        """text возвращает пустую строку если text_area не смонтирован."""
        chat_vm = FakeChatViewModel()
        prompt_input = PromptInput(chat_vm)
        prompt_input._text_area = None
        assert prompt_input.text == ""

    def test_text_setter_without_text_area(self) -> None:
        """text setter ничего не делает если text_area не смонтирован."""
        chat_vm = FakeChatViewModel()
        prompt_input = PromptInput(chat_vm)
        prompt_input._text_area = None
        prompt_input.text = "test"

    async def test_compose_and_mount(self) -> None:
        """Компонент создает поле ввода и кнопки после монтирования."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            prompt_input = PromptInput(chat_vm)
            await pilot.app.mount(prompt_input)

            assert prompt_input._text_area is not None
            assert prompt_input._submit_button is not None
            assert prompt_input._stop_button is not None
            assert prompt_input._stop_button.display is False

    async def test_text_setter_and_getter(self) -> None:
        """Свойство text устанавливает и возвращает текст."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            prompt_input = PromptInput(chat_vm)
            await pilot.app.mount(prompt_input)

            prompt_input.text = "test prompt"
            assert prompt_input.text == "test prompt"

    async def test_set_active_session(self) -> None:
        """Переключение активной сессии сбрасывает историю."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            prompt_input = PromptInput(chat_vm)
            await pilot.app.mount(prompt_input)

            prompt_input.set_active_session("sess_1")
            assert prompt_input._active_session_id == "sess_1"
            assert prompt_input._history_index is None
            assert prompt_input._draft_text == ""

    async def test_remember_prompt_empty(self) -> None:
        """Пустой prompt не сохраняется в историю."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            prompt_input = PromptInput(chat_vm)
            await pilot.app.mount(prompt_input)

            prompt_input.set_active_session("sess_1")
            prompt_input.remember_prompt("   ")
            assert prompt_input._active_history() == []

    async def test_remember_prompt_duplicate(self) -> None:
        """Дублирующий prompt не сохраняется."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            prompt_input = PromptInput(chat_vm)
            await pilot.app.mount(prompt_input)

            prompt_input.set_active_session("sess_1")
            prompt_input.remember_prompt("hello")
            prompt_input.remember_prompt("hello")
            assert prompt_input._active_history() == ["hello"]

    async def test_remember_prompt_trims_history(self) -> None:
        """История обрезается до 100 записей."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            prompt_input = PromptInput(chat_vm)
            await pilot.app.mount(prompt_input)

            prompt_input.set_active_session("sess_1")
            for i in range(102):
                prompt_input.remember_prompt(f"prompt_{i}")

            assert len(prompt_input._active_history()) == 100
            assert prompt_input._active_history()[0] == "prompt_2"

    async def test_action_submit_empty(self) -> None:
        """Пустой текст не отправляет сообщение."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            prompt_input = PromptInput(chat_vm)
            await pilot.app.mount(prompt_input)

            prompt_input.text = "   "
            with patch.object(prompt_input, "post_message") as mock_post:
                prompt_input.action_submit()
            mock_post.assert_not_called()

    async def test_action_submit_posts_submitted(self) -> None:
        """Не пустой текст отправляет Submitted сообщение."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            prompt_input = PromptInput(chat_vm)
            await pilot.app.mount(prompt_input)

            prompt_input.text = "hello"
            with patch.object(prompt_input, "post_message") as mock_post:
                prompt_input.action_submit()

            mock_post.assert_called_once()
            call_args = mock_post.call_args[0][0]
            assert isinstance(call_args, PromptInput.Submitted)
            assert call_args.text == "hello"

    async def test_action_history_previous_empty(self) -> None:
        """history_previous без истории ничего не делает."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            prompt_input = PromptInput(chat_vm)
            await pilot.app.mount(prompt_input)

            prompt_input.action_history_previous()
            assert prompt_input.text == ""

    async def test_action_history_previous_and_next(self) -> None:
        """history_previous/next перебирают историю и черновик."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            prompt_input = PromptInput(chat_vm)
            await pilot.app.mount(prompt_input)

            prompt_input.set_active_session("sess_1")
            prompt_input.remember_prompt("first")
            prompt_input.remember_prompt("second")

            prompt_input.text = "draft"
            prompt_input.action_history_previous()
            assert prompt_input.text == "second"

            prompt_input.action_history_previous()
            assert prompt_input.text == "first"

            prompt_input.action_history_next()
            assert prompt_input.text == "second"

            prompt_input.action_history_next()
            assert prompt_input.text == "draft"

    async def test_action_history_next_no_history(self) -> None:
        """history_next без истории или индекса ничего не делает."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            prompt_input = PromptInput(chat_vm)
            await pilot.app.mount(prompt_input)

            prompt_input.action_history_next()
            assert prompt_input.text == ""

    async def test_on_button_pressed_submit(self) -> None:
        """Нажатие submit-button вызывает action_submit."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            prompt_input = PromptInput(chat_vm)
            await pilot.app.mount(prompt_input)

            prompt_input.text = "submit text"
            with patch.object(prompt_input, "post_message") as mock_post:
                event = MagicMock()
                event.button = prompt_input._submit_button
                prompt_input.on_button_pressed(event)

            mock_post.assert_called_once()
            call_args = mock_post.call_args[0][0]
            assert isinstance(call_args, PromptInput.Submitted)

    async def test_on_button_pressed_stop(self) -> None:
        """Нажатие stop-button отправляет Cancelled сообщение."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            prompt_input = PromptInput(chat_vm)
            await pilot.app.mount(prompt_input)

            with patch.object(prompt_input, "post_message") as mock_post:
                event = MagicMock()
                event.button = prompt_input._stop_button
                prompt_input.on_button_pressed(event)

            mock_post.assert_called_once()
            call_args = mock_post.call_args[0][0]
            assert isinstance(call_args, PromptInput.Cancelled)
            assert prompt_input._stop_button.display is False
            assert prompt_input._submit_button.display is True

    async def test_on_button_pressed_unknown(self) -> None:
        """Нажатие неизвестной кнопки ничего не делает."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            prompt_input = PromptInput(chat_vm)
            await pilot.app.mount(prompt_input)

            with patch.object(prompt_input, "post_message") as mock_post:
                event = MagicMock()
                event.button = MagicMock()
                event.button.id = "unknown-button"
                prompt_input.on_button_pressed(event)
            mock_post.assert_not_called()

    async def test_on_streaming_changed(self) -> None:
        """Изменение is_streaming переключает кнопки и блокирует поле."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            prompt_input = PromptInput(chat_vm)
            await pilot.app.mount(prompt_input)

            chat_vm.is_streaming.value = True
            assert prompt_input._text_area.disabled is True
            assert prompt_input._submit_button.display is False
            assert prompt_input._stop_button.display is True

            chat_vm.is_streaming.value = False
            assert prompt_input._text_area.disabled is False
            assert prompt_input._submit_button.display is True
            assert prompt_input._stop_button.display is False

    async def test_on_streaming_changed_before_mount(self) -> None:
        """Изменение is_streaming до монтирования не вызывает ошибок."""
        chat_vm = FakeChatViewModel()
        prompt_input = PromptInput(chat_vm)
        chat_vm.is_streaming.value = True
        assert prompt_input._text_area is None

    def test_active_history_default_session(self) -> None:
        """История создается для сессии по умолчанию."""
        chat_vm = FakeChatViewModel()
        prompt_input = PromptInput(chat_vm)
        assert prompt_input._active_history() == []

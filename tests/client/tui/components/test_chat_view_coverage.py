"""Тесты покрытия для ChatView компонента.

Проверяют непокрытые строки в:
- ChatView
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from textual.app import App

from codelab.client.messages import PermissionOption, PermissionToolCall
from codelab.client.presentation.observable import Observable
from codelab.client.presentation.permission_view_model import PermissionViewModel
from codelab.client.tui.components.chat_view import ChatView


class FakeChatViewModel:
    """Фейковый ChatViewModel для тестов ChatView."""

    def __init__(self) -> None:
        self.messages: Observable[list[object]] = Observable([])
        self.tool_calls: Observable[list[object]] = Observable([])
        self.is_streaming: Observable[bool] = Observable(False)
        self.streaming_text: Observable[str] = Observable("")


class TestChatView:
    """Тесты для ChatView."""

    async def test_init_without_permission_vm(self) -> None:
        """Инициализация без PermissionViewModel."""
        chat_vm = FakeChatViewModel()
        chat_view = ChatView(chat_vm)
        assert chat_view._permission_manager is None

    async def test_init_with_permission_vm(self) -> None:
        """Инициализация с PermissionViewModel создает менеджер."""
        chat_vm = FakeChatViewModel()
        permission_vm = PermissionViewModel()
        chat_view = ChatView(chat_vm, permission_vm=permission_vm)
        assert chat_view._permission_manager is not None

    async def test_compose_and_mount(self) -> None:
        """Компонент рендерится и монтируется."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            chat_view = ChatView(chat_vm)
            await pilot.app.mount(chat_view)

            assert chat_view._mounted
            assert chat_view._content_container is not None
            assert chat_view._loading_indicator is not None

    async def test_on_messages_changed(self) -> None:
        """Изменение сообщений обновляет отображение."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            chat_view = ChatView(chat_vm)
            await pilot.app.mount(chat_view)

            chat_vm.messages.value = [{"role": "user", "content": "hello"}]
            assert chat_view._content_container is not None

    async def test_on_tool_calls_changed(self) -> None:
        """Изменение tool calls обновляет отображение."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            chat_view = ChatView(chat_vm)
            await pilot.app.mount(chat_view)

            chat_vm.tool_calls.value = [{"toolCallId": "1", "title": "test"}]

    async def test_on_streaming_changed(self) -> None:
        """Изменение статуса streaming обновляет индикатор."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            chat_view = ChatView(chat_vm)
            await pilot.app.mount(chat_view)

            chat_vm.is_streaming.value = True
            assert chat_view._loading_indicator.visible is True

            chat_vm.is_streaming.value = False
            assert chat_view._loading_indicator.visible is False

    async def test_on_streaming_text_changed(self) -> None:
        """Изменение streaming текста обновляет отображение."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            chat_view = ChatView(chat_vm)
            await pilot.app.mount(chat_view)

            chat_vm.is_streaming.value = True
            chat_vm.streaming_text.value = "streaming..."

    async def test_update_display_not_mounted(self) -> None:
        """_update_display без монтирования возвращает управление."""
        chat_vm = FakeChatViewModel()
        chat_view = ChatView(chat_vm)
        chat_view._mounted = False
        chat_view._update_display()

    async def test_update_display_no_chat_vm(self) -> None:
        """_update_display без chat_vm возвращает управление."""
        chat_vm = FakeChatViewModel()
        chat_view = ChatView(chat_vm)
        chat_view.chat_vm = None
        chat_view._mounted = True
        chat_view._content_container = MagicMock()
        chat_view._update_display()

    async def test_update_display_with_messages(self) -> None:
        """_update_display отображает сообщения."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            chat_view = ChatView(chat_vm)
            await pilot.app.mount(chat_view)

            chat_vm.messages.value = [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
                {"role": "system", "content": "system msg"},
                {"role": "error", "content": "error msg"},
            ]

    async def test_update_display_with_streaming_text(self) -> None:
        """_update_display отображает streaming текст."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            chat_view = ChatView(chat_vm)
            await pilot.app.mount(chat_view)

            chat_vm.is_streaming.value = True
            chat_vm.streaming_text.value = "streaming text"

    async def test_update_display_with_tool_calls(self) -> None:
        """_update_display отображает tool calls."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            chat_view = ChatView(chat_vm)
            await pilot.app.mount(chat_view)

            chat_vm.tool_calls.value = [{"toolCallId": "1", "title": "test"}]

    async def test_render_message_unknown_type(self) -> None:
        """_render_message обрабатывает неизвестный тип сообщения."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            chat_view = ChatView(chat_vm)
            await pilot.app.mount(chat_view)

            chat_view._render_message("plain string message")

    async def test_render_message_no_role(self) -> None:
        """_render_message обрабатывает сообщение без role."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            chat_view = ChatView(chat_vm)
            await pilot.app.mount(chat_view)

            chat_view._render_message({"type": "unknown", "content": "content"})

    async def test_render_message_no_content_container(self) -> None:
        """_render_message без контейнера возвращает управление."""
        chat_vm = FakeChatViewModel()
        chat_view = ChatView(chat_vm)
        chat_view._content_container = None
        chat_view._render_message({"role": "user", "content": "test"})

    async def test_render_streaming_text_no_container(self) -> None:
        """_render_streaming_text без контейнера возвращает управление."""
        chat_vm = FakeChatViewModel()
        chat_view = ChatView(chat_vm)
        chat_view._content_container = None
        chat_view._render_streaming_text("test")

    async def test_render_tool_call_no_container(self) -> None:
        """_render_tool_call без контейнера возвращает управление."""
        chat_vm = FakeChatViewModel()
        chat_view = ChatView(chat_vm)
        chat_view._content_container = None
        chat_view._render_tool_call("test")

    async def test_clear_messages(self) -> None:
        """Очистка сообщений."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            chat_view = ChatView(chat_vm)
            await pilot.app.mount(chat_view)

            chat_vm.messages.value = [{"role": "user", "content": "hello"}]
            chat_view.clear_messages()
            assert chat_vm.messages.value == []

    async def test_add_user_message(self) -> None:
        """Добавление пользовательского сообщения."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            chat_view = ChatView(chat_vm)
            await pilot.app.mount(chat_view)

            chat_view.add_user_message("user msg")
            assert len(chat_vm.messages.value) == 1
            assert chat_vm.messages.value[0]["role"] == "user"

    async def test_add_system_message(self) -> None:
        """Добавление системного сообщения."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            chat_view = ChatView(chat_vm)
            await pilot.app.mount(chat_view)

            chat_view.add_system_message("system msg")
            assert len(chat_vm.messages.value) == 1
            assert chat_vm.messages.value[0]["role"] == "system"

    async def test_append_agent_chunk(self) -> None:
        """Добавление chunk от агента."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            chat_view = ChatView(chat_vm)
            await pilot.app.mount(chat_view)

            chat_view.append_agent_chunk("chunk1")
            assert chat_vm.is_streaming.value is True
            assert chat_vm.streaming_text.value == "chunk1"

            chat_view.append_agent_chunk("chunk2")
            assert chat_vm.streaming_text.value == "chunk1chunk2"

    async def test_finish_agent_message(self) -> None:
        """Завершение агентского сообщения сохраняет в историю."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            chat_view = ChatView(chat_vm)
            await pilot.app.mount(chat_view)

            chat_view.append_agent_chunk("response")
            chat_view.finish_agent_message()

            assert chat_vm.is_streaming.value is False
            assert chat_vm.streaming_text.value == ""
            assert len(chat_vm.messages.value) == 1
            assert chat_vm.messages.value[0]["role"] == "assistant"

    async def test_finish_agent_message_empty(self) -> None:
        """Завершение пустого агентского сообщения не добавляет в историю."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            chat_view = ChatView(chat_vm)
            await pilot.app.mount(chat_view)

            chat_view.finish_agent_message()
            assert len(chat_vm.messages.value) == 0

    async def test_show_permission_request_with_manager(self) -> None:
        """show_permission_request делегирует менеджеру."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            permission_vm = PermissionViewModel()
            chat_view = ChatView(chat_vm, permission_vm=permission_vm)
            await pilot.app.mount(chat_view)

            tool_call = PermissionToolCall(toolCallId="call_1", title="Run")
            options = [PermissionOption(optionId="allow", name="Allow", kind="allow_once")]
            callback = MagicMock()
            manager = chat_view._permission_manager

            with patch.object(manager, "show_permission_request") as mock_show:
                chat_view.show_permission_request("req_1", tool_call, options, callback)
                mock_show.assert_called_once_with("req_1", tool_call, options, callback)

    async def test_show_permission_request_without_manager(self) -> None:
        """show_permission_request без менеджера логирует предупреждение."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            chat_view = ChatView(chat_vm)
            await pilot.app.mount(chat_view)

            tool_call = PermissionToolCall(toolCallId="call_1", title="Run")
            options = [PermissionOption(optionId="allow", name="Allow", kind="allow_once")]
            callback = MagicMock()

            chat_view.show_permission_request("req_1", tool_call, options, callback)

    async def test_hide_permission_request(self) -> None:
        """hide_permission_request делегирует менеджеру."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            permission_vm = PermissionViewModel()
            chat_view = ChatView(chat_vm, permission_vm=permission_vm)
            await pilot.app.mount(chat_view)
            manager = chat_view._permission_manager

            with patch.object(manager, "hide_permission_request") as mock_hide:
                chat_view.hide_permission_request()
                mock_hide.assert_called_once()

    async def test_hide_permission_request_without_manager(self) -> None:
        """hide_permission_request без менеджера не вызывает ошибок."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            chat_vm = FakeChatViewModel()
            chat_view = ChatView(chat_vm)
            await pilot.app.mount(chat_view)

            chat_view.hide_permission_request()

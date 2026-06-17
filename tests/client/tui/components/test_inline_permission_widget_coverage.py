"""Тесты для покрытия inline_permission_widget.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from textual.app import App

from codelab.client.messages import PermissionOption, PermissionToolCall
from codelab.client.presentation.permission_view_model import PermissionViewModel
from codelab.client.tui.components.inline_permission_widget import (
    InlinePermissionWidget,
)


class TestInlinePermissionWidgetInit:
    """Тесты инициализации InlinePermissionWidget."""

    def test_init_stores_arguments(self) -> None:
        """Инициализация сохраняет все параметры и строит индекс опций."""
        vm = PermissionViewModel()
        tool_call = PermissionToolCall(toolCallId="call_1", title="Run", kind="execute")
        options = [
            PermissionOption(optionId="allow", name="Allow", kind="allow_once"),
        ]
        on_choice = MagicMock()

        widget = InlinePermissionWidget(
            permission_vm=vm,
            request_id="req_1",
            tool_call=tool_call,
            options=options,
            on_choice=on_choice,
        )

        assert widget.permission_vm is vm
        assert widget._request_id == "req_1"
        assert widget._tool_call is tool_call
        assert widget._options == options
        assert widget._on_choice is on_choice
        assert widget._option_by_id == {"allow": options[0]}
        assert widget.id == "permission_widget_req_1"


class TestInlinePermissionWidgetCompose:
    """Тесты рендеринга виджета."""

    async def test_compose_with_description(self) -> None:
        """При наличии сообщения рендерится описание."""
        vm = PermissionViewModel()
        vm.show_request("execute", "/tmp", "Allow this command?")
        tool_call = PermissionToolCall(toolCallId="call_1", title="Run", kind="execute")
        options = [
            PermissionOption(optionId="allow", name="Allow", kind="allow_once"),
        ]
        widget = InlinePermissionWidget(
            permission_vm=vm,
            request_id="req_1",
            tool_call=tool_call,
            options=options,
            on_choice=MagicMock(),
        )

        class TestApp(App):
            def compose(self):
                yield widget

        async with TestApp().run_test() as _:
            assert widget.query_one("#permission-header")
            assert widget.query_one("#permission-description")
            assert widget.query_one("#permission-buttons")
            assert widget.query_one("#permission-allow")
            assert widget.query_one("#permission-cancel")

    async def test_compose_without_description(self) -> None:
        """Без сообщения описание не рендерится."""
        vm = PermissionViewModel()
        tool_call = PermissionToolCall(toolCallId="call_1", title="Run", kind="execute")
        options = [
            PermissionOption(optionId="allow", name="Allow", kind="allow_once"),
        ]
        widget = InlinePermissionWidget(
            permission_vm=vm,
            request_id="req_1",
            tool_call=tool_call,
            options=options,
            on_choice=MagicMock(),
        )

        class TestApp(App):
            def compose(self):
                yield widget

        async with TestApp().run_test() as _:
            assert widget.query_one("#permission-header")
            assert len(widget.query("#permission-description")) == 0
            assert widget.query_one("#permission-buttons")

    async def test_header_contains_tool_call_info(self) -> None:
        """Заголовок содержит kind и title tool call."""
        vm = PermissionViewModel()
        tool_call = PermissionToolCall(toolCallId="call_1", title="Edit file", kind="edit")
        options = [
            PermissionOption(optionId="allow", name="Allow", kind="allow_once"),
        ]
        widget = InlinePermissionWidget(
            permission_vm=vm,
            request_id="req_1",
            tool_call=tool_call,
            options=options,
            on_choice=MagicMock(),
        )

        class TestApp(App):
            def compose(self):
                yield widget

        async with TestApp().run_test() as _:
            header = widget.query_one("#permission-header")
            header_text = str(header.render())
            assert "edit" in header_text
            assert "Edit file" in header_text


class TestInlinePermissionWidgetButtons:
    """Тесты нажатий кнопок разрешения."""

    def _make_widget(self) -> tuple[InlinePermissionWidget, MagicMock, PermissionViewModel]:
        """Создает виджет с двумя опциями и моком callback."""
        vm = PermissionViewModel()
        vm.show_request("execute", "/tmp", "Allow?")
        tool_call = PermissionToolCall(toolCallId="call_1", title="Run", kind="execute")
        options = [
            PermissionOption(optionId="allow", name="Allow", kind="allow_once"),
            PermissionOption(optionId="deny", name="Deny", kind="reject_once"),
        ]
        on_choice = MagicMock()
        widget = InlinePermissionWidget(
            permission_vm=vm,
            request_id="req_1",
            tool_call=tool_call,
            options=options,
            on_choice=on_choice,
        )
        widget.remove = MagicMock()
        return widget, on_choice, vm

    def _press(self, widget: InlinePermissionWidget, button_id: str) -> None:
        """Эмулирует нажатие кнопки."""
        event = MagicMock()
        event.button.id = button_id
        widget.on_button_pressed(event)

    def test_cancel_button(self) -> None:
        """Нажатие Cancel вызывает callback и скрывает виджет."""
        widget, on_choice, vm = self._make_widget()
        self._press(widget, "permission-cancel")

        on_choice.assert_called_once_with("req_1", "cancelled")
        assert vm.is_visible.value is False
        widget.remove.assert_called_once()

    def test_option_button(self) -> None:
        """Нажатие опции вызывает callback с её id."""
        widget, on_choice, vm = self._make_widget()
        self._press(widget, "permission-allow")

        on_choice.assert_called_once_with("req_1", "allow")
        assert vm.is_visible.value is False
        widget.remove.assert_called_once()

    def test_unknown_option_id_ignored(self) -> None:
        """Нажатие неизвестной опции игнорируется."""
        widget, on_choice, vm = self._make_widget()
        self._press(widget, "permission-unknown")

        on_choice.assert_not_called()
        assert vm.is_visible.value is True
        widget.remove.assert_not_called()

    def test_non_permission_button_ignored(self) -> None:
        """Кнопка без префикса permission- игнорируется."""
        widget, on_choice, vm = self._make_widget()
        self._press(widget, "some-other-button")

        on_choice.assert_not_called()
        assert vm.is_visible.value is True
        widget.remove.assert_not_called()

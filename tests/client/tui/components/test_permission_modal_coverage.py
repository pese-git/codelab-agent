"""Тесты покрытия для permission_modal.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from textual.app import App
from textual.widgets import Button, Static

from codelab.client.messages import PermissionOption
from codelab.client.presentation.permission_view_model import PermissionViewModel
from codelab.client.tui.components.permission_modal import PermissionModal


class TestPermissionModal:
    """Тесты для PermissionModal."""

    def test_init_default(self) -> None:
        """Инициализация с ViewModel по умолчанию."""
        vm = PermissionViewModel()
        modal = PermissionModal(permission_vm=vm)
        assert modal.permission_vm is vm
        assert modal._request_id is None
        assert modal._title == ""
        assert modal._options == []
        assert modal._on_choice is None
        assert len(modal._unsubscribers) == 3

    def test_init_with_options(self) -> None:
        """Инициализация с опциями и callback."""
        vm = PermissionViewModel()
        options = [
            PermissionOption(optionId="allow_once", name="Allow once", kind="allow_once"),
            PermissionOption(optionId="reject_once", name="Reject once", kind="reject_once"),
        ]
        callback = MagicMock()
        modal = PermissionModal(
            permission_vm=vm,
            request_id="req_1",
            title="Test",
            options=options,
            on_choice=callback,
        )
        assert modal._request_id == "req_1"
        assert modal._title == "Test"
        assert modal._options == options
        assert modal._on_choice is callback
        assert modal._option_by_id == {
            "allow_once": options[0],
            "reject_once": options[1],
        }

    async def test_compose(self) -> None:
        """compose создает заголовок, кнопки опций и кнопку отмены."""

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = PermissionViewModel()
            options = [
                PermissionOption(optionId="allow_once", name="Allow once", kind="allow_once"),
            ]
            modal = PermissionModal(permission_vm=vm, options=options)
            await pilot.app.mount(modal)
            assert modal.query_one("#permission-title", Static)
            assert modal.query_one("#permission-allow_once", Button)
            assert modal.query_one("#permission-cancel", Button)

    async def test_on_mount_focus(self) -> None:
        """При монтировании фокус ставится на безопасную кнопку."""
        vm = PermissionViewModel()
        options = [
            PermissionOption(optionId="allow_once", name="Allow", kind="allow_once"),
            PermissionOption(optionId="reject_once", name="Reject", kind="reject_once"),
        ]
        modal = PermissionModal(permission_vm=vm, options=options)

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.app.push_screen(modal)
            await pilot.pause()
            focused = app.screen.focused
            assert focused is not None
            assert focused.id == "permission-reject_once"

    def test_on_unmount_unsubscribes(self) -> None:
        """При размонтировании отписываются от ViewModel."""
        vm = PermissionViewModel()
        modal = PermissionModal(permission_vm=vm)
        unsub_mocks = [MagicMock() for _ in modal._unsubscribers]
        modal._unsubscribers = unsub_mocks
        modal.on_unmount()
        for unsub in unsub_mocks:
            unsub.assert_called_once()

    async def test_view_model_changes_update_title(self) -> None:
        """Изменения ViewModel обновляют заголовок."""
        vm = PermissionViewModel()
        options = [
            PermissionOption(optionId="allow_once", name="Allow", kind="allow_once"),
        ]
        modal = PermissionModal(permission_vm=vm, options=options)

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            await pilot.app.push_screen(modal)
            await pilot.pause()
            vm.permission_type.value = "file_read"
            vm.resource.value = "/tmp/file.txt"
            vm.message.value = "Read needed"
            title = modal.query_one("#permission-title", Static)
            assert "file_read: /tmp/file.txt - Read needed" in str(title.render())

    def test_on_button_pressed_option(self) -> None:
        """Нажатие кнопки опции вызывает callback и dismiss."""
        vm = PermissionViewModel()
        options = [
            PermissionOption(optionId="allow_once", name="Allow", kind="allow_once"),
        ]
        callback = MagicMock()
        modal = PermissionModal(
            permission_vm=vm,
            request_id="req_1",
            options=options,
            on_choice=callback,
        )
        dismissed: list[object] = []
        modal.dismiss = dismissed.append  # type: ignore[method-assign]
        vm.hide = MagicMock()  # type: ignore[method-assign]
        button = Button("Allow", id="permission-allow_once")
        modal.on_button_pressed(Button.Pressed(button))
        callback.assert_called_once_with("req_1", "allow_once")
        vm.hide.assert_called_once()
        assert dismissed == ["allow_once"]

    def test_on_button_pressed_cancel(self) -> None:
        """Нажатие Cancel вызывает callback с cancelled и dismiss(None)."""
        vm = PermissionViewModel()
        callback = MagicMock()
        modal = PermissionModal(
            permission_vm=vm,
            request_id="req_1",
            on_choice=callback,
        )
        dismissed: list[object] = []
        modal.dismiss = dismissed.append  # type: ignore[method-assign]
        vm.hide = MagicMock()  # type: ignore[method-assign]
        button = Button("Cancel", id="permission-cancel")
        modal.on_button_pressed(Button.Pressed(button))
        callback.assert_called_once_with("req_1", "cancelled")
        vm.hide.assert_called_once()
        assert dismissed == [None]

    def test_on_button_pressed_unknown(self) -> None:
        """Неизвестная кнопка не вызывает dismiss."""
        vm = PermissionViewModel()
        modal = PermissionModal(permission_vm=vm)
        dismissed: list[object] = []
        modal.dismiss = dismissed.append  # type: ignore[method-assign]
        button = Button("?", id="permission-unknown")
        modal.on_button_pressed(Button.Pressed(button))
        assert dismissed == []

    def test_action_cancel(self) -> None:
        """action_cancel вызывает callback и dismiss(None)."""
        vm = PermissionViewModel()
        callback = MagicMock()
        modal = PermissionModal(
            permission_vm=vm,
            request_id="req_1",
            on_choice=callback,
        )
        dismissed: list[object] = []
        modal.dismiss = dismissed.append  # type: ignore[method-assign]
        modal.action_cancel()
        callback.assert_called_once_with("req_1", "cancelled")
        assert dismissed == [None]

    def test_action_allow_once(self) -> None:
        """action_allow_once выбирает allow опцию."""
        vm = PermissionViewModel()
        options = [
            PermissionOption(optionId="allow_once", name="Allow", kind="allow_once"),
        ]
        callback = MagicMock()
        modal = PermissionModal(
            permission_vm=vm,
            request_id="req_1",
            options=options,
            on_choice=callback,
        )
        dismissed: list[object] = []
        modal.dismiss = dismissed.append  # type: ignore[method-assign]
        modal.action_allow_once()
        callback.assert_called_once_with("req_1", "allow_once")
        assert dismissed == ["allow_once"]

    def test_action_allow_once_falls_back_to_allow_always(self) -> None:
        """action_allow_once выбирает allow_always если allow_once нет."""
        vm = PermissionViewModel()
        options = [
            PermissionOption(optionId="allow_always", name="Always", kind="allow_always"),
        ]
        callback = MagicMock()
        modal = PermissionModal(
            permission_vm=vm,
            request_id="req_1",
            options=options,
            on_choice=callback,
        )
        dismissed: list[object] = []
        modal.dismiss = dismissed.append  # type: ignore[method-assign]
        modal.action_allow_once()
        callback.assert_called_once_with("req_1", "allow_always")

    def test_action_reject_once(self) -> None:
        """action_reject_once выбирает reject опцию."""
        vm = PermissionViewModel()
        options = [
            PermissionOption(optionId="reject_once", name="Reject", kind="reject_once"),
        ]
        callback = MagicMock()
        modal = PermissionModal(
            permission_vm=vm,
            request_id="req_1",
            options=options,
            on_choice=callback,
        )
        dismissed: list[object] = []
        modal.dismiss = dismissed.append  # type: ignore[method-assign]
        modal.action_reject_once()
        callback.assert_called_once_with("req_1", "reject_once")
        assert dismissed == ["reject_once"]

    def test_action_reject_once_falls_back_to_reject_always(self) -> None:
        """action_reject_once выбирает reject_always если reject_once нет."""
        vm = PermissionViewModel()
        options = [
            PermissionOption(optionId="reject_always", name="Always", kind="reject_always"),
        ]
        callback = MagicMock()
        modal = PermissionModal(
            permission_vm=vm,
            request_id="req_1",
            options=options,
            on_choice=callback,
        )
        dismissed: list[object] = []
        modal.dismiss = dismissed.append  # type: ignore[method-assign]
        modal.action_reject_once()
        callback.assert_called_once_with("req_1", "reject_always")

    def test_action_allow_once_no_option(self) -> None:
        """action_allow_once без allow опций dismiss(None)."""
        vm = PermissionViewModel()
        callback = MagicMock()
        modal = PermissionModal(
            permission_vm=vm,
            request_id="req_1",
            on_choice=callback,
        )
        dismissed: list[object] = []
        modal.dismiss = dismissed.append  # type: ignore[method-assign]
        modal.action_allow_once()
        callback.assert_not_called()
        assert dismissed == [None]

    def test_on_key_allows_navigation(self) -> None:
        """on_key пропускает навигационные клавиши."""
        from textual import events

        vm = PermissionViewModel()
        modal = PermissionModal(permission_vm=vm)

        for key in {"up", "down", "tab", "shift+tab", "enter"}:
            event = events.Key(key=key, character="")
            modal.on_key(event)

    def test_resolve_option_id_by_kinds(self) -> None:
        """_resolve_option_id_by_kinds находит первую подходящую опцию."""
        vm = PermissionViewModel()
        options = [
            PermissionOption(optionId="reject_once", name="Reject", kind="reject_once"),
            PermissionOption(optionId="allow_once", name="Allow", kind="allow_once"),
        ]
        modal = PermissionModal(permission_vm=vm, options=options)
        assert modal._resolve_option_id_by_kinds(["allow_once"]) == "allow_once"
        assert modal._resolve_option_id_by_kinds(["missing"]) is None

    def test_dismiss_by_kinds(self) -> None:
        """_dismiss_by_kinds закрывает модал с выбранной опцией."""
        vm = PermissionViewModel()
        options = [
            PermissionOption(optionId="allow_once", name="Allow", kind="allow_once"),
        ]
        modal = PermissionModal(permission_vm=vm, options=options)
        dismissed: list[object] = []
        modal.dismiss = dismissed.append  # type: ignore[method-assign]
        modal._dismiss_by_kinds(["allow_once"])
        assert dismissed == ["allow_once"]

    def test_default_focus_button_id_reject_once(self) -> None:
        """Фокус по умолчанию на reject_once."""
        vm = PermissionViewModel()
        options = [
            PermissionOption(optionId="allow_once", name="Allow", kind="allow_once"),
            PermissionOption(optionId="reject_once", name="Reject", kind="reject_once"),
        ]
        modal = PermissionModal(permission_vm=vm, options=options)
        assert modal._default_focus_button_id() == "permission-reject_once"

    def test_default_focus_button_id_reject_always(self) -> None:
        """Фокус на reject_always если reject_once нет."""
        vm = PermissionViewModel()
        options = [
            PermissionOption(optionId="allow_once", name="Allow", kind="allow_once"),
            PermissionOption(optionId="reject_always", name="Reject", kind="reject_always"),
        ]
        modal = PermissionModal(permission_vm=vm, options=options)
        assert modal._default_focus_button_id() == "permission-reject_always"

    def test_default_focus_button_id_first(self) -> None:
        """Фокус на первую опцию если reject нет."""
        vm = PermissionViewModel()
        options = [
            PermissionOption(optionId="allow_once", name="Allow", kind="allow_once"),
        ]
        modal = PermissionModal(permission_vm=vm, options=options)
        assert modal._default_focus_button_id() == "permission-allow_once"

    def test_default_focus_button_id_cancel(self) -> None:
        """Фокус на cancel если опций нет."""
        vm = PermissionViewModel()
        modal = PermissionModal(permission_vm=vm)
        assert modal._default_focus_button_id() == "permission-cancel"

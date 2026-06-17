"""Тесты для покрытия permission_request.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from textual.app import App

from codelab.client.messages import PermissionOption
from codelab.client.presentation.permission_view_model import PermissionViewModel
from codelab.client.tui.components.action_button import ActionButton
from codelab.client.tui.components.permission_request import (
    PERMISSION_DESCRIPTIONS,
    PERMISSION_ICONS,
    PermissionRequest,
    PermissionType,
)


def create_view_model() -> PermissionViewModel:
    """Создаёт ViewModel для тестов."""
    return PermissionViewModel()


class TestPermissionConstants:
    """Тесты для констант permission_request."""

    def test_permission_types(self) -> None:
        """Все типы разрешений имеют иконки и описания."""
        types: list[PermissionType] = [
            "file_read",
            "file_write",
            "file_delete",
            "execute_command",
            "mcp_access",
            "unknown",
        ]
        for permission_type in types:
            assert permission_type in PERMISSION_ICONS
            assert permission_type in PERMISSION_DESCRIPTIONS


class TestPermissionRequestInit:
    """Тесты для инициализации PermissionRequest."""

    def test_init_defaults(self) -> None:
        """Инициализация с значениями по умолчанию."""
        vm = create_view_model()
        widget = PermissionRequest(permission_vm=vm, request_id="req_1")
        assert widget.request_id == "req_1"
        assert widget.permission_type == "unknown"
        assert widget.resource == ""
        assert widget.is_resolved is False
        assert widget._auto_deny_seconds is None
        assert widget._action_bar is None

    def test_init_custom(self) -> None:
        """Инициализация с параметрами."""
        vm = create_view_model()
        options = [PermissionOption(optionId="allow", name="Allow", kind="allow_once")]
        widget = PermissionRequest(
            permission_vm=vm,
            request_id="req_1",
            permission_type="file_write",
            resource="/tmp/file.txt",
            message="Test",
            options=options,
            auto_deny_seconds=5,
        )
        assert widget.permission_type == "file_write"
        assert widget.resource == "/tmp/file.txt"
        assert widget._message == "Test"
        assert widget._options == options
        assert widget._auto_deny_seconds == 5
        assert widget._remaining_seconds == 5

    def test_id_generation(self) -> None:
        """ID генерируется из request_id."""
        vm = create_view_model()
        widget = PermissionRequest(permission_vm=vm, request_id="req_1")
        assert widget.id == "perm-req-req_1"


class TestPermissionRequestCompose:
    """Тесты для compose PermissionRequest."""

    async def test_compose_minimal(self) -> None:
        """compose с минимальными параметрами."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            widget = PermissionRequest(permission_vm=vm, request_id="req_1")
            await pilot.app.mount(widget)
            assert widget._action_bar is not None

    async def test_compose_full(self) -> None:
        """compose со всеми полями."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            widget = PermissionRequest(
                permission_vm=vm,
                request_id="req_1",
                permission_type="file_write",
                resource="/tmp/file.txt",
                message="Test message",
                auto_deny_seconds=5,
            )
            await pilot.app.mount(widget)
            assert widget._action_bar is not None


class TestPermissionRequestMount:
    """Тесты для on_mount PermissionRequest."""

    async def test_on_mount_basic_buttons(self) -> None:
        """on_mount добавляет Allow и Deny кнопки."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            widget = PermissionRequest(permission_vm=vm, request_id="req_1")
            await pilot.app.mount(widget)

            assert widget._action_bar is not None
            assert widget._action_bar.get_action("perm-allow") is not None
            assert widget._action_bar.get_action("perm-deny") is not None
            assert widget._action_bar.get_action("perm-always") is None

    async def test_on_mount_always_button(self) -> None:
        """on_mount добавляет Always кнопку при наличии опции."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            options = [
                PermissionOption(optionId="allow_once", name="Allow", kind="allow_once"),
                PermissionOption(optionId="allow_always", name="Always", kind="allow_always"),
            ]
            widget = PermissionRequest(
                permission_vm=vm,
                request_id="req_1",
                options=options,
            )
            await pilot.app.mount(widget)

            assert widget._action_bar.get_action("perm-always") is not None

    async def test_on_mount_auto_deny_timer(self) -> None:
        """on_mount запускает таймер автоотклонения."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            widget = PermissionRequest(
                permission_vm=vm,
                request_id="req_1",
                auto_deny_seconds=5,
            )
            mock_timer = MagicMock()
            with patch.object(widget, "set_interval", return_value=mock_timer):
                await pilot.app.mount(widget)
                widget.set_interval.assert_called_once_with(1.0, widget._tick_auto_deny)
                assert widget._auto_deny_timer is mock_timer


class TestPermissionRequestAutoDeny:
    """Тесты для автоотклонения PermissionRequest."""

    async def test_tick_resolved_stops_timer(self) -> None:
        """Тик при resolved останавливает таймер."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test():
            vm = create_view_model()
            widget = PermissionRequest(
                permission_vm=vm,
                request_id="req_1",
                auto_deny_seconds=5,
            )
            mock_timer = MagicMock()
            widget._auto_deny_timer = mock_timer
            widget._resolved = True
            widget._tick_auto_deny()
            mock_timer.stop.assert_called_once()

    async def test_tick_updates_timer(self) -> None:
        """Тик уменьшает оставшееся время и обновляет виджет."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            widget = PermissionRequest(
                permission_vm=vm,
                request_id="req_1",
                auto_deny_seconds=5,
            )
            await pilot.app.mount(widget)
            widget._remaining_seconds = 5

            widget._tick_auto_deny()
            assert widget._remaining_seconds == 4

    async def test_tick_expires_selects_deny(self) -> None:
        """Истечение времени автоматически отклоняет запрос."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test():
            vm = create_view_model()
            widget = PermissionRequest(
                permission_vm=vm,
                request_id="req_1",
                auto_deny_seconds=5,
            )
            mock_timer = MagicMock()
            widget._auto_deny_timer = mock_timer
            widget._remaining_seconds = 1

            with patch.object(widget, "_select_option") as select_mock:
                widget._tick_auto_deny()
                assert widget._remaining_seconds == 0
                mock_timer.stop.assert_called_once()
                select_mock.assert_called_once_with("deny")

    async def test_tick_timer_widget_not_found_suppressed(self) -> None:
        """Исключение при обновлении таймера подавляется."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            widget = PermissionRequest(
                permission_vm=vm,
                request_id="req_1",
                auto_deny_seconds=5,
            )
            await pilot.app.mount(widget)
            widget._remaining_seconds = 2

            with patch.object(widget, "query_one", side_effect=Exception("not found")):
                widget._tick_auto_deny()
            assert widget._remaining_seconds == 1


class TestPermissionRequestButtons:
    """Тесты для обработки нажатий кнопок."""

    async def test_on_button_pressed_allow(self) -> None:
        """Нажатие Allow выбирает allow_once."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            options = [
                PermissionOption(optionId="opt_allow", name="Allow", kind="allow_once"),
            ]
            widget = PermissionRequest(
                permission_vm=vm,
                request_id="req_1",
                options=options,
            )
            await pilot.app.mount(widget)

            with patch.object(widget, "_select_option") as select_mock:
                allow_button = widget._action_bar.get_action("perm-allow")
                assert allow_button is not None
                widget.on_button_pressed(ActionButton.Pressed(allow_button))
                select_mock.assert_called_once_with("opt_allow")

    async def test_on_button_pressed_deny(self) -> None:
        """Нажатие Deny выбирает reject_once."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            options = [
                PermissionOption(optionId="opt_deny", name="Deny", kind="reject_once"),
            ]
            widget = PermissionRequest(
                permission_vm=vm,
                request_id="req_1",
                options=options,
            )
            await pilot.app.mount(widget)

            with patch.object(widget, "_select_option") as select_mock:
                deny_button = widget._action_bar.get_action("perm-deny")
                assert deny_button is not None
                widget.on_button_pressed(ActionButton.Pressed(deny_button))
                select_mock.assert_called_once_with("opt_deny")

    async def test_on_button_pressed_always(self) -> None:
        """Нажатие Always выбирает allow_always."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            options = [
                PermissionOption(optionId="opt_always", name="Always", kind="allow_always"),
            ]
            widget = PermissionRequest(
                permission_vm=vm,
                request_id="req_1",
                options=options,
            )
            await pilot.app.mount(widget)

            with patch.object(widget, "_select_option") as select_mock:
                always_button = widget._action_bar.get_action("perm-always")
                assert always_button is not None
                widget.on_button_pressed(ActionButton.Pressed(always_button))
                select_mock.assert_called_once_with("opt_always")

    async def test_on_button_pressed_resolved_ignored(self) -> None:
        """Нажатие после решения игнорируется."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            widget = PermissionRequest(permission_vm=vm, request_id="req_1")
            await pilot.app.mount(widget)
            widget._resolved = True

            with patch.object(widget, "_select_option") as select_mock:
                allow_button = widget._action_bar.get_action("perm-allow")
                widget.on_button_pressed(ActionButton.Pressed(allow_button))
                select_mock.assert_not_called()


class TestPermissionRequestFindOption:
    """Тесты для поиска опций."""

    def test_find_option_id_found(self) -> None:
        """Поиск находит ID опции по kind."""
        vm = create_view_model()
        options = [
            PermissionOption(optionId="opt_allow", name="Allow", kind="allow_once"),
        ]
        widget = PermissionRequest(permission_vm=vm, request_id="req_1", options=options)
        assert widget._find_option_id("allow_once") == "opt_allow"

    def test_find_option_id_not_found(self) -> None:
        """Поиск несуществующего kind возвращает None."""
        vm = create_view_model()
        widget = PermissionRequest(permission_vm=vm, request_id="req_1")
        assert widget._find_option_id("allow_once") is None


class TestPermissionRequestSelectOption:
    """Тесты для _select_option."""

    async def test_select_option_granted(self) -> None:
        """Выбор allow устанавливает granted статус."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            widget = PermissionRequest(permission_vm=vm, request_id="req_1")
            await pilot.app.mount(widget)
            await pilot.pause()

            callback_calls: list[tuple[str | int, str]] = []
            widget._on_choice = lambda req_id, opt_id: callback_calls.append((req_id, opt_id))
            posted: list[PermissionRequest.Choice] = []

            def mock_post(msg: object) -> None:
                if isinstance(msg, PermissionRequest.Choice):
                    posted.append(msg)

            with patch.object(widget, "post_message", side_effect=mock_post):
                widget._select_option("allow")

            assert widget.is_resolved is True
            assert widget.has_class("granted")
            assert len(callback_calls) == 1
            assert callback_calls[0] == ("req_1", "allow")
            assert len(posted) == 1
            assert posted[0].request_id == "req_1"
            assert posted[0].option_id == "allow"
            assert posted[0].widget is widget
            assert vm.is_visible.value is False

    async def test_select_option_denied(self) -> None:
        """Выбор deny устанавливает denied статус."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            widget = PermissionRequest(permission_vm=vm, request_id="req_1")
            await pilot.app.mount(widget)

            widget._select_option("deny")
            assert widget.has_class("denied")
            assert not widget.has_class("granted")

    async def test_select_option_resolved_guard(self) -> None:
        """Повторный выбор игнорируется."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            widget = PermissionRequest(permission_vm=vm, request_id="req_1")
            await pilot.app.mount(widget)

            widget._resolved = True
            with patch.object(widget, "post_message") as post_mock:
                widget._select_option("allow")
            post_mock.assert_not_called()

    async def test_select_option_stops_timer(self) -> None:
        """Выбор останавливает таймер."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            widget = PermissionRequest(permission_vm=vm, request_id="req_1")
            await pilot.app.mount(widget)

            mock_timer = MagicMock()
            widget._auto_deny_timer = mock_timer
            widget._select_option("allow")
            mock_timer.stop.assert_called_once()

    async def test_select_option_badge_exception_suppressed(self) -> None:
        """Исключение при обновлении badge подавляется."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            widget = PermissionRequest(permission_vm=vm, request_id="req_1")
            await pilot.app.mount(widget)

            with patch.object(widget, "query_one", side_effect=Exception("boom")):
                widget._select_option("allow")

            assert widget.is_resolved is True

    async def test_select_option_buttons_exception_suppressed(self) -> None:
        """Исключение при отключении кнопок подавляется."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            widget = PermissionRequest(permission_vm=vm, request_id="req_1")
            await pilot.app.mount(widget)

            with patch.object(widget, "query", side_effect=Exception("boom")):
                widget._select_option("allow")

            assert widget.is_resolved is True


class TestPermissionRequestPublicMethods:
    """Тесты для публичных методов PermissionRequest."""

    async def test_allow(self) -> None:
        """allow выбирает allow_once опцию."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            options = [
                PermissionOption(optionId="opt_allow", name="Allow", kind="allow_once"),
            ]
            widget = PermissionRequest(
                permission_vm=vm,
                request_id="req_1",
                options=options,
            )
            await pilot.app.mount(widget)

            with patch.object(widget, "_select_option") as select_mock:
                widget.allow()
                select_mock.assert_called_once_with("opt_allow")

    async def test_allow_fallback(self) -> None:
        """allow без allow_once опции использует fallback."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            widget = PermissionRequest(permission_vm=vm, request_id="req_1")
            await pilot.app.mount(widget)

            with patch.object(widget, "_select_option") as select_mock:
                widget.allow()
                select_mock.assert_called_once_with("allow")

    async def test_deny(self) -> None:
        """deny выбирает reject_once опцию."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            options = [
                PermissionOption(optionId="opt_deny", name="Deny", kind="reject_once"),
            ]
            widget = PermissionRequest(
                permission_vm=vm,
                request_id="req_1",
                options=options,
            )
            await pilot.app.mount(widget)

            with patch.object(widget, "_select_option") as select_mock:
                widget.deny()
                select_mock.assert_called_once_with("opt_deny")

    async def test_deny_fallback(self) -> None:
        """deny без reject_once опции использует fallback."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            widget = PermissionRequest(permission_vm=vm, request_id="req_1")
            await pilot.app.mount(widget)

            with patch.object(widget, "_select_option") as select_mock:
                widget.deny()
                select_mock.assert_called_once_with("deny")

    async def test_always_allow(self) -> None:
        """always_allow выбирает allow_always опцию."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            options = [
                PermissionOption(optionId="opt_always", name="Always", kind="allow_always"),
            ]
            widget = PermissionRequest(
                permission_vm=vm,
                request_id="req_1",
                options=options,
            )
            await pilot.app.mount(widget)

            with patch.object(widget, "_select_option") as select_mock:
                widget.always_allow()
                select_mock.assert_called_once_with("opt_always")

    async def test_always_allow_fallback(self) -> None:
        """always_allow без allow_always опции использует fallback."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            vm = create_view_model()
            widget = PermissionRequest(permission_vm=vm, request_id="req_1")
            await pilot.app.mount(widget)

            with patch.object(widget, "_select_option") as select_mock:
                widget.always_allow()
                select_mock.assert_called_once_with("always")

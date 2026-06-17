"""Тесты для покрытия quick_actions_bar.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from textual.app import App

from codelab.client.presentation.ui_view_model import UIViewModel
from codelab.client.tui.components.quick_actions_bar import QuickActionsBar


def _make_ui_vm() -> UIViewModel:
    """Создает UIViewModel с моком event_bus для тестов."""
    return UIViewModel(event_bus=MagicMock())


class TestQuickActionsBarInit:
    """Тесты инициализации QuickActionsBar."""

    def test_init_subscribes_to_loading(self) -> None:
        """При инициализации подписывается на изменения загрузки."""
        ui_vm = _make_ui_vm()
        bar = QuickActionsBar(ui_vm)

        assert bar._ui_vm is ui_vm
        assert bar._theme_manager is None
        assert bar._action_bar is None
        assert bar.id == "quick-actions-bar"

    def test_init_custom_id_and_theme_manager(self) -> None:
        """Можно задать id и theme_manager."""
        ui_vm = _make_ui_vm()
        theme_manager = MagicMock()
        bar = QuickActionsBar(ui_vm, id="custom-bar", theme_manager=theme_manager)

        assert bar.id == "custom-bar"
        assert bar._theme_manager is theme_manager


class TestQuickActionsBarThemeIcon:
    """Тесты для _get_theme_icon."""

    def test_no_theme_manager_returns_palette(self) -> None:
        """Без theme_manager возвращает иконку палитры."""
        bar = QuickActionsBar(_make_ui_vm())
        assert bar._get_theme_icon() == "🎨"

    def test_dark_theme_returns_moon(self) -> None:
        """Темная тема возвращает луну."""
        theme_manager = MagicMock()
        theme_manager.current_theme_name = "dark"
        bar = QuickActionsBar(_make_ui_vm(), theme_manager=theme_manager)
        assert bar._get_theme_icon() == "🌙"

    def test_light_theme_returns_sun(self) -> None:
        """Светлая тема возвращает солнце."""
        theme_manager = MagicMock()
        theme_manager.current_theme_name = "light"
        bar = QuickActionsBar(_make_ui_vm(), theme_manager=theme_manager)
        assert bar._get_theme_icon() == "☀️"

    def test_attribute_error_returns_palette(self) -> None:
        """При отсутствии current_theme_name возвращает палитру."""
        theme_manager = MagicMock()
        del theme_manager.current_theme_name
        bar = QuickActionsBar(_make_ui_vm(), theme_manager=theme_manager)
        assert bar._get_theme_icon() == "🎨"


class TestQuickActionsBarMount:
    """Тесты монтирования и отображения."""

    async def test_compose_creates_action_bar(self) -> None:
        """compose создает ActionBar."""
        bar = QuickActionsBar(_make_ui_vm())

        class TestApp(App):
            def compose(self):
                yield bar

        async with TestApp().run_test() as _:
            assert bar._action_bar is not None
            assert bar._action_bar.id == "quick-actions"

    async def test_on_mount_creates_buttons(self) -> None:
        """При монтировании создаются все кнопки."""
        bar = QuickActionsBar(_make_ui_vm())

        class TestApp(App):
            def compose(self):
                yield bar

        async with TestApp().run_test() as _:
            action_bar = bar._action_bar
            assert action_bar.get_action("quick-new-session") is not None
            assert action_bar.get_action("quick-cancel") is not None
            assert action_bar.get_action("quick-help") is not None
            assert action_bar.get_action("quick-theme") is not None
            assert action_bar.get_action("quick-cancel").disabled is True

    async def test_on_mount_uses_theme_icon(self) -> None:
        """Кнопка темы использует иконку из theme_manager."""
        theme_manager = MagicMock()
        theme_manager.current_theme_name = "dark"
        bar = QuickActionsBar(_make_ui_vm(), theme_manager=theme_manager)

        class TestApp(App):
            def compose(self):
                yield bar

        async with TestApp().run_test() as _:
            theme_button = bar._action_bar.get_action("quick-theme")
            assert theme_button.icon == "🌙"


class TestQuickActionsBarUpdateThemeIcon:
    """Тесты обновления иконки темы."""

    async def test_update_theme_icon_changes_button(self) -> None:
        """Обновление меняет иконку кнопки темы."""
        theme_manager = MagicMock()
        theme_manager.current_theme_name = "dark"
        bar = QuickActionsBar(_make_ui_vm(), theme_manager=theme_manager)

        class TestApp(App):
            def compose(self):
                yield bar

        async with TestApp().run_test() as _:
            theme_manager.current_theme_name = "light"
            bar.update_theme_icon()
            theme_button = bar._action_bar.get_action("quick-theme")
            assert theme_button.icon == "☀️"

    def test_update_theme_icon_no_action_bar(self) -> None:
        """Без action_bar обновление безопасно."""
        bar = QuickActionsBar(_make_ui_vm())
        bar.update_theme_icon()

    async def test_update_theme_icon_exception_suppressed(self) -> None:
        """Исключения при обновлении иконки подавляются."""
        bar = QuickActionsBar(_make_ui_vm())

        class TestApp(App):
            def compose(self):
                yield bar

        async with TestApp().run_test() as _:
            bar._action_bar.get_action = MagicMock(side_effect=RuntimeError("boom"))
            bar.update_theme_icon()


class TestQuickActionsBarLoading:
    """Тесты реакции на изменение загрузки."""

    def test_on_loading_changed_enables_cancel(self) -> None:
        """При загрузке кнопка отмены активируется."""
        ui_vm = _make_ui_vm()
        bar = QuickActionsBar(ui_vm)
        action_bar = MagicMock()
        bar._action_bar = action_bar

        bar._on_loading_changed(True)
        action_bar.set_action_disabled.assert_called_once_with("quick-cancel", False)

    def test_on_loading_changed_disables_cancel(self) -> None:
        """При завершении загрузки кнопка отмены отключается."""
        ui_vm = _make_ui_vm()
        bar = QuickActionsBar(ui_vm)
        action_bar = MagicMock()
        bar._action_bar = action_bar

        bar._on_loading_changed(False)
        action_bar.set_action_disabled.assert_called_once_with("quick-cancel", True)

    def test_subscription_receives_changes(self) -> None:
        """Подписка на is_loading обновляет состояние кнопки отмены."""
        ui_vm = _make_ui_vm()
        bar = QuickActionsBar(ui_vm)
        action_bar = MagicMock()
        bar._action_bar = action_bar

        ui_vm.set_loading(True)
        action_bar.set_action_disabled.assert_called_once_with("quick-cancel", False)

        ui_vm.set_loading(False)
        assert action_bar.set_action_disabled.call_args_list == [
            (("quick-cancel", False),),
            (("quick-cancel", True),),
        ]


class TestQuickActionsBarButtonPresses:
    """Тесты обработки нажатий кнопок."""

    def _press(self, bar: QuickActionsBar, button_id: str) -> list[object]:
        """Эмулирует нажатие кнопки и возвращает отправленные сообщения."""
        posted: list[object] = []
        bar.post_message = posted.append
        event = MagicMock()
        event.button.id = button_id
        bar.on_button_pressed(event)
        return posted

    def test_new_session_posts_requested(self) -> None:
        """Нажатие новой сессии отправляет NewSessionRequested."""
        bar = QuickActionsBar(_make_ui_vm())
        posted = self._press(bar, "quick-new-session")
        assert len(posted) == 1
        assert isinstance(posted[0], QuickActionsBar.NewSessionRequested)

    def test_cancel_posts_requested(self) -> None:
        """Нажатие отмены отправляет CancelRequested."""
        bar = QuickActionsBar(_make_ui_vm())
        posted = self._press(bar, "quick-cancel")
        assert len(posted) == 1
        assert isinstance(posted[0], QuickActionsBar.CancelRequested)

    def test_help_posts_requested(self) -> None:
        """Нажатие справки отправляет HelpRequested."""
        bar = QuickActionsBar(_make_ui_vm())
        posted = self._press(bar, "quick-help")
        assert len(posted) == 1
        assert isinstance(posted[0], QuickActionsBar.HelpRequested)

    def test_theme_posts_requested(self) -> None:
        """Нажатие темы отправляет ThemeToggleRequested."""
        bar = QuickActionsBar(_make_ui_vm())
        posted = self._press(bar, "quick-theme")
        assert len(posted) == 1
        assert isinstance(posted[0], QuickActionsBar.ThemeToggleRequested)

    def test_unknown_button_does_nothing(self) -> None:
        """Неизвестная кнопка не отправляет сообщений."""
        bar = QuickActionsBar(_make_ui_vm())
        posted = self._press(bar, "quick-unknown")
        assert len(posted) == 0


class TestQuickActionsBarVisibility:
    """Тесты показа и скрытия панели."""

    async def test_show_removes_hidden_class(self) -> None:
        """show удаляет класс hidden."""
        bar = QuickActionsBar(_make_ui_vm())

        class TestApp(App):
            def compose(self):
                yield bar

        async with TestApp().run_test() as _:
            bar.add_class("hidden")
            bar.show()
            assert not bar.has_class("hidden")

    async def test_hide_adds_hidden_class(self) -> None:
        """hide добавляет класс hidden."""
        bar = QuickActionsBar(_make_ui_vm())

        class TestApp(App):
            def compose(self):
                yield bar

        async with TestApp().run_test() as _:
            bar.hide()
            assert bar.has_class("hidden")

"""Тесты для компонентов Фазы 4 (Advanced Features).

Тестирует:
- Theme System (ThemeManager)
- Toast Notifications
- TabBar/TabPanel
- SearchInput
- ProgressBar
- Spinner
- ContextMenu
- TerminalPanel
"""

from __future__ import annotations

from codelab.client.tui.components.context_menu import (
    MenuGroup,
    MenuItem,
    MenuSeparator,
)
from codelab.client.tui.components.progress import ProgressVariant
from codelab.client.tui.components.spinner import SpinnerSize, SpinnerVariant
from codelab.client.tui.components.tabs import TabData
from codelab.client.tui.components.terminal_panel import TerminalSession
from codelab.client.tui.components.toast import ToastData, ToastType
from codelab.client.tui.themes import Theme, ThemeManager, ThemeType


class TestThemeManager:
    """Тесты для ThemeManager."""

    def test_theme_manager_initialization(self) -> None:
        """ThemeManager инициализируется с темами по умолчанию."""
        manager = ThemeManager()

        assert "dark" in manager.available_themes
        assert "light" in manager.available_themes
        assert manager.current_theme_name == "light"

    def test_set_theme_valid(self) -> None:
        """Установка валидной темы работает."""
        manager = ThemeManager()

        result = manager.set_theme("dark")

        assert result is True
        assert manager.current_theme_name == "dark"

    def test_set_theme_invalid(self) -> None:
        """Установка невалидной темы возвращает False."""
        manager = ThemeManager()

        result = manager.set_theme("nonexistent")

        assert result is False
        assert manager.current_theme_name == "light"

    def test_toggle_theme(self) -> None:
        """Переключение темы работает."""
        manager = ThemeManager()
        assert manager.current_theme_name == "light"

        new_theme = manager.toggle_theme()
        assert new_theme == "dark"
        assert manager.current_theme_name == "dark"

        new_theme = manager.toggle_theme()
        assert new_theme == "light"
        assert manager.current_theme_name == "light"

    def test_register_custom_theme(self) -> None:
        """Регистрация пользовательской темы работает."""
        manager = ThemeManager()
        custom_theme = Theme(
            name="custom",
            display_name="Custom Theme",
            colors={"background": "#000000"},
        )

        manager.register_theme(custom_theme)

        assert "custom" in manager.available_themes
        assert manager.set_theme("custom") is True
        assert manager.current_theme_name == "custom"

    def test_theme_get_css_variables(self) -> None:
        """Генерация CSS переменных темы работает."""
        theme = Theme(
            name="test",
            display_name="Test",
            colors={"background": "#123456", "foreground": "#abcdef"},
        )

        css = theme.get_css_variables()

        assert "--background: #123456" in css
        assert "--foreground: #abcdef" in css


class TestThemeType:
    """Тесты для ThemeType enum."""

    def test_theme_type_values(self) -> None:
        """ThemeType имеет правильные значения."""
        assert ThemeType.DARK.value == "dark"
        assert ThemeType.LIGHT.value == "light"


class TestToastData:
    """Тесты для ToastData."""

    def test_toast_data_defaults(self) -> None:
        """ToastData имеет правильные значения по умолчанию."""
        data = ToastData(message="Test message")

        assert data.message == "Test message"
        assert data.toast_type == ToastType.INFO
        assert data.duration == 3.0
        assert data.title is None

    def test_toast_data_custom_values(self) -> None:
        """ToastData принимает пользовательские значения."""
        data = ToastData(
            message="Error occurred",
            toast_type=ToastType.ERROR,
            duration=0.0,
            title="Error",
        )

        assert data.message == "Error occurred"
        assert data.toast_type == ToastType.ERROR
        assert data.duration == 0.0
        assert data.title == "Error"


class TestToastType:
    """Тесты для ToastType enum."""

    def test_toast_type_values(self) -> None:
        """ToastType имеет правильные значения."""
        assert ToastType.INFO.value == "info"
        assert ToastType.SUCCESS.value == "success"
        assert ToastType.WARNING.value == "warning"
        assert ToastType.ERROR.value == "error"


class TestTabData:
    """Тесты для TabData."""

    def test_tab_data_defaults(self) -> None:
        """TabData имеет правильные значения по умолчанию."""
        data = TabData(id="test", label="Test Tab")

        assert data.id == "test"
        assert data.label == "Test Tab"
        assert data.closable is True
        assert data.icon is None

    def test_tab_data_custom_values(self) -> None:
        """TabData принимает пользовательские значения."""
        data = TabData(
            id="main",
            label="Main",
            closable=False,
            icon="📁",
        )

        assert data.id == "main"
        assert data.label == "Main"
        assert data.closable is False
        assert data.icon == "📁"


class TestProgressVariant:
    """Тесты для ProgressVariant enum."""

    def test_progress_variant_values(self) -> None:
        """ProgressVariant имеет правильные значения."""
        assert ProgressVariant.DEFAULT.value == "default"
        assert ProgressVariant.PRIMARY.value == "primary"
        assert ProgressVariant.SUCCESS.value == "success"
        assert ProgressVariant.WARNING.value == "warning"
        assert ProgressVariant.ERROR.value == "error"


class TestSpinnerEnums:
    """Тесты для enum-ов Spinner."""

    def test_spinner_size_values(self) -> None:
        """SpinnerSize имеет правильные значения."""
        assert SpinnerSize.SMALL.value == "sm"
        assert SpinnerSize.MEDIUM.value == "md"
        assert SpinnerSize.LARGE.value == "lg"

    def test_spinner_variant_values(self) -> None:
        """SpinnerVariant имеет правильные значения."""
        assert SpinnerVariant.DOTS.value == "dots"
        assert SpinnerVariant.LINE.value == "line"
        assert SpinnerVariant.CIRCLE.value == "circle"
        assert SpinnerVariant.ARROW.value == "arrow"
        assert SpinnerVariant.PULSE.value == "pulse"


class TestMenuItem:
    """Тесты для MenuItem."""

    def test_menu_item_defaults(self) -> None:
        """MenuItem имеет правильные значения по умолчанию."""
        item = MenuItem(id="test", label="Test Item")

        assert item.id == "test"
        assert item.label == "Test Item"
        assert item.icon is None
        assert item.hotkey is None
        assert item.disabled is False
        assert item.action is None
        assert item.data is None

    def test_menu_item_with_action(self) -> None:
        """MenuItem с action работает."""
        action_called = []

        def action() -> None:
            action_called.append(True)

        item = MenuItem(
            id="action",
            label="Action",
            icon="▶",
            hotkey="Enter",
            action=action,
        )

        assert item.icon == "▶"
        assert item.hotkey == "Enter"
        assert item.action is not None

        item.action()
        assert len(action_called) == 1


class TestMenuGroup:
    """Тесты для MenuGroup."""

    def test_menu_group_defaults(self) -> None:
        """MenuGroup имеет правильные значения по умолчанию."""
        group = MenuGroup()

        assert group.items == []
        assert group.title is None

    def test_menu_group_with_items(self) -> None:
        """MenuGroup с элементами работает."""
        items = [
            MenuItem(id="1", label="Item 1"),
            MenuSeparator(),
            MenuItem(id="2", label="Item 2"),
        ]
        group = MenuGroup(items=items, title="Group")

        assert len(group.items) == 3
        assert group.title == "Group"


class TestTerminalSession:
    """Тесты для TerminalSession."""

    def test_terminal_session_creation(self) -> None:
        """TerminalSession создаётся корректно."""
        session = TerminalSession(id="term-1", name="Terminal 1")

        assert session.id == "term-1"
        assert session.name == "Terminal 1"
        assert session.cwd == ""
        assert session.output == []

    def test_terminal_session_add_output(self) -> None:
        """Добавление вывода в сессию работает."""
        session = TerminalSession(id="term-1", name="Terminal 1")

        session.add_output("line 1")
        session.add_output("line 2")

        assert len(session.output) == 2
        assert session.output[0] == "line 1"
        assert session.output[1] == "line 2"


# Примечание: интеграционные тесты с Textual TUI требуют дополнительной настройки
# CSS и будут добавлены после интеграции компонентов в основное приложение.
# Unit-тесты выше покрывают логику компонентов без рендеринга.

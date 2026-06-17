"""Тесты покрытия для themes/manager.py.

Проверяют непокрытые строки в:
- Theme.current_theme
- ThemeManager.get_css
- ThemeManager._apply_theme
- ThemeManager.set_app
- get_theme_manager
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from codelab.client.tui.themes.manager import (
    DARK_THEME,
    LIGHT_THEME,
    ThemeManager,
    get_theme_manager,
)


class TestThemeCurrentProperty:
    """Тесты для свойства current_theme."""

    def test_current_theme_returns_theme_object(self) -> None:
        """current_theme возвращает объект Theme."""
        manager = ThemeManager()
        assert manager.current_theme is LIGHT_THEME

    def test_current_theme_after_set_theme(self) -> None:
        """current_theme обновляется после set_theme."""
        manager = ThemeManager()
        manager.set_theme("dark")
        assert manager.current_theme is DARK_THEME


class TestThemeManagerGetCss:
    """Тесты для ThemeManager.get_css."""

    def test_get_css_contains_screen_styles(self) -> None:
        """get_css генерирует CSS с переменными для Screen."""
        manager = ThemeManager()
        css = manager.get_css()

        assert "Screen {" in css
        assert "background:" in css
        assert "color:" in css
        assert LIGHT_THEME.colors["background"] in css
        assert LIGHT_THEME.colors["foreground"] in css

    def test_get_css_dark_theme(self) -> None:
        """get_css использует текущую тёмную тему."""
        manager = ThemeManager()
        manager.set_theme("dark")
        css = manager.get_css()

        assert DARK_THEME.colors["background"] in css
        assert DARK_THEME.colors["foreground"] in css


class TestThemeManagerApplyTheme:
    """Тесты для ThemeManager._apply_theme."""

    def test_apply_theme_no_app_returns(self) -> None:
        """_apply_theme без приложения возвращает управление."""
        manager = ThemeManager()
        manager._apply_theme()
        # Не должно быть ошибок

    def test_apply_theme_sets_app_theme(self) -> None:
        """_apply_theme устанавливает тему приложения."""
        mock_app = MagicMock()
        mock_app.theme = "light"
        manager = ThemeManager(app=mock_app)

        manager.set_theme("dark")

        assert mock_app.theme == "dark"

    def test_apply_theme_exception_logged(self) -> None:
        """Исключение при применении темы логируется."""

        class FailingApp:
            """Приложение, которое не может применить тему."""

            def __init__(self) -> None:
                self._theme = "light"

            @property
            def theme(self) -> str:
                return self._theme

            @theme.setter
            def theme(self, value: str) -> None:
                raise RuntimeError("theme error")

            def register_theme(self, theme: object) -> None:
                pass

        manager = ThemeManager(app=FailingApp())
        manager._current_theme = DARK_THEME

        manager._apply_theme()


class TestThemeManagerSetApp:
    """Тесты для ThemeManager.set_app."""

    def test_set_app_updates_app(self) -> None:
        """set_app обновляет ссылку на приложение."""
        manager = ThemeManager()
        mock_app = MagicMock()
        manager.set_app(mock_app)
        assert manager._app is mock_app

    def test_set_app_then_apply_theme(self) -> None:
        """После set_app тема применяется к приложению."""
        manager = ThemeManager()
        manager.set_theme("dark")

        mock_app = MagicMock()
        mock_app.theme = "light"
        manager.set_app(mock_app)

        assert manager._app is mock_app


class TestGetThemeManager:
    """Тесты для глобального менеджера тем."""

    def test_get_theme_manager_creates_singleton(self) -> None:
        """get_theme_manager создаёт singleton."""
        manager1 = get_theme_manager()
        manager2 = get_theme_manager()
        assert isinstance(manager1, ThemeManager)
        assert manager1 is manager2

    @patch("codelab.client.tui.themes.manager._theme_manager", None)
    def test_get_theme_manager_returns_new_instance(self) -> None:
        """get_theme_manager возвращает новый экземпляр если None."""
        manager = get_theme_manager()
        assert isinstance(manager, ThemeManager)

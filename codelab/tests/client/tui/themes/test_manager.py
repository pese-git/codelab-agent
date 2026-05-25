"""Тесты для ThemeManager."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codelab.client.tui.themes.manager import (
    DARK_THEME,
    LIGHT_THEME,
    Theme,
    ThemeManager,
)


class TestTheme:
    """Тесты для Theme dataclass."""

    def test_theme_creation(self) -> None:
        """Создание темы с цветами."""
        theme = Theme(name="test", display_name="Test", colors={"bg": "#000000"})
        assert theme.name == "test"
        assert theme.display_name == "Test"
        assert theme.colors["bg"] == "#000000"

    def test_get_css_variables(self) -> None:
        """Генерация CSS переменных."""
        theme = Theme(name="test", display_name="Test", colors={"bg": "#000000", "fg": "#ffffff"})
        css = theme.get_css_variables()
        assert "--bg: #000000" in css
        assert "--fg: #ffffff" in css


class TestThemeManager:
    """Тесты для ThemeManager."""

    def test_default_theme_is_light(self) -> None:
        """По умолчанию тема light."""
        manager = ThemeManager()
        assert manager.current_theme_name == "light"

    def test_available_themes(self) -> None:
        """Доступные темы."""
        manager = ThemeManager()
        assert "light" in manager.available_themes
        assert "dark" in manager.available_themes

    def test_set_theme_dark(self) -> None:
        """Установка dark темы."""
        manager = ThemeManager()
        result = manager.set_theme("dark")
        assert result is True
        assert manager.current_theme_name == "dark"

    def test_set_theme_light(self) -> None:
        """Установка light темы."""
        manager = ThemeManager()
        manager.set_theme("dark")
        result = manager.set_theme("light")
        assert result is True
        assert manager.current_theme_name == "light"

    def test_set_theme_invalid(self) -> None:
        """Установка несуществующей темы."""
        manager = ThemeManager()
        result = manager.set_theme("invalid")
        assert result is False
        assert manager.current_theme_name == "light"  # Не изменилась

    def test_toggle_theme_from_light(self) -> None:
        """Переключение с light на dark."""
        manager = ThemeManager()
        new_theme = manager.toggle_theme()
        assert new_theme == "dark"
        assert manager.current_theme_name == "dark"

    def test_toggle_theme_from_dark(self) -> None:
        """Переключение с dark на light."""
        manager = ThemeManager()
        manager.set_theme("dark")
        new_theme = manager.toggle_theme()
        assert new_theme == "light"
        assert manager.current_theme_name == "light"

    def test_register_theme(self) -> None:
        """Регистрация новой темы."""
        manager = ThemeManager()
        custom_theme = Theme(name="custom", display_name="Custom", colors={"bg": "#ff0000"})
        manager.register_theme(custom_theme)
        assert "custom" in manager.available_themes

    def test_apply_theme_with_app(self) -> None:
        """Применение темы с приложением."""
        mock_app = MagicMock()
        manager = ThemeManager(app=mock_app)

        # Применяем тему
        manager.set_theme("dark")

        # Проверяем что refresh_css был вызван
        mock_app.refresh_css.assert_called_once()

    def test_apply_theme_missing_tcss_no_refresh(self) -> None:
        """Отсутствующий TCSS файл не вызывает refresh_css."""
        mock_app = MagicMock()
        manager = ThemeManager(app=mock_app)

        # Патчим _css_path на несуществующую директорию
        with patch.object(manager, "_css_path", Path("/nonexistent")):
            manager.set_theme("dark")

        # refresh_css не должен вызываться если TCSS файл не найден
        mock_app.refresh_css.assert_not_called()

    def test_predefined_themes_have_all_colors(self) -> None:
        """Предустановленные темы имеют все необходимые цвета."""
        required_keys = {
            "background",
            "foreground",
            "primary",
            "border",
            "header-bg",
            "footer-bg",
        }

        for key in required_keys:
            assert key in DARK_THEME.colors, f"Dark theme missing {key}"
            assert key in LIGHT_THEME.colors, f"Light theme missing {key}"

    def test_dark_theme_contrast_improved(self) -> None:
        """Dark theme имеет улучшенный контраст границ."""
        # Border должен быть #565f89 вместо старого #3b4261
        assert DARK_THEME.colors["border"] == "#565f89"
        assert DARK_THEME.colors["sidebar-border"] == "#565f89"
        assert DARK_THEME.colors["input-border"] == "#565f89"

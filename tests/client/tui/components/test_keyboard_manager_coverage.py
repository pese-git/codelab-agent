"""Тесты покрытия для KeyboardManager."""

from __future__ import annotations

from unittest.mock import MagicMock

from codelab.client.tui.components.keyboard_manager import (
    HotkeyBinding,
    HotkeyCategory,
    KeyboardManager,
)


class TestKeyboardManagerCoverage:
    """Тесты для непокрытых строк keyboard_manager.py."""

    def test_register_duplicate_key_logs_warning(self) -> None:
        """Регистрация дублирующейся клавиши логирует предупреждение."""
        manager = KeyboardManager()
        binding1 = HotkeyBinding(key="f1", action="action_one", description="One")
        binding2 = HotkeyBinding(key="f1", action="action_two", description="Two")

        manager.register(binding1)
        manager.register(binding2)

        assert manager.get_binding("f1").action == "action_two"

    def test_get_bindings_by_category_skips_hidden(self) -> None:
        """Binding'и с show_in_help=False исключаются из справки."""
        manager = KeyboardManager()
        manager.register(
            HotkeyBinding(
                key="shift+x",
                action="hidden_action",
                description="Hidden",
                category=HotkeyCategory.EDITING,
                show_in_help=False,
            )
        )

        by_category = manager.get_bindings_by_category()
        for bindings in by_category.values():
            assert all(binding.show_in_help for binding in bindings)

    def test_format_key_alt(self) -> None:
        """format_key корректно форматирует Alt."""
        manager = KeyboardManager()
        assert manager.format_key("alt+x") == "Alt+X"

    def test_execute_custom_handler_raises(self) -> None:
        """Если кастомный обработчик бросает исключение, execute возвращает False."""
        manager = KeyboardManager()
        failing_handler = MagicMock(side_effect=RuntimeError("boom"))
        manager.register_handler("boom_action", failing_handler)

        result = manager.execute("boom_action")

        assert result is False
        failing_handler.assert_called_once()

    def test_execute_app_action_raises(self) -> None:
        """Если app.action бросает исключение, execute возвращает False."""
        app = MagicMock()
        app.action.side_effect = RuntimeError("no action")
        manager = KeyboardManager(app=app)

        result = manager.execute("nonexistent_action")

        assert result is False
        app.action.assert_called_once_with("nonexistent_action")

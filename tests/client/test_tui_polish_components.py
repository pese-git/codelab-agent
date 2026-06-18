"""Тесты для компонентов Фазы 5 (Polish).

Покрытие:
- KeyboardManager: регистрация и управление горячими клавишами
- CommandPalette: палитра команд с fuzzy search
- StatusLine: строка статуса
"""

from __future__ import annotations

from codelab.client.tui.components.command_palette import (
    DEFAULT_COMMANDS,
    Command,
    CommandCategory,
    CommandPalette,
)
from codelab.client.tui.components.keyboard_manager import (
    CATEGORY_NAMES,
    DEFAULT_BINDINGS,
    HotkeyBinding,
    HotkeyCategory,
    HotkeyGroup,
    KeyboardManager,
    get_keyboard_manager,
    set_keyboard_manager,
)
from codelab.client.tui.components.status_line import (
    StatusIndicator,
    StatusLine,
    StatusMode,
)

# ============================================================================
# KeyboardManager Tests
# ============================================================================


class TestHotkeyBinding:
    """Тесты для HotkeyBinding dataclass."""

    def test_create_basic_binding(self) -> None:
        """Создание базового binding."""
        binding = HotkeyBinding(
            key="ctrl+n",
            action="new_session",
            description="Новая сессия",
        )
        assert binding.key == "ctrl+n"
        assert binding.action == "new_session"
        assert binding.description == "Новая сессия"
        assert binding.category == HotkeyCategory.NAVIGATION
        assert binding.show_in_help is True
        assert binding.priority == 100

    def test_create_binding_with_category(self) -> None:
        """Создание binding с указанной категорией."""
        binding = HotkeyBinding(
            key="ctrl+q",
            action="quit",
            description="Выход",
            category=HotkeyCategory.SYSTEM,
            priority=1,
        )
        assert binding.category == HotkeyCategory.SYSTEM
        assert binding.priority == 1

    def test_binding_hidden_from_help(self) -> None:
        """Binding скрытый из справки."""
        binding = HotkeyBinding(
            key="secret",
            action="secret_action",
            description="Секрет",
            show_in_help=False,
        )
        assert binding.show_in_help is False


class TestKeyboardManager:
    """Тесты для KeyboardManager."""

    def test_create_empty_manager(self) -> None:
        """Создание пустого менеджера (без default bindings)."""
        manager = KeyboardManager()
        # По умолчанию регистрируются DEFAULT_BINDINGS
        assert len(manager.get_all_bindings()) == len(DEFAULT_BINDINGS)

    def test_register_binding(self) -> None:
        """Регистрация нового binding."""
        manager = KeyboardManager()
        initial_count = len(manager.get_all_bindings())
        
        binding = HotkeyBinding(
            key="ctrl+x",
            action="custom_action",
            description="Custom",
        )
        manager.register(binding)
        
        assert len(manager.get_all_bindings()) == initial_count + 1
        assert manager.get_binding("ctrl+x") == binding

    def test_unregister_binding(self) -> None:
        """Удаление binding."""
        manager = KeyboardManager()
        binding = HotkeyBinding(
            key="ctrl+z",
            action="undo",
            description="Отменить",
        )
        manager.register(binding)
        
        assert manager.get_binding("ctrl+z") is not None
        assert manager.unregister("ctrl+z") is True
        assert manager.get_binding("ctrl+z") is None

    def test_unregister_nonexistent(self) -> None:
        """Удаление несуществующего binding."""
        manager = KeyboardManager()
        assert manager.unregister("nonexistent") is False

    def test_get_bindings_by_category(self) -> None:
        """Получение bindings по категориям."""
        manager = KeyboardManager()
        by_category = manager.get_bindings_by_category()
        
        # Должны быть категории из DEFAULT_BINDINGS
        assert len(by_category) > 0
        # Все binding'и должны быть show_in_help=True
        for bindings in by_category.values():
            for binding in bindings:
                assert binding.show_in_help is True

    def test_get_help_groups(self) -> None:
        """Получение групп для справки."""
        manager = KeyboardManager()
        groups = manager.get_help_groups()
        
        assert len(groups) > 0
        for group in groups:
            assert isinstance(group, HotkeyGroup)
            assert group.name in CATEGORY_NAMES.values()

    def test_format_key(self) -> None:
        """Форматирование клавиш для отображения."""
        manager = KeyboardManager()
        
        assert manager.format_key("ctrl+b") == "Ctrl+B"
        assert manager.format_key("ctrl+shift+tab") == "Ctrl+Shift+Tab"
        assert manager.format_key("escape") == "Esc"
        assert manager.format_key("a") == "A"

    def test_get_textual_bindings(self) -> None:
        """Получение bindings в формате Textual."""
        manager = KeyboardManager()
        textual_bindings = manager.get_textual_bindings()
        
        assert len(textual_bindings) > 0
        for key, action, description in textual_bindings:
            assert isinstance(key, str)
            assert isinstance(action, str)
            assert isinstance(description, str)

    def test_case_insensitive_keys(self) -> None:
        """Ключи должны быть case-insensitive."""
        manager = KeyboardManager()
        binding = HotkeyBinding(
            key="CTRL+M",
            action="test",
            description="Test",
        )
        manager.register(binding)
        
        assert manager.get_binding("ctrl+m") is not None
        assert manager.get_binding("CTRL+M") is not None


class TestGlobalKeyboardManager:
    """Тесты для глобального KeyboardManager."""

    def test_get_global_manager(self) -> None:
        """Получение глобального менеджера."""
        manager = get_keyboard_manager()
        assert manager is not None
        assert isinstance(manager, KeyboardManager)

    def test_set_global_manager(self) -> None:
        """Установка глобального менеджера."""
        new_manager = KeyboardManager()
        set_keyboard_manager(new_manager)
        assert get_keyboard_manager() is new_manager


# ============================================================================
# Command Tests
# ============================================================================


class TestCommand:
    """Тесты для Command dataclass."""

    def test_create_command(self) -> None:
        """Создание команды."""
        cmd = Command(
            id="test_cmd",
            name="Тестовая команда",
            description="Описание",
            action="test_action",
        )
        assert cmd.id == "test_cmd"
        assert cmd.name == "Тестовая команда"
        assert cmd.description == "Описание"
        assert cmd.action == "test_action"
        assert cmd.category == CommandCategory.SYSTEM
        assert cmd.enabled is True

    def test_command_with_hotkey(self) -> None:
        """Команда с горячей клавишей."""
        cmd = Command(
            id="save",
            name="Сохранить",
            action="save",
            hotkey="Ctrl+S",
        )
        assert cmd.hotkey == "Ctrl+S"

    def test_disabled_command(self) -> None:
        """Отключённая команда."""
        cmd = Command(
            id="disabled",
            name="Disabled",
            enabled=False,
        )
        assert cmd.enabled is False


class TestDefaultCommands:
    """Тесты для стандартных команд."""

    def test_default_commands_exist(self) -> None:
        """Стандартные команды существуют."""
        assert len(DEFAULT_COMMANDS) > 0

    def test_default_commands_have_required_fields(self) -> None:
        """Все команды имеют обязательные поля."""
        for cmd in DEFAULT_COMMANDS:
            assert cmd.id
            assert cmd.name
            assert cmd.category

    def test_default_commands_unique_ids(self) -> None:
        """ID команд уникальны."""
        ids = [cmd.id for cmd in DEFAULT_COMMANDS]
        assert len(ids) == len(set(ids))


# ============================================================================
# StatusLine Tests
# ============================================================================


class TestStatusMode:
    """Тесты для StatusMode enum."""

    def test_modes_exist(self) -> None:
        """Все режимы существуют."""
        assert StatusMode.NORMAL.value == "normal"
        assert StatusMode.CHAT.value == "chat"
        assert StatusMode.COMMAND.value == "command"
        assert StatusMode.SEARCH.value == "search"


class TestStatusIndicator:
    """Тесты для StatusIndicator dataclass."""

    def test_create_indicator(self) -> None:
        """Создание индикатора."""
        indicator = StatusIndicator(
            name="connection",
            icon="●",
            label="Online",
            active=True,
        )
        assert indicator.name == "connection"
        assert indicator.icon == "●"
        assert indicator.label == "Online"
        assert indicator.active is True

    def test_inactive_indicator(self) -> None:
        """Неактивный индикатор."""
        indicator = StatusIndicator(
            name="sync",
            icon="○",
            active=False,
        )
        assert indicator.active is False


# ============================================================================
# Integration Tests
# ============================================================================


class TestKeyboardManagerIntegration:
    """Интеграционные тесты KeyboardManager."""

    def test_custom_handler(self) -> None:
        """Регистрация и выполнение кастомного обработчика."""
        manager = KeyboardManager()
        executed = []

        def handler() -> None:
            executed.append(True)

        manager.register_handler("custom", handler)
        assert manager.execute("custom") is True
        assert len(executed) == 1

    def test_execute_unknown_action(self) -> None:
        """Выполнение неизвестного действия."""
        manager = KeyboardManager()
        assert manager.execute("unknown_action") is False


class TestCommandPaletteIntegration:
    """Интеграционные тесты CommandPalette."""

    def test_palette_has_default_commands(self) -> None:
        """Палитра содержит команды по умолчанию."""
        palette = CommandPalette()
        # Проверяем что _commands содержит DEFAULT_COMMANDS
        assert len(palette._commands) == len(DEFAULT_COMMANDS)

    def test_add_command(self) -> None:
        """Добавление команды в палитру."""
        palette = CommandPalette()
        initial = len(palette._commands)
        
        cmd = Command(
            id="new_cmd",
            name="New Command",
            action="new_action",
        )
        palette.add_command(cmd)
        
        assert len(palette._commands) == initial + 1

    def test_remove_command(self) -> None:
        """Удаление команды из палитры."""
        palette = CommandPalette()
        initial = len(palette._commands)
        
        # Удаляем одну из существующих команд
        assert palette.remove_command("quit") is True
        assert len(palette._commands) == initial - 1
        assert palette.remove_command("quit") is False

    def test_fuzzy_match(self) -> None:
        """Fuzzy matching в палитре."""
        palette = CommandPalette()
        
        # Тест fuzzy match
        assert palette._fuzzy_match("ns", "new session") is True
        assert palette._fuzzy_match("nsn", "new session") is True
        assert palette._fuzzy_match("xyz", "new session") is False


class TestStatusLineIntegration:
    """Интеграционные тесты StatusLine."""

    def test_default_hints(self) -> None:
        """Стандартные подсказки для режимов."""
        # Проверяем что DEFAULT_HINTS определены для всех режимов
        for mode in StatusMode:
            assert mode in StatusLine.DEFAULT_HINTS
            hints = StatusLine.DEFAULT_HINTS[mode]
            assert isinstance(hints, list)
            assert len(hints) > 0

    def test_set_custom_hints(self) -> None:
        """Установка кастомных подсказок."""
        status_line = StatusLine()
        custom_hints = [("Enter", "OK"), ("Esc", "Cancel")]
        status_line.set_hints(custom_hints)
        assert status_line._custom_hints == custom_hints

    def test_clear_hints(self) -> None:
        """Сброс подсказок."""
        status_line = StatusLine()
        status_line.set_hints([("A", "B")])
        status_line.clear_hints()
        assert status_line._custom_hints == []

    def test_add_indicator(self) -> None:
        """Добавление индикатора."""
        status_line = StatusLine()
        indicator = StatusIndicator(
            name="test",
            icon="T",
        )
        status_line.add_indicator(indicator)
        assert len(status_line._indicators) == 1

    def test_remove_indicator(self) -> None:
        """Удаление индикатора."""
        status_line = StatusLine()
        indicator = StatusIndicator(name="test", icon="T")
        status_line.add_indicator(indicator)
        
        assert status_line.remove_indicator("test") is True
        assert status_line.remove_indicator("test") is False

    def test_update_indicator(self) -> None:
        """Обновление индикатора."""
        status_line = StatusLine()
        indicator = StatusIndicator(name="status", icon="●", active=True)
        status_line.add_indicator(indicator)
        
        assert status_line.update_indicator("status", active=False) is True
        assert status_line._indicators[0].active is False
        
        assert status_line.update_indicator("nonexistent") is False

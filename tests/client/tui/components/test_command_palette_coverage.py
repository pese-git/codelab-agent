"""Тесты для покрытия command_palette.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from textual.widgets import Label

from codelab.client.tui.components.command_palette import (
    CATEGORY_ICONS,
    DEFAULT_COMMANDS,
    Command,
    CommandCategory,
    CommandItem,
    CommandPalette,
)
from codelab.client.tui.components.keyboard_manager import KeyboardManager


class TestCommandConstants:
    """Тесты для констант и Command."""

    def test_command_category_values(self) -> None:
        """Категории команд имеют ожидаемые значения."""
        assert CommandCategory.SESSION.value == "session"
        assert CommandCategory.NAVIGATION.value == "navigation"
        assert CommandCategory.VIEW.value == "view"
        assert CommandCategory.TOOLS.value == "tools"
        assert CommandCategory.SYSTEM.value == "system"

    def test_category_icons(self) -> None:
        """Все категории имеют иконки."""
        for category in CommandCategory:
            assert category in CATEGORY_ICONS

    def test_command_defaults(self) -> None:
        """Command использует значения по умолчанию."""
        cmd = Command(id="test", name="Test")
        assert cmd.description == ""
        assert cmd.category == CommandCategory.SYSTEM
        assert cmd.action == ""
        assert cmd.hotkey == ""
        assert cmd.icon == "▸"
        assert cmd.enabled is True

    def test_default_commands_populated(self) -> None:
        """Стандартный набор команд не пуст."""
        assert len(DEFAULT_COMMANDS) > 0
        assert all(isinstance(cmd, Command) for cmd in DEFAULT_COMMANDS)


class TestCommandItem:
    """Тесты для CommandItem."""

    def test_command_property(self) -> None:
        """Свойство command возвращает исходные данные."""
        cmd = Command(id="test", name="Test", icon="⚙")
        item = CommandItem(cmd)
        assert item.command is cmd

    def test_compose_selected(self) -> None:
        """Выбранный элемент получает CSS класс и содержит Label."""
        cmd = Command(id="test", name="Test", hotkey="Ctrl+T")
        item = CommandItem(cmd, selected=True)
        children = list(item.compose())
        assert item.has_class("-selected")
        assert any(isinstance(child, Label) for child in children)

    def test_compose_disabled(self) -> None:
        """Disabled команда получает CSS класс."""
        cmd = Command(id="test", name="Test", enabled=False)
        item = CommandItem(cmd)
        list(item.compose())
        assert item.has_class("-disabled")

    def test_compose_without_hotkey(self) -> None:
        """Элемент без hotkey не содержит скобок."""
        cmd = Command(id="test", name="Test")
        item = CommandItem(cmd)
        labels = [child for child in item.compose() if isinstance(child, Label)]
        assert labels
        text = str(labels[0].render())
        assert "[" not in text

    def test_click_enabled_posts_selected(self) -> None:
        """Клик по доступной команде отправляет Selected."""
        cmd = Command(id="test", name="Test")
        item = CommandItem(cmd)
        posted: list[CommandItem.Selected] = []
        item.post_message = posted.append
        item.on_click()
        assert len(posted) == 1
        assert posted[0].command is cmd

    def test_click_disabled_does_not_post(self) -> None:
        """Клик по недоступной команде не отправляет Selected."""
        cmd = Command(id="test", name="Test", enabled=False)
        item = CommandItem(cmd)
        posted: list[CommandItem.Selected] = []
        item.post_message = posted.append
        item.on_click()
        assert len(posted) == 0


class TestCommandPalette:
    """Тесты для CommandPalette."""

    def test_init_defaults(self) -> None:
        """Палитра использует стандартные команды и keyboard manager."""
        palette = CommandPalette()
        assert palette._commands == DEFAULT_COMMANDS
        assert isinstance(palette._keyboard_manager, KeyboardManager)
        assert palette._filtered_commands == DEFAULT_COMMANDS
        assert palette._selected_index == 0
        assert palette._history == []

    def test_init_custom_commands(self) -> None:
        """Можно передать собственный список команд."""
        commands = [Command(id="custom", name="Custom")]
        palette = CommandPalette(commands=commands)
        assert palette._commands is commands

    def test_init_custom_keyboard_manager(self) -> None:
        """Можно передать собственный KeyboardManager."""
        manager = KeyboardManager()
        palette = CommandPalette(keyboard_manager=manager)
        assert palette._keyboard_manager is manager

    async def test_compose_in_app(self) -> None:
        """Палитра монтируется в приложении с ожидаемой структурой."""
        from textual.app import App

        palette = CommandPalette()

        class TestApp(App):
            def compose(self):
                yield palette

        async with TestApp().run_test() as pilot:
            assert pilot.app.query_one("#command-search")
            assert pilot.app.query_one(".commands-scroll")
            hint = pilot.app.query_one(".hint", Label)
            assert "Esc" in str(hint.render())

    def test_render_commands_groups_by_category(self) -> None:
        """Команды группируются по категориям."""
        palette = CommandPalette()
        children = list(palette._render_commands())
        assert len(children) > 0

    def test_render_commands_no_results(self) -> None:
        """При пустом фильтре показывается сообщение."""
        palette = CommandPalette()
        palette._commands = []
        palette._filtered_commands = []
        children = list(palette._render_commands())
        assert len(children) == 1
        assert "не найдены" in str(children[0].render()).lower()

    def test_on_screen_resume_focuses_input(self) -> None:
        """При открытии фокус на поле поиска."""
        palette = CommandPalette()
        input_mock = MagicMock()
        with patch.object(palette, "query_one", return_value=input_mock):
            palette.on_screen_resume()
        input_mock.focus.assert_called_once()

    def test_filter_commands_empty_query(self) -> None:
        """Пустой запрос сбрасывает фильтр."""
        palette = CommandPalette()
        original = palette._commands.copy()
        palette._filter_commands("")
        assert palette._filtered_commands == original
        assert palette._selected_index == 0

    def test_filter_commands_non_empty(self) -> None:
        """Фильтр оставляет только подходящие команды."""
        palette = CommandPalette()
        palette._filter_commands("выход")
        assert all("выход" in cmd.name.lower() for cmd in palette._filtered_commands)

    def test_filter_commands_no_results(self) -> None:
        """При отсутствии совпадений список пуст."""
        palette = CommandPalette()
        palette._filter_commands("xyznoexist")
        assert palette._filtered_commands == []

    def test_fuzzy_match(self) -> None:
        """Fuzzy match работает по порядку символов."""
        palette = CommandPalette()
        assert palette._fuzzy_match("abc", "abc") is True
        assert palette._fuzzy_match("abc", "aabbcc") is True
        assert palette._fuzzy_match("abc", "cba") is False
        assert palette._fuzzy_match("", "text") is True

    @pytest.mark.asyncio
    async def test_refresh_commands(self) -> None:
        """Пересоздание списка команд работает."""
        palette = CommandPalette()
        scroll_mock = AsyncMock()
        with patch.object(palette, "query_one", return_value=scroll_mock):
            await palette._refresh_commands()
        scroll_mock.remove_children.assert_called_once()
        scroll_mock.mount.assert_called_once()

    @pytest.mark.asyncio
    async def test_input_changed(self) -> None:
        """Изменение ввода фильтрует и обновляет список."""
        palette = CommandPalette()
        event_mock = MagicMock()
        event_mock.value = "новая"
        with patch.object(palette, "_refresh_commands") as refresh_mock:
            await palette.on_input_changed(event_mock)
        assert palette._filtered_commands
        refresh_mock.assert_awaited_once()

    def test_update_selection(self) -> None:
        """Обновление выделения меняет класс у найденных элементов."""
        palette = CommandPalette()
        palette._selected_index = 1
        item_mocks = [MagicMock() for _ in palette._filtered_commands]
        with patch.object(palette, "query_one", side_effect=item_mocks):
            palette._update_selection()
        # Второй элемент (индекс 1) должен быть выбран
        item_mocks[1].set_class.assert_called_with(True, "-selected")

    def test_update_selection_exception_suppressed(self) -> None:
        """Исключения при обновлении выделения подавляются."""
        palette = CommandPalette()
        with patch.object(palette, "query_one", side_effect=Exception("boom")):
            palette._update_selection()

    def test_action_close(self) -> None:
        """Закрытие палитры возвращает None."""
        palette = CommandPalette()
        dismissed: list[object] = []
        palette.dismiss = dismissed.append  # type: ignore[method-assign]
        palette.action_close()
        assert dismissed == [None]

    def test_action_previous(self) -> None:
        """Переход к предыдущей команде уменьшает индекс."""
        palette = CommandPalette()
        palette._selected_index = 2
        with patch.object(palette, "_update_selection") as update_mock:
            palette.action_previous()
        assert palette._selected_index == 1
        update_mock.assert_called_once()

    def test_action_previous_at_zero(self) -> None:
        """Переход вверх из нулевого индекса не меняет его."""
        palette = CommandPalette()
        palette._selected_index = 0
        with patch.object(palette, "_update_selection") as update_mock:
            palette.action_previous()
        assert palette._selected_index == 0
        update_mock.assert_not_called()

    def test_action_previous_no_commands(self) -> None:
        """Переход вверх без команд не падает."""
        palette = CommandPalette()
        palette._commands = []
        palette._filtered_commands = []
        palette.action_previous()
        assert palette._selected_index == 0

    def test_action_next(self) -> None:
        """Переход к следующей команде увеличивает индекс."""
        palette = CommandPalette()
        with patch.object(palette, "_update_selection") as update_mock:
            palette.action_next()
        assert palette._selected_index == 1
        update_mock.assert_called_once()

    def test_action_next_at_end(self) -> None:
        """Переход вниз из последнего индекса не меняет его."""
        palette = CommandPalette()
        palette._selected_index = len(palette._filtered_commands) - 1
        with patch.object(palette, "_update_selection") as update_mock:
            palette.action_next()
        assert palette._selected_index == len(palette._filtered_commands) - 1
        update_mock.assert_not_called()

    def test_action_next_no_commands(self) -> None:
        """Переход вниз без команд не падает."""
        palette = CommandPalette()
        palette._commands = []
        palette._filtered_commands = []
        palette.action_next()
        assert palette._selected_index == 0

    def test_action_select(self) -> None:
        """Выбор команды добавляет её в историю и закрывает палитру."""
        palette = CommandPalette()
        dismissed: list[Command | None] = []
        palette.dismiss = dismissed.append  # type: ignore[method-assign]
        palette.action_select()
        assert dismissed
        assert dismissed[0] is not None
        assert dismissed[0].id == palette._filtered_commands[0].id
        assert palette._history == [palette._filtered_commands[0].id]

    def test_action_select_index_out_of_range(self) -> None:
        """Выбор с невалидным индексом ничего не делает."""
        palette = CommandPalette()
        palette._selected_index = -1
        dismissed: list[Command | None] = []
        palette.dismiss = dismissed.append  # type: ignore[method-assign]
        palette.action_select()
        assert dismissed == []

    def test_on_command_item_selected(self) -> None:
        """Выбор через CommandItem добавляет в историю и закрывает."""
        palette = CommandPalette()
        dismissed: list[Command | None] = []
        palette.dismiss = dismissed.append  # type: ignore[method-assign]
        cmd = palette._filtered_commands[2]
        palette.on_command_item_selected(CommandItem.Selected(cmd))
        assert dismissed[-1] is cmd
        assert cmd.id in palette._history

    def test_add_to_history_dedup_and_limit(self) -> None:
        """История дедублируется и ограничивается."""
        palette = CommandPalette()
        for i in range(CommandPalette.MAX_HISTORY + 3):
            palette._add_to_history(f"cmd_{i}")
        assert len(palette._history) == CommandPalette.MAX_HISTORY
        assert palette._history[0] == "cmd_7"

    def test_add_command(self) -> None:
        """Добавление команды обновляет списки."""
        palette = CommandPalette()
        new_cmd = Command(id="new", name="New")
        palette.add_command(new_cmd)
        assert new_cmd in palette._commands
        assert new_cmd in palette._filtered_commands

    def test_remove_command_found(self) -> None:
        """Удаление существующей команды возвращает True."""
        palette = CommandPalette()
        assert palette.remove_command("new_session") is True
        assert all(cmd.id != "new_session" for cmd in palette._commands)

    def test_remove_command_not_found(self) -> None:
        """Удаление отсутствующей команды возвращает False."""
        palette = CommandPalette()
        assert palette.remove_command("missing") is False

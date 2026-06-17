"""Тесты для покрытия context_menu.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from textual.app import App
from textual.geometry import Offset
from textual.widgets import Label

from codelab.client.tui.components.context_menu import (
    ContextMenu,
    ContextMenuItem,
    ContextMenuScreen,
    ContextMenuSeparator,
    MenuGroup,
    MenuItem,
    MenuSeparator,
)


class ThemedApp(App):
    """Тестовое приложение с CSS переменными для компонентов."""

    def get_theme_variable_defaults(self) -> dict[str, str]:
        """Добавляет недостающие CSS переменные для компонентов."""
        return {
            "background-secondary": "#24283b",
            "background-tertiary": "#1f2335",
        }


class TestMenuDataClasses:
    """Тесты для dataclass данных меню."""

    def test_menu_item_defaults(self) -> None:
        """MenuItem использует значения по умолчанию."""
        item = MenuItem(id="test", label="Test")
        assert item.icon is None
        assert item.hotkey is None
        assert item.disabled is False
        assert item.action is None
        assert item.data is None

    def test_menu_item_full(self) -> None:
        """MenuItem сохраняет все переданные значения."""
        action = lambda: None
        item = MenuItem(
            id="test",
            label="Test",
            icon="⚙",
            hotkey="Ctrl+T",
            disabled=True,
            action=action,
            data={"key": "value"},
        )
        assert item.icon == "⚙"
        assert item.hotkey == "Ctrl+T"
        assert item.disabled is True
        assert item.action is action
        assert item.data == {"key": "value"}

    def test_menu_separator(self) -> None:
        """MenuSeparator создаётся без параметров."""
        separator = MenuSeparator()
        assert isinstance(separator, MenuSeparator)

    def test_menu_group_defaults(self) -> None:
        """MenuGroup использует значения по умолчанию."""
        group = MenuGroup()
        assert group.items == []
        assert group.title is None

    def test_menu_group_with_items(self) -> None:
        """MenuGroup сохраняет элементы и заголовок."""
        items = [MenuItem(id="a", label="A")]
        group = MenuGroup(items=items, title="Group")
        assert group.items is items
        assert group.title == "Group"


class TestContextMenuItem:
    """Тесты для ContextMenuItem."""

    def test_init_default_id(self) -> None:
        """ID генерируется из id элемента меню."""
        item = MenuItem(id="test", label="Test")
        widget = ContextMenuItem(item)
        assert widget.id == "menu-item-test"
        assert widget.item is item

    def test_init_custom_id(self) -> None:
        """Можно передать явный ID виджета."""
        item = MenuItem(id="test", label="Test")
        widget = ContextMenuItem(item, id="custom-id")
        assert widget.id == "custom-id"

    def test_init_disabled_class(self) -> None:
        """Disabled пункт получает CSS класс."""
        item = MenuItem(id="test", label="Test", disabled=True)
        widget = ContextMenuItem(item)
        assert widget.has_class("-disabled")

    def test_compose_full(self) -> None:
        """compose создаёт иконку, label и hotkey."""
        item = MenuItem(id="test", label="Test", icon="⚙", hotkey="Ctrl+T")
        widget = ContextMenuItem(item)
        children = list(widget.compose())
        assert len(children) == 3
        assert all(isinstance(child, Label) for child in children)
        assert children[0].render() == "⚙"
        assert children[1].render() == "Test"
        assert children[2].render() == "Ctrl+T"

    def test_compose_without_hotkey(self) -> None:
        """compose без hotkey создаёт только иконку и label."""
        item = MenuItem(id="test", label="Test")
        widget = ContextMenuItem(item)
        children = list(widget.compose())
        assert len(children) == 2

    def test_watch_is_selected(self) -> None:
        """watch_is_selected управляет CSS классом."""
        item = MenuItem(id="test", label="Test")
        widget = ContextMenuItem(item)
        widget.watch_is_selected(True)
        assert widget.has_class("-selected")
        widget.watch_is_selected(False)
        assert not widget.has_class("-selected")

    async def test_on_click_enabled(self) -> None:
        """Клик по доступному пункту отправляет Selected."""
        item = MenuItem(id="test", label="Test")
        widget = ContextMenuItem(item)
        posted: list[ContextMenuItem.Selected] = []
        widget.post_message = posted.append
        await widget.on_click()
        assert len(posted) == 1
        assert posted[0].item is item

    def test_on_click_disabled(self) -> None:
        """Клик по отключённому пункту не отправляет Selected."""
        item = MenuItem(id="test", label="Test", disabled=True)
        widget = ContextMenuItem(item)
        posted: list[ContextMenuItem.Selected] = []
        widget.post_message = posted.append
        widget.on_click()
        assert len(posted) == 0


class TestContextMenuSeparator:
    """Тесты для ContextMenuSeparator."""

    def test_init(self) -> None:
        """Разделитель содержит линию."""
        widget = ContextMenuSeparator()
        assert "─" in widget._Static__content


class TestContextMenu:
    """Тесты для ContextMenu."""

    def test_init_defaults(self) -> None:
        """Инициализация с значениями по умолчанию."""
        menu = ContextMenu()
        assert menu._items == []
        assert menu._title is None
        assert menu._menu_items == []
        assert menu._selected_index == -1
        assert menu._visible is True
        assert menu.id == "context-menu"

    def test_init_custom(self) -> None:
        """Инициализация с параметрами."""
        items = [MenuItem(id="a", label="A")]
        menu = ContextMenu(items, title="Menu", id="custom")
        assert menu._items is items
        assert menu._title == "Menu"
        assert menu.id == "custom"

    def test_from_items(self) -> None:
        """Фабричный метод создаёт меню."""
        items = [MenuItem(id="a", label="A")]
        menu = ContextMenu.from_items(items, title="Menu")
        assert isinstance(menu, ContextMenu)
        assert menu._items is items
        assert menu._title == "Menu"

    def test_compose_with_title(self) -> None:
        """compose с заголовком создаёт Label."""
        menu = ContextMenu(title="Menu")
        children = list(menu.compose())
        assert any(isinstance(child, Label) and child.render() == "Menu" for child in children)

    def test_compose_with_group(self) -> None:
        """compose с группой создаёт элементы группы."""
        group = MenuGroup(
            items=[MenuItem(id="a", label="A")],
            title="Group",
        )
        menu = ContextMenu([group])
        children = list(menu.compose())
        labels = [c for c in children if isinstance(c, Label)]
        assert any(c.render() == "Group" for c in labels)
        assert len(menu._menu_items) == 1

    def test_compose_with_separator(self) -> None:
        """compose с разделителем создаёт ContextMenuSeparator."""
        menu = ContextMenu([MenuItem(id="a", label="A"), MenuSeparator()])
        children = list(menu.compose())
        assert any(isinstance(child, ContextMenuSeparator) for child in children)
        assert len(menu._menu_items) == 1

    def test_show_without_items(self) -> None:
        """show без новых элементов меняет видимость."""
        menu = ContextMenu()
        menu.add_class("-hidden")
        menu._visible = False
        menu.focus = MagicMock()
        menu.show()
        assert menu._visible is True
        assert not menu.has_class("-hidden")
        menu.focus.assert_called_once()

    async def test_show_with_items_and_position(self) -> None:
        """show с новыми элементами и позицией перестраивает меню."""
        app = ThemedApp()
        async with app.run_test() as pilot:
            menu = ContextMenu()
            await pilot.app.mount(menu)
            items = [MenuItem(id="a", label="A")]
            menu.focus = MagicMock()
            menu.show(items, x=10, y=20)
            assert menu._items is items
            assert menu.styles.offset.x.value == 10
            assert menu.styles.offset.y.value == 20
            assert len(menu._menu_items) == 1

    def test_hide(self) -> None:
        """hide скрывает меню и отправляет Closed."""
        menu = ContextMenu()
        posted: list[ContextMenu.Closed] = []
        menu.post_message = posted.append
        menu.hide()
        assert menu._visible is False
        assert menu.has_class("-hidden")
        assert len(posted) == 1
        assert isinstance(posted[0], ContextMenu.Closed)

    def test_visible_property(self) -> None:
        """visible возвращает текущее состояние."""
        menu = ContextMenu()
        assert menu.visible is True
        menu._visible = False
        assert menu.visible is False

    def test_select_first_enabled(self) -> None:
        """Первый доступный пункт выделяется."""
        menu = ContextMenu([
            MenuItem(id="disabled", label="D", disabled=True),
            MenuItem(id="enabled", label="E"),
        ])
        list(menu.compose())
        menu._select_first_enabled()
        assert menu._selected_index == 1
        assert menu._menu_items[1].is_selected is True

    def test_select_item(self) -> None:
        """_select_item переключает выделение."""
        menu = ContextMenu([
            MenuItem(id="a", label="A"),
            MenuItem(id="b", label="B"),
        ])
        list(menu.compose())
        menu._select_item(0)
        assert menu._selected_index == 0
        assert menu._menu_items[0].is_selected is True
        menu._select_item(1)
        assert menu._menu_items[0].is_selected is False
        assert menu._menu_items[1].is_selected is True

    def test_select_item_out_of_range(self) -> None:
        """_select_item с невалидным индексом ничего не делает."""
        menu = ContextMenu()
        menu._select_item(0)
        assert menu._selected_index == -1

    def test_action_move_up(self) -> None:
        """action_move_up переключает выделение вверх."""
        menu = ContextMenu([
            MenuItem(id="a", label="A"),
            MenuItem(id="b", label="B"),
        ])
        list(menu.compose())
        menu._select_item(1)
        menu.action_move_up()
        assert menu._selected_index == 0

    def test_action_move_up_skips_disabled(self) -> None:
        """action_move_up пропускает отключённые пункты."""
        menu = ContextMenu([
            MenuItem(id="a", label="A", disabled=True),
            MenuItem(id="b", label="B"),
        ])
        list(menu.compose())
        menu._select_item(1)
        menu.action_move_up()
        assert menu._selected_index == 1

    def test_action_move_up_empty(self) -> None:
        """action_move_up в пустом меню не падает."""
        menu = ContextMenu()
        menu.action_move_up()
        assert menu._selected_index == -1

    def test_action_move_down(self) -> None:
        """action_move_down переключает выделение вниз."""
        menu = ContextMenu([
            MenuItem(id="a", label="A"),
            MenuItem(id="b", label="B"),
        ])
        list(menu.compose())
        menu._select_item(0)
        menu.action_move_down()
        assert menu._selected_index == 1

    def test_action_move_down_wraps(self) -> None:
        """action_move_down переходит с последнего на первый."""
        menu = ContextMenu([
            MenuItem(id="a", label="A"),
            MenuItem(id="b", label="B"),
        ])
        list(menu.compose())
        menu._select_item(1)
        menu.action_move_down()
        assert menu._selected_index == 0

    def test_action_move_down_skips_disabled(self) -> None:
        """action_move_down пропускает отключённые пункты."""
        menu = ContextMenu([
            MenuItem(id="a", label="A"),
            MenuItem(id="b", label="B", disabled=True),
        ])
        list(menu.compose())
        menu._select_item(0)
        menu.action_move_down()
        assert menu._selected_index == 0

    def test_action_select(self) -> None:
        """action_select выполняет выбранный пункт."""
        action_called: list[None] = []
        item = MenuItem(id="a", label="A", action=lambda: action_called.append(None))
        menu = ContextMenu([item])
        list(menu.compose())
        menu._select_item(0)
        posted: list[ContextMenu.ItemSelected] = []
        menu.post_message = posted.append
        menu.action_select()
        assert len(action_called) == 1
        assert len(posted) == 1
        assert posted[0].item is item

    def test_action_select_disabled(self) -> None:
        """action_select не выполняет отключённый пункт."""
        item = MenuItem(id="a", label="A", disabled=True, action=lambda: pytest.fail("called"))
        menu = ContextMenu([item])
        list(menu.compose())
        menu._select_item(0)
        posted: list[ContextMenu.ItemSelected] = []
        menu.post_message = posted.append
        menu.action_select()
        assert len(posted) == 0

    def test_action_select_no_selection(self) -> None:
        """action_select без выделения ничего не делает."""
        menu = ContextMenu([MenuItem(id="a", label="A")])
        list(menu.compose())
        menu.action_select()
        assert menu._selected_index == -1

    def test_action_close(self) -> None:
        """action_close отправляет Closed."""
        menu = ContextMenu()
        posted: list[ContextMenu.Closed] = []
        menu.post_message = posted.append
        menu.action_close()
        assert len(posted) == 1
        assert isinstance(posted[0], ContextMenu.Closed)

    def test_on_context_menu_item_selected(self) -> None:
        """Выбор пункта через ContextMenuItem выполняет действие."""
        item = MenuItem(id="a", label="A")
        menu = ContextMenu([item])
        posted: list[ContextMenu.ItemSelected] = []
        menu.post_message = posted.append
        menu.on_context_menu_item_selected(ContextMenuItem.Selected(item))
        assert len(posted) == 1
        assert posted[0].item is item

    def test_execute_item_without_action(self) -> None:
        """_execute_item без action отправляет только сообщение."""
        item = MenuItem(id="a", label="A")
        menu = ContextMenu([item])
        posted: list[ContextMenu.ItemSelected] = []
        menu.post_message = posted.append
        menu._execute_item(item)
        assert len(posted) == 1
        assert posted[0].item is item

    async def test_mount(self) -> None:
        """Монтирование выделяет первый доступный пункт."""
        app = ThemedApp()
        async with app.run_test() as pilot:
            menu = ContextMenu([
                MenuItem(id="a", label="A"),
                MenuItem(id="b", label="B"),
            ])
            await pilot.app.mount(menu)
            assert menu._selected_index == 0
            assert menu._menu_items[0].is_selected is True


class TestContextMenuScreen:
    """Тесты для ContextMenuScreen."""

    def test_init_defaults(self) -> None:
        """Инициализация с позицией по умолчанию."""
        items = [MenuItem(id="a", label="A")]
        screen = ContextMenuScreen(items)
        assert screen._items is items
        assert screen._position == Offset(0, 0)
        assert screen._title is None

    def test_init_custom(self) -> None:
        """Инициализация с параметрами."""
        items = [MenuItem(id="a", label="A")]
        screen = ContextMenuScreen(items, position=Offset(5, 10), title="Menu", id="screen")
        assert screen._position == Offset(5, 10)
        assert screen._title == "Menu"
        assert screen.id == "screen"

    def test_compose(self) -> None:
        """compose создаёт ContextMenu с позицией."""
        items = [MenuItem(id="a", label="A")]
        screen = ContextMenuScreen(items, position=Offset(5, 10), title="Menu")
        children = list(screen.compose())
        assert len(children) == 1
        assert isinstance(children[0], ContextMenu)
        assert children[0]._title == "Menu"
        assert children[0].styles.offset.x.value == 5
        assert children[0].styles.offset.y.value == 10

    async def test_on_click(self) -> None:
        """Клик вне меню закрывает экран."""
        items = [MenuItem(id="a", label="A")]
        screen = ContextMenuScreen(items)
        dismissed: list[MenuItem | None] = []
        screen.dismiss = dismissed.append  # type: ignore[method-assign]
        await screen.on_click()
        assert dismissed == [None]

    def test_on_context_menu_item_selected(self) -> None:
        """Выбор пункта закрывает экран с выбранным элементом."""
        item = MenuItem(id="a", label="A")
        screen = ContextMenuScreen([item])
        dismissed: list[MenuItem | None] = []
        screen.dismiss = dismissed.append  # type: ignore[method-assign]
        screen.on_context_menu_item_selected(ContextMenu.ItemSelected(item))
        assert dismissed == [item]

    def test_on_context_menu_closed(self) -> None:
        """Закрытие меню закрывает экран."""
        screen = ContextMenuScreen([MenuItem(id="a", label="A")])
        dismissed: list[MenuItem | None] = []
        screen.dismiss = dismissed.append  # type: ignore[method-assign]
        screen.on_context_menu_closed(ContextMenu.Closed())
        assert dismissed == [None]

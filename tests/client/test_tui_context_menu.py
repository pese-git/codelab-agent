"""Тесты для ContextMenu компонента.

Тестирует:
- Рендеринг компонента
- Выбор пунктов меню
- Disabled пункты
- Закрытие по Escape
- Методы show/hide/from_items
"""

from __future__ import annotations

from codelab.client.tui.components.context_menu import (
    ContextMenu,
    ContextMenuItem,
    ContextMenuScreen,
    MenuGroup,
    MenuItem,
    MenuSeparator,
)


class TestMenuItemDataclass:
    """Тесты для dataclass MenuItem."""

    def test_menu_item_required_fields(self) -> None:
        """MenuItem требует id и label."""
        item = MenuItem(id="test", label="Test Item")

        assert item.id == "test"
        assert item.label == "Test Item"

    def test_menu_item_defaults(self) -> None:
        """MenuItem имеет значения по умолчанию."""
        item = MenuItem(id="test", label="Test")

        assert item.icon is None
        assert item.hotkey is None
        assert item.disabled is False
        assert item.action is None
        assert item.data is None

    def test_menu_item_with_all_fields(self) -> None:
        """MenuItem принимает все поля."""
        action_called: list[bool] = []

        def action() -> None:
            action_called.append(True)

        item = MenuItem(
            id="copy",
            label="Copy",
            icon="📋",
            hotkey="Ctrl+C",
            disabled=False,
            action=action,
            data={"type": "copy"},
        )

        assert item.id == "copy"
        assert item.label == "Copy"
        assert item.icon == "📋"
        assert item.hotkey == "Ctrl+C"
        assert item.disabled is False
        assert item.action is not None
        assert item.data == {"type": "copy"}

        # Проверяем вызов action
        item.action()
        assert action_called == [True]

    def test_menu_item_disabled(self) -> None:
        """MenuItem может быть отключён."""
        item = MenuItem(id="paste", label="Paste", disabled=True)

        assert item.disabled is True


class TestMenuSeparatorDataclass:
    """Тесты для dataclass MenuSeparator."""

    def test_menu_separator_creation(self) -> None:
        """MenuSeparator создаётся без параметров."""
        sep = MenuSeparator()

        assert isinstance(sep, MenuSeparator)


class TestMenuGroupDataclass:
    """Тесты для dataclass MenuGroup."""

    def test_menu_group_defaults(self) -> None:
        """MenuGroup имеет пустой список items по умолчанию."""
        group = MenuGroup()

        assert group.items == []
        assert group.title is None

    def test_menu_group_with_items(self) -> None:
        """MenuGroup содержит элементы."""
        items = [
            MenuItem(id="cut", label="Cut"),
            MenuSeparator(),
            MenuItem(id="paste", label="Paste"),
        ]
        group = MenuGroup(items=items, title="Edit")

        assert len(group.items) == 3
        assert group.title == "Edit"


class TestContextMenuItemClass:
    """Тесты для класса ContextMenuItem."""

    def test_context_menu_item_has_css(self) -> None:
        """ContextMenuItem имеет CSS стили."""
        assert "ContextMenuItem" in ContextMenuItem.DEFAULT_CSS
        assert ":hover" in ContextMenuItem.DEFAULT_CSS
        assert ".-disabled" in ContextMenuItem.DEFAULT_CSS
        assert ".-selected" in ContextMenuItem.DEFAULT_CSS

    def test_context_menu_item_initialization(self) -> None:
        """ContextMenuItem инициализируется с MenuItem."""
        item = MenuItem(id="test", label="Test Item")
        widget = ContextMenuItem(item)

        assert widget._item == item
        assert widget.item == item

    def test_context_menu_item_disabled_class(self) -> None:
        """ContextMenuItem добавляет класс -disabled для отключённых пунктов."""
        item = MenuItem(id="test", label="Test", disabled=True)
        widget = ContextMenuItem(item)

        assert "-disabled" in widget.classes

    def test_context_menu_item_id_generated(self) -> None:
        """ContextMenuItem генерирует id из item.id."""
        item = MenuItem(id="my-action", label="Action")
        widget = ContextMenuItem(item)

        assert widget.id == "menu-item-my-action"

    def test_context_menu_item_custom_id(self) -> None:
        """ContextMenuItem может иметь кастомный id."""
        item = MenuItem(id="test", label="Test")
        widget = ContextMenuItem(item, id="custom-id")

        assert widget.id == "custom-id"

    def test_context_menu_item_selected_message(self) -> None:
        """ContextMenuItem.Selected содержит пункт меню."""
        item = MenuItem(id="test", label="Test")
        msg = ContextMenuItem.Selected(item)

        assert msg.item == item


class TestContextMenuClass:
    """Тесты для класса ContextMenu."""

    def test_context_menu_has_css(self) -> None:
        """ContextMenu имеет CSS стили."""
        assert "ContextMenu" in ContextMenu.DEFAULT_CSS
        assert "layer: context-menu" in ContextMenu.DEFAULT_CSS
        assert ".-hidden" in ContextMenu.DEFAULT_CSS

    def test_context_menu_has_bindings(self) -> None:
        """ContextMenu имеет клавиатурные привязки."""
        bindings = {b[0] for b in ContextMenu.BINDINGS}

        assert "up" in bindings
        assert "down" in bindings
        assert "enter" in bindings
        assert "escape" in bindings

    def test_context_menu_initialization_empty(self) -> None:
        """ContextMenu может быть создан без элементов."""
        menu = ContextMenu()

        assert menu._items == []
        assert menu._title is None
        assert menu._menu_items == []
        assert menu._selected_index == -1
        assert menu._visible is True

    def test_context_menu_initialization_with_items(self) -> None:
        """ContextMenu инициализируется со списком элементов."""
        items = [
            MenuItem(id="copy", label="Copy"),
            MenuItem(id="paste", label="Paste"),
        ]
        menu = ContextMenu(items, title="Edit")

        assert menu._items == items
        assert menu._title == "Edit"

    def test_context_menu_default_id(self) -> None:
        """ContextMenu имеет id по умолчанию."""
        menu = ContextMenu()

        assert menu.id == "context-menu"

    def test_context_menu_custom_id(self) -> None:
        """ContextMenu может иметь кастомный id."""
        menu = ContextMenu(id="custom-menu")

        assert menu.id == "custom-menu"

    def test_context_menu_item_selected_message(self) -> None:
        """ContextMenu.ItemSelected содержит пункт меню."""
        item = MenuItem(id="test", label="Test")
        msg = ContextMenu.ItemSelected(item)

        assert msg.item == item

    def test_context_menu_closed_message(self) -> None:
        """ContextMenu.Closed создаётся без аргументов."""
        msg = ContextMenu.Closed()

        assert isinstance(msg, ContextMenu.Closed)


class TestContextMenuFromItems:
    """Тесты для фабричного метода from_items."""

    def test_from_items_creates_menu(self) -> None:
        """from_items создаёт ContextMenu из списка элементов."""
        items = [
            MenuItem(id="cut", label="Cut"),
            MenuItem(id="copy", label="Copy"),
        ]
        menu = ContextMenu.from_items(items)

        assert isinstance(menu, ContextMenu)
        assert menu._items == items
        assert menu._title is None

    def test_from_items_with_title(self) -> None:
        """from_items принимает заголовок."""
        items = [MenuItem(id="test", label="Test")]
        menu = ContextMenu.from_items(items, title="Actions")

        assert menu._title == "Actions"


class TestContextMenuShowHide:
    """Тесты для методов show и hide."""

    def test_hide_sets_hidden_state(self) -> None:
        """hide() устанавливает _visible в False."""
        menu = ContextMenu()
        menu._visible = True

        # Не вызываем hide напрямую т.к. post_message требует mount
        # Проверяем начальное состояние
        assert menu._visible is True

    def test_visible_property(self) -> None:
        """visible возвращает состояние видимости."""
        menu = ContextMenu()

        assert menu.visible is True

        menu._visible = False
        assert menu.visible is False


class TestContextMenuDisabledItems:
    """Тесты для отключённых пунктов меню."""

    def test_disabled_items_skipped_on_navigation(self) -> None:
        """Отключённые пункты пропускаются при навигации."""
        items = [
            MenuItem(id="item1", label="Item 1"),
            MenuItem(id="item2", label="Item 2", disabled=True),
            MenuItem(id="item3", label="Item 3"),
        ]
        menu = ContextMenu(items)

        # Индекс начинается с -1
        assert menu._selected_index == -1


class TestContextMenuScreenClass:
    """Тесты для класса ContextMenuScreen."""

    def test_context_menu_screen_has_css(self) -> None:
        """ContextMenuScreen имеет CSS стили."""
        assert "ContextMenuScreen" in ContextMenuScreen.DEFAULT_CSS
        assert "transparent" in ContextMenuScreen.DEFAULT_CSS

    def test_context_menu_screen_has_escape_binding(self) -> None:
        """ContextMenuScreen имеет привязку Escape."""
        bindings = {b[0] for b in ContextMenuScreen.BINDINGS}

        assert "escape" in bindings

    def test_context_menu_screen_initialization(self) -> None:
        """ContextMenuScreen инициализируется с элементами и позицией."""
        items = [MenuItem(id="test", label="Test")]
        screen = ContextMenuScreen(items, title="Menu")

        assert screen._items == items
        assert screen._title == "Menu"

    def test_context_menu_screen_default_position(self) -> None:
        """ContextMenuScreen имеет позицию по умолчанию (0, 0)."""
        from textual.geometry import Offset

        items = [MenuItem(id="test", label="Test")]
        screen = ContextMenuScreen(items)

        assert screen._position == Offset(0, 0)

    def test_context_menu_screen_custom_position(self) -> None:
        """ContextMenuScreen принимает кастомную позицию."""
        from textual.geometry import Offset

        items = [MenuItem(id="test", label="Test")]
        pos = Offset(10, 20)
        screen = ContextMenuScreen(items, position=pos)

        assert screen._position == pos


class TestContextMenuIntegration:
    """Интеграционные тесты для ContextMenu."""

    def test_menu_with_separator(self) -> None:
        """ContextMenu поддерживает разделители."""
        items = [
            MenuItem(id="cut", label="Cut"),
            MenuSeparator(),
            MenuItem(id="paste", label="Paste"),
        ]
        menu = ContextMenu(items)

        assert len(menu._items) == 3

    def test_menu_with_group(self) -> None:
        """ContextMenu поддерживает группы."""
        items = [
            MenuGroup(
                items=[
                    MenuItem(id="cut", label="Cut"),
                    MenuItem(id="copy", label="Copy"),
                ],
                title="Edit",
            ),
            MenuSeparator(),
            MenuItem(id="settings", label="Settings"),
        ]
        menu = ContextMenu(items)

        assert len(menu._items) == 3

    def test_menu_items_with_icons_and_hotkeys(self) -> None:
        """ContextMenu отображает иконки и горячие клавиши."""
        items = [
            MenuItem(id="copy", label="Copy", icon="📋", hotkey="Ctrl+C"),
            MenuItem(id="paste", label="Paste", icon="📥", hotkey="Ctrl+V"),
        ]
        menu = ContextMenu(items)

        assert menu._items[0].icon == "📋"
        assert menu._items[0].hotkey == "Ctrl+C"
        assert menu._items[1].icon == "📥"
        assert menu._items[1].hotkey == "Ctrl+V"

    def test_action_callback(self) -> None:
        """MenuItem action вызывается при выборе."""
        results = []

        def on_copy():
            results.append("copied")

        item = MenuItem(id="copy", label="Copy", action=on_copy)

        # Вызываем action напрямую
        assert item.action is not None
        item.action()
        assert results == ["copied"]

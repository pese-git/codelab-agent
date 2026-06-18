"""Тесты для CollapsiblePanel и AccordionGroup компонентов.

Тестирует:
- Рендеринг компонента CollapsiblePanel
- Методы toggle, expand, collapse
- Событие CollapsiblePanel.Toggled
- AccordionGroup (одна панель открыта)
"""

from __future__ import annotations

from codelab.client.tui.components.collapsible_panel import (
    AccordionGroup,
    AccordionPanel,
    CollapsiblePanel,
)


class TestCollapsiblePanelClass:
    """Тесты для класса CollapsiblePanel."""

    def test_collapsible_panel_has_default_css(self) -> None:
        """CollapsiblePanel имеет встроенные CSS стили."""
        assert "CollapsiblePanel" in CollapsiblePanel.DEFAULT_CSS
        assert ".panel-header" in CollapsiblePanel.DEFAULT_CSS
        assert ".panel-content" in CollapsiblePanel.DEFAULT_CSS
        assert ".panel-toggle" in CollapsiblePanel.DEFAULT_CSS

    def test_collapsible_panel_initialization_defaults(self) -> None:
        """CollapsiblePanel инициализируется с параметрами по умолчанию."""
        panel = CollapsiblePanel()

        assert panel._title == ""
        assert panel._icon == ""
        assert panel._initial_collapsed is False

    def test_collapsible_panel_initialization_custom(self) -> None:
        """CollapsiblePanel принимает пользовательские параметры."""
        panel = CollapsiblePanel(
            title="Настройки",
            icon="⚙️",
            collapsed=True,
            name="settings-panel",
            id="custom-panel",
            classes="settings",
        )

        assert panel._title == "Настройки"
        assert panel._icon == "⚙️"
        assert panel._initial_collapsed is True
        assert panel.name == "settings-panel"
        assert panel.id == "custom-panel"
        assert "settings" in panel.classes

    def test_collapsible_panel_initial_collapsed_state(self) -> None:
        """CollapsiblePanel может быть изначально свёрнута."""
        panel = CollapsiblePanel(title="Свёрнутая", collapsed=True)

        assert panel._initial_collapsed is True

    def test_collapsible_panel_initial_expanded_state(self) -> None:
        """CollapsiblePanel по умолчанию развёрнута."""
        panel = CollapsiblePanel(title="Развёрнутая")

        assert panel._initial_collapsed is False


class TestCollapsiblePanelToggledMessage:
    """Тесты для сообщения CollapsiblePanel.Toggled."""

    def test_toggled_message_contains_panel_reference(self) -> None:
        """Toggled сообщение содержит ссылку на панель."""
        panel = CollapsiblePanel(title="Test")
        msg = CollapsiblePanel.Toggled(panel=panel, collapsed=True)

        assert msg.panel is panel

    def test_toggled_message_contains_collapsed_state(self) -> None:
        """Toggled сообщение содержит состояние свёрнутости."""
        panel = CollapsiblePanel(title="Test")

        msg_collapsed = CollapsiblePanel.Toggled(panel=panel, collapsed=True)
        assert msg_collapsed.collapsed is True

        msg_expanded = CollapsiblePanel.Toggled(panel=panel, collapsed=False)
        assert msg_expanded.collapsed is False


class TestCollapsiblePanelMethods:
    """Тесты для методов CollapsiblePanel."""

    def test_expand_method_exists(self) -> None:
        """CollapsiblePanel имеет метод expand()."""
        panel = CollapsiblePanel()
        assert hasattr(panel, "expand")
        assert callable(panel.expand)

    def test_collapse_method_exists(self) -> None:
        """CollapsiblePanel имеет метод collapse()."""
        panel = CollapsiblePanel()
        assert hasattr(panel, "collapse")
        assert callable(panel.collapse)

    def test_toggle_method_exists(self) -> None:
        """CollapsiblePanel имеет метод toggle()."""
        panel = CollapsiblePanel()
        assert hasattr(panel, "toggle")
        assert callable(panel.toggle)

    def test_content_property_exists(self) -> None:
        """CollapsiblePanel имеет свойство content."""
        panel = CollapsiblePanel()
        assert hasattr(panel, "content")


class TestCollapsiblePanelReactiveProperties:
    """Тесты для reactive свойств CollapsiblePanel."""

    def test_collapsed_is_reactive(self) -> None:
        """collapsed является reactive свойством."""
        # Проверяем что reactive свойство определено в классе
        assert hasattr(CollapsiblePanel, "collapsed")

    def test_title_is_reactive(self) -> None:
        """title является reactive свойством."""
        assert hasattr(CollapsiblePanel, "title")

    def test_icon_is_reactive(self) -> None:
        """icon является reactive свойством."""
        assert hasattr(CollapsiblePanel, "icon")


class TestAccordionGroupClass:
    """Тесты для класса AccordionGroup."""

    def test_accordion_group_is_alias_for_accordion_panel(self) -> None:
        """AccordionGroup является alias для AccordionPanel."""
        assert AccordionGroup is AccordionPanel

    def test_accordion_group_has_default_css(self) -> None:
        """AccordionGroup имеет встроенные CSS стили."""
        assert "AccordionPanel" in AccordionGroup.DEFAULT_CSS
        assert "CollapsiblePanel" in AccordionGroup.DEFAULT_CSS

    def test_accordion_group_initialization_defaults(self) -> None:
        """AccordionGroup инициализируется с параметрами по умолчанию."""
        group = AccordionGroup()

        assert group._allow_multiple is False

    def test_accordion_group_initialization_allow_multiple(self) -> None:
        """AccordionGroup может разрешить несколько открытых панелей."""
        group = AccordionGroup(allow_multiple=True)

        assert group._allow_multiple is True

    def test_accordion_group_initialization_custom(self) -> None:
        """AccordionGroup принимает пользовательские параметры."""
        group = AccordionGroup(
            allow_multiple=False,
            name="settings-accordion",
            id="accordion-1",
            classes="accordion-group",
        )

        assert group._allow_multiple is False
        assert group.name == "settings-accordion"
        assert group.id == "accordion-1"
        assert "accordion-group" in group.classes


class TestAccordionGroupBehavior:
    """Тесты для поведения AccordionGroup."""

    def test_accordion_group_default_single_panel_mode(self) -> None:
        """По умолчанию AccordionGroup работает в режиме одной открытой панели."""
        group = AccordionGroup()

        assert group._allow_multiple is False

    def test_accordion_group_multiple_panels_mode(self) -> None:
        """AccordionGroup может работать в режиме нескольких открытых панелей."""
        group = AccordionGroup(allow_multiple=True)

        assert group._allow_multiple is True

    def test_accordion_group_handles_toggled_event(self) -> None:
        """AccordionGroup обрабатывает событие CollapsiblePanel.Toggled."""
        group = AccordionGroup()
        # Проверяем что метод обработки события существует
        assert hasattr(group, "on_collapsible_panel_toggled")


class TestCollapsiblePanelImports:
    """Тесты для импортов из collapsible_panel модуля."""

    def test_collapsible_panel_importable(self) -> None:
        """CollapsiblePanel можно импортировать из collapsible_panel."""
        from codelab.client.tui.components.collapsible_panel import CollapsiblePanel

        assert CollapsiblePanel is not None

    def test_accordion_group_importable(self) -> None:
        """AccordionGroup можно импортировать из collapsible_panel."""
        from codelab.client.tui.components.collapsible_panel import AccordionGroup

        assert AccordionGroup is not None

    def test_accordion_panel_importable(self) -> None:
        """AccordionPanel можно импортировать из collapsible_panel для совместимости."""
        from codelab.client.tui.components.collapsible_panel import AccordionPanel

        assert AccordionPanel is not None

    def test_components_importable_from_main_init(self) -> None:
        """Компоненты можно импортировать из главного __init__.py."""
        from codelab.client.tui.components import (
            AccordionGroup,
            AccordionPanel,
            CollapsiblePanel,
        )

        assert CollapsiblePanel is not None
        assert AccordionGroup is not None
        assert AccordionPanel is not None


class TestCollapsiblePanelIcons:
    """Тесты для иконок CollapsiblePanel."""

    def test_panel_toggle_icons_in_css(self) -> None:
        """Иконки toggle (▶/▼) используются в panel."""
        # Проверяем что CSS содержит стили для toggle кнопки
        assert ".panel-toggle" in CollapsiblePanel.DEFAULT_CSS

    def test_panel_accepts_custom_icon(self) -> None:
        """CollapsiblePanel принимает пользовательскую иконку."""
        panel = CollapsiblePanel(title="Test", icon="📁")

        assert panel._icon == "📁"

    def test_panel_accepts_emoji_icon(self) -> None:
        """CollapsiblePanel принимает emoji как иконку."""
        panel = CollapsiblePanel(title="Файлы", icon="📂")

        assert panel._icon == "📂"

    def test_panel_accepts_empty_icon(self) -> None:
        """CollapsiblePanel принимает пустую иконку."""
        panel = CollapsiblePanel(title="Без иконки", icon="")

        assert panel._icon == ""

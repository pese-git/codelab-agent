"""Тесты покрытия для panel.py.

Проверяют непокрытые строки в:
- CollapsiblePanel
- AccordionPanel
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from textual.app import App
from textual.containers import Container
from textual.widgets import Button, Static

from codelab.client.tui.components.panel import AccordionPanel, CollapsiblePanel


class TestToggledMessage:
    """Тесты для сообщения CollapsiblePanel.Toggled."""

    def test_toggled_message_stores_state(self) -> None:
        """Toggled сохраняет панель и состояние."""
        panel = CollapsiblePanel(title="Test")
        msg = CollapsiblePanel.Toggled(panel=panel, collapsed=True)
        assert msg.panel is panel
        assert msg.collapsed is True


class TestCollapsiblePanelInit:
    """Тесты инициализации CollapsiblePanel."""

    def test_init_with_children(self) -> None:
        """Инициализация с дочерними виджетами."""
        child = Static("child")
        panel = CollapsiblePanel(
            child,
            title="Заголовок",
            icon="⚙️",
            collapsed=True,
            name="panel-name",
            id="panel-id",
            classes="panel-class",
        )
        assert panel._initial_children == (child,)
        assert panel._title == "Заголовок"
        assert panel._icon == "⚙️"
        assert panel._initial_collapsed is True
        assert panel.name == "panel-name"
        assert panel.id == "panel-id"
        assert "panel-class" in panel.classes


class TestCollapsiblePanelCompose:
    """Тесты compose и on_mount."""

    async def test_compose_creates_header_and_content(self) -> None:
        """compose создаёт header, иконку, заголовок, кнопку и контент."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            panel = CollapsiblePanel(title="Test", icon="⚙️")
            await pilot.app.mount(panel)

            assert panel._icon_widget is not None
            assert panel._title_widget is not None
            assert panel._toggle_button is not None
            assert panel._content_container is not None
            assert "▼" in str(panel._toggle_button.label)

    async def test_compose_collapsed_initially(self) -> None:
        """compose добавляет hidden класс если панель свёрнута."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            panel = CollapsiblePanel(title="Test", collapsed=True)
            await pilot.app.mount(panel)

            assert panel._content_container.has_class("hidden")
            assert "▶" in str(panel._toggle_button.label)

    async def test_on_mount_adds_children(self) -> None:
        """on_mount монтирует переданных детей в контент."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            child = Static("child content")
            panel = CollapsiblePanel(child, title="Test", icon="⚙️")
            await pilot.app.mount(panel)

            assert child in panel._content_container.children
            assert panel.title == "Test"
            assert panel.icon == "⚙️"
            assert panel.collapsed is False


class TestCollapsiblePanelInteractions:
    """Тесты взаимодействий CollapsiblePanel."""

    async def test_toggle_button_pressed(self) -> None:
        """Нажатие кнопки toggle переключает панель."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            panel = CollapsiblePanel(title="Test")
            await pilot.app.mount(panel)

            panel.on_button_pressed(Button.Pressed(panel._toggle_button))
            assert panel.collapsed is True

    async def test_click_on_header_toggles(self) -> None:
        """Клик по header сворачивает/разворачивает панель."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            panel = CollapsiblePanel(title="Test")
            await pilot.app.mount(panel)

            header = panel.query_one(".panel-header", Container)
            mock_widget = MagicMock()
            mock_widget.ancestors_with_self = [header, panel]
            event = MagicMock()
            event.widget = mock_widget

            panel.on_click(event)
            assert panel.collapsed is True

    async def test_toggle_changes_state(self) -> None:
        """toggle меняет состояние collapsed."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            panel = CollapsiblePanel(title="Test")
            await pilot.app.mount(panel)

            panel.toggle()
            assert panel.collapsed is True
            panel.toggle()
            assert panel.collapsed is False

    async def test_expand_and_collapse(self) -> None:
        """expand и collapse устанавливают состояние."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            panel = CollapsiblePanel(title="Test", collapsed=True)
            await pilot.app.mount(panel)

            panel.expand()
            assert panel.collapsed is False

            panel.collapse()
            assert panel.collapsed is True


class TestCollapsiblePanelWatchers:
    """Тесты watch_* методов."""

    async def test_watch_collapsed_updates_ui(self) -> None:
        """watch_collapsed обновляет UI и отправляет событие."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            panel = CollapsiblePanel(title="Test")
            await pilot.app.mount(panel)

            with patch.object(panel, "post_message") as post_mock:
                panel.watch_collapsed(True)

            assert panel._content_container.has_class("hidden")
            assert panel.has_class("collapsed")
            assert "▶" in str(panel._toggle_button.label)
            post_mock.assert_called_once()
            assert post_mock.call_args[0][0].collapsed is True

    async def test_watch_title_updates_widget(self) -> None:
        """watch_title обновляет виджет заголовка."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            panel = CollapsiblePanel(title="Test")
            await pilot.app.mount(panel)

            panel.watch_title("Новый заголовок")
            assert "Новый заголовок" in str(panel._title_widget.render())

    async def test_watch_icon_updates_widget(self) -> None:
        """watch_icon обновляет виджет иконки."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            panel = CollapsiblePanel(title="Test", icon="⚙️")
            await pilot.app.mount(panel)

            panel.watch_icon("🔧")
            assert "🔧" in str(panel._icon_widget.render())

    async def test_watch_collapsed_without_widgets(self) -> None:
        """watch_collapsed без виджетов не падает."""
        panel = CollapsiblePanel(title="Test")
        panel._content_container = None
        panel._toggle_button = None
        panel.watch_collapsed(True)


class TestCollapsiblePanelContent:
    """Тесты свойства content."""

    async def test_content_property(self) -> None:
        """content возвращает контейнер контента."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            panel = CollapsiblePanel(title="Test")
            await pilot.app.mount(panel)

            assert panel.content is panel._content_container


class TestAccordionPanel:
    """Тесты для AccordionPanel."""

    def test_init_allow_multiple(self) -> None:
        """Инициализация с allow_multiple."""
        group = AccordionPanel(allow_multiple=True)
        assert group._allow_multiple is True

    async def test_toggled_collapses_other_panels(self) -> None:
        """При разворачивании одной панели остальные сворачиваются."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            panel1 = CollapsiblePanel(title="Panel 1")
            panel2 = CollapsiblePanel(title="Panel 2")
            group = AccordionPanel(panel1, panel2)
            await pilot.app.mount(group)

            panel2.expand()
            event = CollapsiblePanel.Toggled(panel=panel2, collapsed=False)
            group.on_collapsible_panel_toggled(event)

            assert panel1.collapsed is True
            assert panel2.collapsed is False

    async def test_toggled_allow_multiple_no_collapse(self) -> None:
        """При allow_multiple другие панели не сворачиваются."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            panel1 = CollapsiblePanel(title="Panel 1")
            panel2 = CollapsiblePanel(title="Panel 2")
            group = AccordionPanel(panel1, panel2, allow_multiple=True)
            await pilot.app.mount(group)

            panel1.expand()
            panel2.expand()
            event = CollapsiblePanel.Toggled(panel=panel2, collapsed=False)
            group.on_collapsible_panel_toggled(event)

            assert panel1.collapsed is False
            assert panel2.collapsed is False

    async def test_toggled_collapsed_event_ignored(self) -> None:
        """Событие сворачивания панели игнорируется."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            panel1 = CollapsiblePanel(title="Panel 1")
            panel2 = CollapsiblePanel(title="Panel 2")
            group = AccordionPanel(panel1, panel2)
            await pilot.app.mount(group)

            panel1.expand()
            panel2.expand()
            event = CollapsiblePanel.Toggled(panel=panel2, collapsed=True)
            group.on_collapsible_panel_toggled(event)

            assert panel1.collapsed is False

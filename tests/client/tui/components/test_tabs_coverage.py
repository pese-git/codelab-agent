"""Тесты для покрытия tabs.py."""

from __future__ import annotations

from textual.app import App
from textual.widgets import Button, Label

from codelab.client.tui.components.tabs import (
    Tab,
    TabBar,
    TabbedContainer,
    TabData,
    TabPanel,
)


class ThemedApp(App):
    """Тестовое приложение с CSS переменными для компонентов."""

    def get_theme_variable_defaults(self) -> dict[str, str]:
        """Добавляет недостающие CSS переменные для компонентов."""
        return {
            "background-secondary": "#24283b",
            "background-tertiary": "#1f2335",
        }


class TestTabData:
    """Тесты для TabData."""

    def test_defaults(self) -> None:
        """TabData использует значения по умолчанию."""
        data = TabData(id="test", label="Test")
        assert data.closable is True
        assert data.icon is None

    def test_custom(self) -> None:
        """TabData сохраняет все значения."""
        data = TabData(id="test", label="Test", closable=False, icon="⚙")
        assert data.closable is False
        assert data.icon == "⚙"


class TestTab:
    """Тесты для Tab."""

    def test_init_default_id(self) -> None:
        """ID генерируется из данных таба."""
        data = TabData(id="test", label="Test")
        tab = Tab(data)
        assert tab.id == "tab-test"
        assert tab.tab_id == "test"

    def test_init_custom_id(self) -> None:
        """Можно передать явный ID."""
        data = TabData(id="test", label="Test")
        tab = Tab(data, id="custom")
        assert tab.id == "custom"

    def test_init_closable_class(self) -> None:
        """Closable таб получает CSS класс."""
        data = TabData(id="test", label="Test", closable=True)
        tab = Tab(data)
        assert tab.has_class("-closable")

    def test_init_not_closable(self) -> None:
        """Не-closable таб не имеет класс."""
        data = TabData(id="test", label="Test", closable=False)
        tab = Tab(data)
        assert not tab.has_class("-closable")

    async def test_compose_with_icon(self) -> None:
        """compose с иконкой создаёт три виджета."""
        class TestApp(ThemedApp):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            data = TabData(id="test", label="Test", icon="⚙")
            tab = Tab(data)
            await pilot.app.mount(tab)
            await pilot.pause()
            labels = tab.query(Label)
            buttons = tab.query(Button)
            assert len(labels) == 2
            assert len(buttons) == 1

    async def test_compose_without_icon(self) -> None:
        """compose без иконки создаёт label и кнопку."""
        class TestApp(ThemedApp):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            data = TabData(id="test", label="Test")
            tab = Tab(data)
            await pilot.app.mount(tab)
            await pilot.pause()
            labels = tab.query(Label)
            assert len(labels) == 1

    def test_watch_is_active(self) -> None:
        """watch_is_active управляет CSS классом."""
        data = TabData(id="test", label="Test")
        tab = Tab(data)
        tab.watch_is_active(True)
        assert tab.has_class("-active")
        tab.watch_is_active(False)
        assert not tab.has_class("-active")

    async def test_on_click(self) -> None:
        """Клик на таб отправляет Clicked."""
        from unittest.mock import patch

        class TestApp(ThemedApp):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            data = TabData(id="test", label="Test")
            tab = Tab(data)
            await pilot.app.mount(tab)
            posted: list[Tab.Clicked] = []
            with patch.object(tab, "post_message", side_effect=posted.append):
                await tab.on_click()
            assert len(posted) == 1
            assert posted[0].tab_id == "test"

    async def test_on_button_pressed_close(self) -> None:
        """Клик на кнопку закрытия отправляет CloseRequested."""
        from unittest.mock import patch

        class TestApp(ThemedApp):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            data = TabData(id="test", label="Test")
            tab = Tab(data)
            await pilot.app.mount(tab)
            posted: list[Tab.CloseRequested] = []
            button = Button("×", classes="tab-close")
            with patch.object(tab, "post_message", side_effect=posted.append):
                tab.on_button_pressed(Button.Pressed(button))
            assert len(posted) == 1
            assert posted[0].tab_id == "test"

    async def test_on_button_pressed_other(self) -> None:
        """Клик на другую кнопку не отправляет CloseRequested."""
        from unittest.mock import patch

        class TestApp(ThemedApp):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            data = TabData(id="test", label="Test")
            tab = Tab(data)
            await pilot.app.mount(tab)
            posted: list[Tab.CloseRequested] = []
            button = Button("?", classes="other")
            with patch.object(tab, "post_message", side_effect=posted.append):
                tab.on_button_pressed(Button.Pressed(button))
            assert len(posted) == 0


class TestTabBar:
    """Тесты для TabBar."""

    def test_init_defaults(self) -> None:
        """Инициализация TabBar."""
        bar = TabBar()
        assert bar.id == "tab-bar"
        assert bar._tabs == {}
        assert bar._tab_order == []
        assert bar.active_tab is None

    def test_tabs_property(self) -> None:
        """tabs возвращает копию порядка табов."""
        bar = TabBar()
        bar._tab_order = ["a", "b"]
        assert bar.tabs == ["a", "b"]
        bar.tabs.append("c")
        assert bar._tab_order == ["a", "b"]

    async def test_add_tab(self) -> None:
        """add_tab добавляет таб и активирует его."""
        class TestApp(ThemedApp):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            bar = TabBar()
            await pilot.app.mount(bar)
            tab = bar.add_tab("test", "Test", closable=False, icon="⚙")
            assert bar.tabs == ["test"]
            assert bar.active_tab == "test"
            assert bar._tabs["test"] is tab
            assert tab.is_active is True

    async def test_add_tab_not_activate(self) -> None:
        """add_tab без активации не меняет активный таб."""
        class TestApp(ThemedApp):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            bar = TabBar()
            await pilot.app.mount(bar)
            bar.add_tab("first", "First")
            bar.add_tab("second", "Second", activate=False)
            assert bar.active_tab == "first"

    async def test_remove_tab(self) -> None:
        """remove_tab удаляет таб."""
        class TestApp(ThemedApp):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            bar = TabBar()
            await pilot.app.mount(bar)
            bar.add_tab("a", "A")
            bar.add_tab("b", "B")
            result = bar.remove_tab("a")
            assert result is True
            assert "a" not in bar._tabs
            assert "a" not in bar._tab_order

    async def test_remove_active_tab_activates_neighbor(self) -> None:
        """Удаление активного таба активирует соседний."""
        class TestApp(ThemedApp):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            bar = TabBar()
            await pilot.app.mount(bar)
            bar.add_tab("a", "A")
            bar.add_tab("b", "B")
            bar.remove_tab("b")
            assert bar.active_tab == "a"

    async def test_remove_last_tab_clears_active(self) -> None:
        """Удаление последнего таба сбрасывает active_tab."""
        class TestApp(ThemedApp):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            bar = TabBar()
            await pilot.app.mount(bar)
            bar.add_tab("a", "A")
            bar.remove_tab("a")
            assert bar.active_tab is None

    def test_remove_tab_not_found(self) -> None:
        """remove_tab для несуществующего возвращает False."""
        bar = TabBar()
        assert bar.remove_tab("missing") is False

    async def test_activate_tab(self) -> None:
        """activate_tab переключает активный таб."""
        class TestApp(ThemedApp):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            bar = TabBar()
            await pilot.app.mount(bar)
            bar.add_tab("a", "A", activate=False)
            bar.add_tab("b", "B", activate=False)
            result = bar.activate_tab("b")
            assert result is True
            assert bar.active_tab == "b"
            assert bar._tabs["b"].is_active is True
            assert bar._tabs["a"].is_active is False

    def test_activate_tab_not_found(self) -> None:
        """activate_tab для несуществующего возвращает False."""
        bar = TabBar()
        assert bar.activate_tab("missing") is False

    async def test_on_tab_clicked(self) -> None:
        """Клик на таб активирует его."""
        class TestApp(ThemedApp):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            bar = TabBar()
            await pilot.app.mount(bar)
            bar.add_tab("a", "A")
            bar.add_tab("b", "B", activate=False)
            bar.on_tab_clicked(Tab.Clicked("b"))
            assert bar.active_tab == "b"

    async def test_on_tab_close_requested(self) -> None:
        """Запрос закрытия удаляет таб."""
        class TestApp(ThemedApp):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            bar = TabBar()
            await pilot.app.mount(bar)
            bar.add_tab("a", "A")
            bar.on_tab_close_requested(Tab.CloseRequested("a"))
            assert "a" not in bar._tabs

    async def test_action_previous_tab(self) -> None:
        """Предыдущий таб переключает активный."""
        class TestApp(ThemedApp):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            bar = TabBar()
            await pilot.app.mount(bar)
            bar.add_tab("a", "A")
            bar.add_tab("b", "B")
            bar.action_previous_tab()
            assert bar.active_tab == "a"

    def test_action_previous_tab_empty(self) -> None:
        """Предыдущий таб в пустом баре не падает."""
        bar = TabBar()
        bar.action_previous_tab()
        assert bar.active_tab is None

    def test_action_previous_tab_no_active(self) -> None:
        """Предыдущий таб без активного не падает."""
        bar = TabBar()
        bar._tab_order = ["a"]
        bar.action_previous_tab()
        assert bar.active_tab is None

    async def test_action_next_tab(self) -> None:
        """Следующий таб переключает активный."""
        class TestApp(ThemedApp):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            bar = TabBar()
            await pilot.app.mount(bar)
            bar.add_tab("a", "A")
            bar.add_tab("b", "B", activate=False)
            bar.action_next_tab()
            assert bar.active_tab == "b"

    def test_action_next_tab_empty(self) -> None:
        """Следующий таб в пустом баре не падает."""
        bar = TabBar()
        bar.action_next_tab()
        assert bar.active_tab is None


class TestTabPanel:
    """Тесты для TabPanel."""

    def test_init_defaults(self) -> None:
        """Инициализация TabPanel."""
        panel = TabPanel()
        assert panel.id == "tab-panel"
        assert panel._panels == {}
        assert panel.active_tab is None

    async def test_add_panel(self) -> None:
        """add_panel добавляет контент."""
        class TestApp(ThemedApp):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            panel = TabPanel()
            await pilot.app.mount(panel)
            content = panel.add_panel("test")
            assert panel._panels["test"] is content
            assert content.id == "panel-test"

    async def test_add_panel_active(self) -> None:
        """add_panel активирует панель если active_tab совпадает."""
        class TestApp(ThemedApp):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            panel = TabPanel()
            await pilot.app.mount(panel)
            panel.active_tab = "test"
            content = panel.add_panel("test")
            assert content.has_class("-active")

    async def test_remove_panel(self) -> None:
        """remove_panel удаляет панель."""
        class TestApp(ThemedApp):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            panel = TabPanel()
            await pilot.app.mount(panel)
            panel.add_panel("test")
            result = panel.remove_panel("test")
            assert result is True
            assert "test" not in panel._panels

    def test_remove_panel_not_found(self) -> None:
        """remove_panel для несуществующей возвращает False."""
        panel = TabPanel()
        assert panel.remove_panel("missing") is False

    async def test_watch_active_tab(self) -> None:
        """watch_active_tab переключает CSS класс."""
        class TestApp(ThemedApp):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            panel = TabPanel()
            await pilot.app.mount(panel)
            panel.add_panel("a")
            panel.add_panel("b")
            panel.watch_active_tab("b")
            assert panel._panels["b"].has_class("-active")
            assert not panel._panels["a"].has_class("-active")

    def test_get_panel(self) -> None:
        """get_panel возвращает панель по ID."""
        panel = TabPanel()
        panel._panels["test"] = object()  # type: ignore[assignment]
        assert panel.get_panel("test") is panel._panels["test"]
        assert panel.get_panel("missing") is None


class TestTabbedContainer:
    """Тесты для TabbedContainer."""

    def test_init(self) -> None:
        """Инициализация создаёт TabBar и TabPanel."""
        container = TabbedContainer()
        assert isinstance(container.tab_bar, TabBar)
        assert isinstance(container.tab_panel, TabPanel)

    def test_compose(self) -> None:
        """compose создаёт TabBar и TabPanel."""
        container = TabbedContainer()
        children = list(container.compose())
        assert children[0] is container.tab_bar
        assert children[1] is container.tab_panel

    async def test_add_tab(self) -> None:
        """add_tab добавляет таб и панель."""
        class TestApp(ThemedApp):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            container = TabbedContainer()
            await pilot.app.mount(container)
            container.add_tab("test", "Test")
            assert container.tab_bar.tabs == ["test"]
            assert container.tab_panel.get_panel("test") is not None
            assert container.tab_panel.active_tab == "test"

    async def test_add_tab_not_activate(self) -> None:
        """add_tab с activate=False не активирует панель."""
        class TestApp(ThemedApp):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            container = TabbedContainer()
            await pilot.app.mount(container)
            container.add_tab("a", "A")
            container.add_tab("b", "B", activate=False)
            assert container.tab_panel.active_tab == "a"

    async def test_remove_tab(self) -> None:
        """remove_tab удаляет таб и панель."""
        class TestApp(ThemedApp):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            container = TabbedContainer()
            await pilot.app.mount(container)
            container.add_tab("a", "A")
            container.add_tab("b", "B")
            result = container.remove_tab("a")
            assert result is True
            assert "a" not in container.tab_bar._tabs
            assert "a" not in container.tab_panel._panels

    def test_remove_tab_not_found(self) -> None:
        """remove_tab для несуществующего возвращает False."""
        container = TabbedContainer()
        assert container.remove_tab("missing") is False

    def test_on_tab_bar_tab_activated(self) -> None:
        """Активация таба в TabBar синхронизирует TabPanel."""
        container = TabbedContainer()
        container.on_tab_bar_tab_activated(TabBar.TabActivated("test"))
        assert container.tab_panel.active_tab == "test"

    def test_on_tab_bar_tab_closed(self) -> None:
        """Закрытие таба в TabBar удаляет панель."""
        from unittest.mock import MagicMock

        container = TabbedContainer()
        mock_panel = MagicMock()
        container.tab_panel._panels["test"] = mock_panel
        container.on_tab_bar_tab_closed(TabBar.TabClosed("test"))
        assert "test" not in container.tab_panel._panels
        mock_panel.remove.assert_called_once()

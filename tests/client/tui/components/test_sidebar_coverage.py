"""Тесты покрытия для Sidebar компонента.

Проверяют отображение списка сессий, фильтрацию и навигацию.
"""

from __future__ import annotations

from typing import Any

from textual import events
from textual.app import App

from codelab.client.presentation.observable import Observable
from codelab.client.presentation.ui_view_model import SidebarTab
from codelab.client.tui.components.search_input import SearchInput
from codelab.client.tui.components.sidebar import Sidebar


class FakeSession:
    """Фейковая сессия с атрибутами."""

    def __init__(self, session_id: str, title: str) -> None:
        self.sessionId = session_id
        self.id = session_id
        self.title = title


class FakeSessionViewModel:
    """Фейковый SessionViewModel для тестов Sidebar."""

    def __init__(self) -> None:
        self.sessions: Observable[list[Any]] = Observable([])
        self.selected_session_id: Observable[str | None] = Observable(None)
        self.is_loading_sessions: Observable[bool] = Observable(False)


class FakeUIViewModel:
    """Фейковый UIViewModel для тестов Sidebar."""

    def __init__(self) -> None:
        self.sidebar_tab: Observable[SidebarTab] = Observable(SidebarTab.SESSIONS)
        self.sessions_expanded: Observable[bool] = Observable(True)
        self.files_expanded: Observable[bool] = Observable(True)

    def toggle_active_sidebar_section(self) -> bool:
        """Переключает развернутость активной секции."""
        if self.sidebar_tab.value == SidebarTab.SESSIONS:
            self.sessions_expanded.value = not self.sessions_expanded.value
            return self.sessions_expanded.value
        if self.sidebar_tab.value == SidebarTab.FILES:
            self.files_expanded.value = not self.files_expanded.value
            return self.files_expanded.value
        return True


class TestSidebar:
    """Тесты для Sidebar."""

    async def test_init_subscribes_to_view_model(self) -> None:
        """Инициализация подписывается на SessionViewModel."""
        session_vm = FakeSessionViewModel()
        ui_vm = FakeUIViewModel()

        sidebar = Sidebar(session_vm, ui_vm)

        assert sidebar.session_vm is session_vm
        assert sidebar.ui_vm is ui_vm
        assert sidebar._selected_index == 0

    async def test_compose_and_mount(self) -> None:
        """Компонент создаёт поле поиска и список сессий."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            session_vm = FakeSessionViewModel()
            sidebar = Sidebar(session_vm)
            await pilot.app.mount(sidebar)

            assert sidebar.query_one("#sidebar-search") is not None
            assert sidebar.query_one("#sidebar-sessions-list") is not None

    async def test_on_sessions_changed_updates_display(self) -> None:
        """Изменение списка сессий обновляет отображение."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            session_vm = FakeSessionViewModel()
            sidebar = Sidebar(session_vm)
            await pilot.app.mount(sidebar)

            session_vm.sessions.value = [
                {"sessionId": "s1", "title": "First"},
                {"sessionId": "s2", "title": "Second"},
            ]

            text = sidebar.query_one("#sidebar-sessions-list")._Static__content
            assert "First" in text
            assert "Second" in text

    async def test_on_selected_session_changed_syncs_index(self) -> None:
        """Изменение выбранной сессии синхронизирует выделение."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            session_vm = FakeSessionViewModel()
            sidebar = Sidebar(session_vm)
            await pilot.app.mount(sidebar)

            session_vm.sessions.value = [
                {"sessionId": "s1", "title": "First"},
                {"sessionId": "s2", "title": "Second"},
            ]
            session_vm.selected_session_id.value = "s2"

            assert sidebar._selected_index == 1

    async def test_on_loading_changed(self) -> None:
        """Статус загрузки отображается в панели."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            session_vm = FakeSessionViewModel()
            sidebar = Sidebar(session_vm)
            await pilot.app.mount(sidebar)

            session_vm.is_loading_sessions.value = True

            text = sidebar.query_one("#sidebar-sessions-list")._Static__content
            assert "загружаются" in text

    async def test_on_sidebar_tab_changed(self) -> None:
        """Смена вкладки sidebar меняет отображение."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            session_vm = FakeSessionViewModel()
            ui_vm = FakeUIViewModel()
            sidebar = Sidebar(session_vm, ui_vm)
            await pilot.app.mount(sidebar)

            ui_vm.sidebar_tab.value = SidebarTab.FILES

            text = sidebar.query_one("#sidebar-sessions-list")._Static__content
            assert "Файлы отображаются" in text

    async def test_on_sessions_expanded_changed(self) -> None:
        """Сворачивание секции сессий меняет отображение."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            session_vm = FakeSessionViewModel()
            ui_vm = FakeUIViewModel()
            sidebar = Sidebar(session_vm, ui_vm)
            await pilot.app.mount(sidebar)

            session_vm.sessions.value = [{"sessionId": "s1", "title": "First"}]
            ui_vm.sessions_expanded.value = False

            text = sidebar.query_one("#sidebar-sessions-list")._Static__content
            assert "свернуто" in text

    async def test_search_filter(self) -> None:
        """Фильтрация сессий по поисковому запросу."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            session_vm = FakeSessionViewModel()
            sidebar = Sidebar(session_vm)
            await pilot.app.mount(sidebar)

            session_vm.sessions.value = [
                {"sessionId": "s1", "title": "Alpha"},
                {"sessionId": "s2", "title": "Beta"},
            ]
            sidebar.search_filter = "alp"
            sidebar._update_display()

            text = sidebar.query_one("#sidebar-sessions-list")._Static__content
            assert "Alpha" in text
            assert "Beta" not in text
            assert "Найдено: 1 из 2" in text

    async def test_select_next_and_previous(self) -> None:
        """Навигация вверх/вниз по списку сессий."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            session_vm = FakeSessionViewModel()
            sidebar = Sidebar(session_vm)
            await pilot.app.mount(sidebar)

            session_vm.sessions.value = [
                {"sessionId": "s1", "title": "First"},
                {"sessionId": "s2", "title": "Second"},
            ]

            sidebar.select_next()
            assert sidebar._selected_index == 1

            sidebar.select_next()
            assert sidebar._selected_index == 0

            sidebar.select_previous()
            assert sidebar._selected_index == 1

    async def test_get_selected_session_id(self) -> None:
        """get_selected_session_id возвращает ID выделенной сессии."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            session_vm = FakeSessionViewModel()
            sidebar = Sidebar(session_vm)
            await pilot.app.mount(sidebar)

            session_vm.sessions.value = [
                {"sessionId": "s1", "title": "First"},
            ]

            assert sidebar.get_selected_session_id() == "s1"

            sidebar._selected_index = 5
            assert sidebar.get_selected_session_id() is None

    async def test_update_selected_session(self) -> None:
        """_update_selected_session обновляет ViewModel."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            session_vm = FakeSessionViewModel()
            sidebar = Sidebar(session_vm)
            await pilot.app.mount(sidebar)

            session_vm.sessions.value = [
                {"sessionId": "s1", "title": "First"},
                {"sessionId": "s2", "title": "Second"},
            ]
            sidebar._selected_index = 1
            sidebar._update_selected_session()

            assert session_vm.selected_session_id.value == "s2"

    async def test_key_navigation(self) -> None:
        """Клавиши Up/Down/Enter управляют выбором сессии."""
        from unittest.mock import patch

        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            session_vm = FakeSessionViewModel()
            sidebar = Sidebar(session_vm)
            await pilot.app.mount(sidebar)

            session_vm.sessions.value = [
                {"sessionId": "s1", "title": "First"},
                {"sessionId": "s2", "title": "Second"},
            ]
            sidebar.focus()

            await pilot.press("down")
            assert sidebar._selected_index == 1

            await pilot.press("up")
            assert sidebar._selected_index == 0

            posted: list[object] = []
            with patch.object(sidebar, "post_message", side_effect=posted.append):
                sidebar.on_key(events.Key(key="enter", character=""))
            assert len(posted) == 1
            assert isinstance(posted[0], Sidebar.SessionSelected)

    async def test_key_space_toggles_section(self) -> None:
        """Пробел переключает активную секцию."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            session_vm = FakeSessionViewModel()
            ui_vm = FakeUIViewModel()
            sidebar = Sidebar(session_vm, ui_vm)
            await pilot.app.mount(sidebar)
            sidebar.focus()

            await pilot.press("space")
            assert ui_vm.sessions_expanded.value is False

    async def test_render_text_files_tab(self) -> None:
        """_render_text показывает заглушку вкладки файлов."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            session_vm = FakeSessionViewModel()
            ui_vm = FakeUIViewModel()
            sidebar = Sidebar(session_vm, ui_vm)
            await pilot.app.mount(sidebar)

            ui_vm.sidebar_tab.value = SidebarTab.FILES
            text = sidebar._render_text()

            assert "Файлы отображаются" in text
            assert "Files" in text

    async def test_render_text_settings_tab(self) -> None:
        """_render_text показывает заглушку вкладки настроек."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            session_vm = FakeSessionViewModel()
            ui_vm = FakeUIViewModel()
            sidebar = Sidebar(session_vm, ui_vm)
            await pilot.app.mount(sidebar)

            ui_vm.sidebar_tab.value = SidebarTab.SETTINGS
            text = sidebar._render_text()

            assert "Settings" in text
            assert "F1" in text

    async def test_render_text_empty_sessions(self) -> None:
        """_render_text показывает состояние без сессий."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            session_vm = FakeSessionViewModel()
            sidebar = Sidebar(session_vm)
            await pilot.app.mount(sidebar)

            text = sidebar._render_text()
            assert "Сессий пока нет" in text

    async def test_render_text_collapsed(self) -> None:
        """_render_text показывает свернутое состояние."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            session_vm = FakeSessionViewModel()
            ui_vm = FakeUIViewModel()
            sidebar = Sidebar(session_vm, ui_vm)
            await pilot.app.mount(sidebar)

            session_vm.sessions.value = [{"sessionId": "s1", "title": "First"}]
            ui_vm.sessions_expanded.value = False
            text = sidebar._render_text()

            assert "свернуто" in text

    async def test_sync_selected_index(self) -> None:
        """_sync_selected_index синхронизирует индекс с выбранной сессией."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            session_vm = FakeSessionViewModel()
            sidebar = Sidebar(session_vm)
            await pilot.app.mount(sidebar)

            session_vm.sessions.value = [
                {"sessionId": "s1", "title": "First"},
                {"sessionId": "s2", "title": "Second"},
            ]
            session_vm.selected_session_id.value = "s2"
            sidebar._sync_selected_index()

            assert sidebar._selected_index == 1

    async def test_sync_selected_index_not_in_filtered(self) -> None:
        """Если выбранная сессия не в отфильтрованном списке, индекс сбрасывается."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            session_vm = FakeSessionViewModel()
            sidebar = Sidebar(session_vm)
            await pilot.app.mount(sidebar)

            session_vm.sessions.value = [
                {"sessionId": "s1", "title": "First"},
                {"sessionId": "s2", "title": "Second"},
            ]
            sidebar.search_filter = "first"
            session_vm.selected_session_id.value = "s2"
            sidebar._sync_selected_index()

            assert sidebar._selected_index == 0

    def test_extract_session_id(self) -> None:
        """_extract_session_id поддерживает dict и объект."""
        assert Sidebar._extract_session_id({"sessionId": "s1"}) == "s1"
        assert Sidebar._extract_session_id({"id": "s2"}) == "s2"
        assert Sidebar._extract_session_id({}) is None
        assert Sidebar._extract_session_id(FakeSession("s3", "Title")) == "s3"

    def test_extract_session_title(self) -> None:
        """_extract_session_title возвращает title или sessionId."""
        assert Sidebar._extract_session_title({"sessionId": "s1", "title": "My"}) == "My"
        assert Sidebar._extract_session_title({"sessionId": "s2"}) == "s2"
        assert Sidebar._extract_session_title({}) == "unknown-session"
        assert Sidebar._extract_session_title(FakeSession("s3", "Title")) == "Title"

    def test_extract_session_title_fallback(self) -> None:
        """_extract_session_title использует id если sessionId отсутствует."""
        assert Sidebar._extract_session_title({"id": "s4"}) == "s4"

    async def test_search_input_events(self) -> None:
        """События SearchInput обновляют фильтр и сбрасывают выделение."""
        class TestApp(App):
            pass

        app = TestApp()
        async with app.run_test() as pilot:
            session_vm = FakeSessionViewModel()
            sidebar = Sidebar(session_vm)
            await pilot.app.mount(sidebar)

            sidebar._selected_index = 3
            sidebar.on_search_input_search_changed(
                SearchInput.SearchChanged(value="test")
            )
            assert sidebar.search_filter == "test"
            assert sidebar._selected_index == 0

            sidebar.on_search_input_search_cleared(SearchInput.SearchCleared())
            assert sidebar.search_filter == ""
            assert sidebar._selected_index == 0

    def test_tabs_header_without_ui_vm(self) -> None:
        """_tabs_header возвращает пустую строку без UIViewModel."""
        session_vm = FakeSessionViewModel()
        sidebar = Sidebar(session_vm)
        assert sidebar._tabs_header() == ""

    def test_with_tabs_header(self) -> None:
        """_with_tabs_header добавляет шапку если UI-состояние доступно."""
        session_vm = FakeSessionViewModel()
        ui_vm = FakeUIViewModel()
        sidebar = Sidebar(session_vm, ui_vm)

        result = sidebar._with_tabs_header("content")
        assert result.startswith("[")
        assert "content" in result

    def test_with_tabs_header_no_header(self) -> None:
        """_with_tabs_header возвращает content если шапки нет."""
        session_vm = FakeSessionViewModel()
        sidebar = Sidebar(session_vm)
        assert sidebar._with_tabs_header("content") == "content"

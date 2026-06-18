"""Тесты для компонента Sidebar с MVVM интеграцией."""

from __future__ import annotations

import pytest

from codelab.client.infrastructure.events.bus import EventBus
from codelab.client.messages import SessionListItem
from codelab.client.presentation.session_view_model import SessionViewModel
from codelab.client.presentation.ui_view_model import SidebarTab, UIViewModel
from codelab.client.tui.components.sidebar import Sidebar


@pytest.fixture
def event_bus() -> EventBus:
    """Создать EventBus для тестов."""
    return EventBus()


@pytest.fixture
def session_view_model(event_bus: EventBus) -> SessionViewModel:
    """Создать SessionViewModel для тестов."""
    coordinator = None
    return SessionViewModel(coordinator=coordinator, event_bus=event_bus, logger=None)


@pytest.fixture
def ui_view_model(event_bus: EventBus) -> UIViewModel:
    """Создать UIViewModel для тестов sidebar вкладок."""

    return UIViewModel(event_bus=event_bus, logger=None)


@pytest.fixture
def sidebar(session_view_model: SessionViewModel) -> Sidebar:
    """Создать Sidebar с SessionViewModel."""
    return Sidebar(session_view_model)


@pytest.fixture
def sidebar_with_ui(
    session_view_model: SessionViewModel,
    ui_view_model: UIViewModel,
) -> Sidebar:
    """Создать Sidebar с SessionViewModel и UIViewModel."""

    return Sidebar(session_view_model, ui_view_model)


def test_sidebar_initializes_with_session_view_model(session_view_model: SessionViewModel) -> None:
    """Проверить что Sidebar инициализируется с SessionViewModel."""
    sidebar = Sidebar(session_view_model)

    assert sidebar.session_vm is session_view_model
    assert sidebar.id == "sidebar"


def test_sidebar_displays_loading_message_when_loading(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
) -> None:
    """Проверить что Sidebar показывает сообщение загрузки."""
    # Включить загрузку
    session_view_model.is_loading_sessions.value = True

    rendered = sidebar._render_text()
    assert "загружаются" in rendered


def test_sidebar_displays_empty_message_when_no_sessions(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
) -> None:
    """Проверить что Sidebar показывает сообщение пустого списка."""
    # Не загружаем сессии
    session_view_model.sessions.value = []
    session_view_model.is_loading_sessions.value = False

    rendered = sidebar._render_text()
    assert "нет" in rendered


def test_sidebar_displays_sessions_list(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
) -> None:
    """Проверить что Sidebar отображает список сессий."""
    sessions = [
        SessionListItem(sessionId="sess_1", cwd="/tmp", title="Session 1"),
        SessionListItem(sessionId="sess_2", cwd="/tmp", title="Session 2"),
    ]

    session_view_model.sessions.value = sessions
    session_view_model.is_loading_sessions.value = False

    rendered = sidebar._render_text()
    assert "Session 1" in rendered
    assert "Session 2" in rendered


def test_sidebar_marks_selected_session(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
) -> None:
    """Проверить что Sidebar отмечает выбранную сессию звездочкой."""
    sessions = [
        SessionListItem(sessionId="sess_1", cwd="/tmp", title="Session 1"),
        SessionListItem(sessionId="sess_2", cwd="/tmp", title="Session 2"),
    ]

    session_view_model.sessions.value = sessions
    session_view_model.selected_session_id.value = "sess_1"
    session_view_model.is_loading_sessions.value = False

    rendered = sidebar._render_text()
    # Проверить что первая сессия отмечена звездочкой
    lines = rendered.split("\n")
    # Найти линию с Session 1
    for line in lines:
        if "Session 1" in line:
            assert "*" in line
        elif "Session 2" in line:
            assert "*" not in line


def test_sidebar_marks_current_selection_with_cursor(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
) -> None:
    """Проверить что Sidebar отмечает текущее выделение курсором."""
    sessions = [
        SessionListItem(sessionId="sess_1", cwd="/tmp", title="Session 1"),
        SessionListItem(sessionId="sess_2", cwd="/tmp", title="Session 2"),
    ]

    session_view_model.sessions.value = sessions
    session_view_model.selected_session_id.value = "sess_1"
    session_view_model.is_loading_sessions.value = False

    # Первая сессия уже выбрана по умолчанию
    sidebar._selected_index = 0

    rendered = sidebar._render_text()
    lines = rendered.split("\n")

    # Проверяем курсор на строке с первой сессией независимо от заголовков.
    for line in lines:
        if "Session 1" in line:
            assert ">" in line
            break


def test_sidebar_select_next_changes_selection(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
) -> None:
    """Проверить что select_next переходит к следующей сессии."""
    sessions = [
        SessionListItem(sessionId="sess_1", cwd="/tmp", title="Session 1"),
        SessionListItem(sessionId="sess_2", cwd="/tmp", title="Session 2"),
    ]

    session_view_model.sessions.value = sessions
    session_view_model.selected_session_id.value = "sess_1"

    sidebar._selected_index = 0
    sidebar.select_next()

    assert sidebar.get_selected_session_id() == "sess_2"
    assert session_view_model.selected_session_id.value == "sess_2"


def test_sidebar_select_next_wraps_around(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
) -> None:
    """Проверить что select_next переходит на первую при конце списка."""
    sessions = [
        SessionListItem(sessionId="sess_1", cwd="/tmp", title="Session 1"),
        SessionListItem(sessionId="sess_2", cwd="/tmp", title="Session 2"),
    ]

    session_view_model.sessions.value = sessions
    session_view_model.selected_session_id.value = "sess_2"

    sidebar._selected_index = 1
    sidebar.select_next()

    assert sidebar.get_selected_session_id() == "sess_1"


def test_sidebar_select_previous_changes_selection(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
) -> None:
    """Проверить что select_previous переходит к предыдущей сессии."""
    sessions = [
        SessionListItem(sessionId="sess_1", cwd="/tmp", title="Session 1"),
        SessionListItem(sessionId="sess_2", cwd="/tmp", title="Session 2"),
    ]

    session_view_model.sessions.value = sessions
    session_view_model.selected_session_id.value = "sess_2"

    sidebar._selected_index = 1
    sidebar.select_previous()

    assert sidebar.get_selected_session_id() == "sess_1"
    assert session_view_model.selected_session_id.value == "sess_1"


def test_sidebar_select_previous_wraps_around(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
) -> None:
    """Проверить что select_previous переходит на последнюю при начале списка."""
    sessions = [
        SessionListItem(sessionId="sess_1", cwd="/tmp", title="Session 1"),
        SessionListItem(sessionId="sess_2", cwd="/tmp", title="Session 2"),
    ]

    session_view_model.sessions.value = sessions
    session_view_model.selected_session_id.value = "sess_1"

    sidebar._selected_index = 0
    sidebar.select_previous()

    assert sidebar.get_selected_session_id() == "sess_2"


def test_sidebar_syncs_selected_index_with_view_model(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
) -> None:
    """Проверить что Sidebar синхронизирует индекс с ViewModel."""
    sessions = [
        SessionListItem(sessionId="sess_1", cwd="/tmp", title="Session 1"),
        SessionListItem(sessionId="sess_2", cwd="/tmp", title="Session 2"),
        SessionListItem(sessionId="sess_3", cwd="/tmp", title="Session 3"),
    ]

    session_view_model.sessions.value = sessions
    session_view_model.selected_session_id.value = "sess_3"

    sidebar._sync_selected_index()

    assert sidebar._selected_index == 2
    assert sidebar.get_selected_session_id() == "sess_3"


def test_sidebar_handles_session_list_changes(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
) -> None:
    """Проверить что Sidebar обновляется при изменении списка сессий."""
    sessions_v1 = [
        SessionListItem(sessionId="sess_1", cwd="/tmp", title="Session 1"),
    ]

    session_view_model.sessions.value = sessions_v1
    rendered_v1 = sidebar._render_text()
    assert "Session 1" in rendered_v1

    sessions_v2 = [
        SessionListItem(sessionId="sess_1", cwd="/tmp", title="Session 1"),
        SessionListItem(sessionId="sess_2", cwd="/tmp", title="Session 2"),
        SessionListItem(sessionId="sess_3", cwd="/tmp", title="Session 3"),
    ]

    session_view_model.sessions.value = sessions_v2
    rendered_v2 = sidebar._render_text()
    assert "Session 1" in rendered_v2
    assert "Session 2" in rendered_v2
    assert "Session 3" in rendered_v2


def test_sidebar_renders_tabs_when_ui_view_model_is_provided(
    sidebar_with_ui: Sidebar,
) -> None:
    """Проверить, что Sidebar показывает вкладки при наличии UIViewModel."""

    rendered = sidebar_with_ui._render_text()
    assert "Sessions" in rendered
    assert "Files" in rendered
    assert "Settings" in rendered


def test_sidebar_can_render_collapsed_sessions_section(
    sidebar_with_ui: Sidebar,
    ui_view_model: UIViewModel,
) -> None:
    """Проверить отображение свернутой секции sessions."""

    ui_view_model.set_sidebar_tab(SidebarTab.SESSIONS)
    ui_view_model.sessions_expanded.value = False

    rendered = sidebar_with_ui._render_text()
    assert "свернуто" in rendered

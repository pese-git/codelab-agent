"""Тесты для фильтрации сессий в Sidebar через SearchInput."""

from __future__ import annotations

import pytest

from codelab.client.infrastructure.events.bus import EventBus
from codelab.client.messages import SessionListItem
from codelab.client.presentation.session_view_model import SessionViewModel
from codelab.client.tui.components.search_input import SearchInput
from codelab.client.tui.components.sidebar import Sidebar


@pytest.fixture
def event_bus() -> EventBus:
    """Создать EventBus для тестов."""
    return EventBus()


@pytest.fixture
def session_view_model(event_bus: EventBus) -> SessionViewModel:
    """Создать SessionViewModel для тестов."""
    return SessionViewModel(coordinator=None, event_bus=event_bus, logger=None)


@pytest.fixture
def sidebar(session_view_model: SessionViewModel) -> Sidebar:
    """Создать Sidebar с SessionViewModel."""
    return Sidebar(session_view_model)


@pytest.fixture
def sessions() -> list[SessionListItem]:
    """Создать тестовый список сессий."""
    return [
        SessionListItem(sessionId="sess_1", cwd="/tmp", title="Python Project"),
        SessionListItem(sessionId="sess_2", cwd="/tmp", title="JavaScript App"),
        SessionListItem(sessionId="sess_3", cwd="/tmp", title="Python Script"),
        SessionListItem(sessionId="sess_4", cwd="/tmp", title="Go Service"),
        SessionListItem(sessionId="sess_5", cwd="/tmp", title="Rust CLI"),
    ]


def test_sidebar_has_search_filter_reactive_property(sidebar: Sidebar) -> None:
    """Проверить что Sidebar имеет reactive свойство search_filter."""
    assert hasattr(sidebar, "search_filter")
    assert sidebar.search_filter == ""


def test_sidebar_get_filtered_sessions_without_filter(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
    sessions: list[SessionListItem],
) -> None:
    """Проверить что без фильтра возвращаются все сессии."""
    session_view_model.sessions.value = sessions

    filtered = sidebar._get_filtered_sessions()

    assert len(filtered) == 5
    assert filtered == sessions


def test_sidebar_get_filtered_sessions_by_title(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
    sessions: list[SessionListItem],
) -> None:
    """Проверить фильтрацию по названию сессии."""
    session_view_model.sessions.value = sessions
    sidebar.search_filter = "Python"

    filtered = sidebar._get_filtered_sessions()

    assert len(filtered) == 2
    titles = [s.title for s in filtered]
    assert "Python Project" in titles
    assert "Python Script" in titles


def test_sidebar_get_filtered_sessions_case_insensitive(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
    sessions: list[SessionListItem],
) -> None:
    """Проверить что фильтрация регистронезависима."""
    session_view_model.sessions.value = sessions
    sidebar.search_filter = "python"

    filtered = sidebar._get_filtered_sessions()

    assert len(filtered) == 2


def test_sidebar_get_filtered_sessions_by_session_id(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
    sessions: list[SessionListItem],
) -> None:
    """Проверить фильтрацию по sessionId."""
    session_view_model.sessions.value = sessions
    sidebar.search_filter = "sess_3"

    filtered = sidebar._get_filtered_sessions()

    assert len(filtered) == 1
    assert filtered[0].sessionId == "sess_3"


def test_sidebar_get_filtered_sessions_no_match(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
    sessions: list[SessionListItem],
) -> None:
    """Проверить что при отсутствии совпадений возвращается пустой список."""
    session_view_model.sessions.value = sessions
    sidebar.search_filter = "nonexistent"

    filtered = sidebar._get_filtered_sessions()

    assert len(filtered) == 0


def test_sidebar_select_next_uses_filtered_sessions(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
    sessions: list[SessionListItem],
) -> None:
    """Проверить что select_next работает с отфильтрованным списком."""
    session_view_model.sessions.value = sessions
    sidebar.search_filter = "Python"  # 2 сессии: Python Project, Python Script
    sidebar._selected_index = 0  # Явно сбрасываем индекс после установки фильтра

    sidebar.select_next()
    assert sidebar._selected_index == 1

    sidebar.select_next()
    # Должен вернуться к 0 (wrap around для 2 сессий)
    assert sidebar._selected_index == 0


def test_sidebar_select_previous_uses_filtered_sessions(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
    sessions: list[SessionListItem],
) -> None:
    """Проверить что select_previous работает с отфильтрованным списком."""
    session_view_model.sessions.value = sessions
    sidebar.search_filter = "Python"  # 2 сессии
    sidebar._selected_index = 0  # Явно сбрасываем индекс

    # Начинаем с индекса 0, идём назад
    sidebar.select_previous()
    # Должен перейти к последнему элементу (индекс 1)
    assert sidebar._selected_index == 1


def test_sidebar_get_selected_session_id_uses_filtered_sessions(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
    sessions: list[SessionListItem],
) -> None:
    """Проверить что get_selected_session_id возвращает ID из отфильтрованного списка."""
    session_view_model.sessions.value = sessions
    sidebar.search_filter = "Go"  # Только Go Service

    selected_id = sidebar.get_selected_session_id()

    assert selected_id == "sess_4"


def test_sidebar_render_text_shows_filter_count(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
    sessions: list[SessionListItem],
) -> None:
    """Проверить что при активном фильтре показывается счётчик найденных."""
    session_view_model.sessions.value = sessions
    session_view_model.is_loading_sessions.value = False
    sidebar.search_filter = "Python"

    rendered = sidebar._render_text()

    assert "Найдено: 2 из 5" in rendered


def test_sidebar_render_text_shows_no_results_message(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
    sessions: list[SessionListItem],
) -> None:
    """Проверить что показывается сообщение когда ничего не найдено."""
    session_view_model.sessions.value = sessions
    session_view_model.is_loading_sessions.value = False
    sidebar.search_filter = "nonexistent"

    rendered = sidebar._render_text()

    assert "Ничего не найдено" in rendered


def test_sidebar_render_text_shows_filtered_sessions(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
    sessions: list[SessionListItem],
) -> None:
    """Проверить что отображаются только отфильтрованные сессии."""
    session_view_model.sessions.value = sessions
    session_view_model.is_loading_sessions.value = False
    sidebar.search_filter = "Python"

    rendered = sidebar._render_text()

    assert "Python Project" in rendered
    assert "Python Script" in rendered
    assert "JavaScript App" not in rendered
    assert "Go Service" not in rendered


def test_sidebar_on_search_changed_updates_filter(
    sidebar: Sidebar,
) -> None:
    """Проверить что обработчик SearchChanged обновляет фильтр."""
    event = SearchInput.SearchChanged("test query")

    sidebar.on_search_input_search_changed(event)

    assert sidebar.search_filter == "test query"
    assert sidebar._selected_index == 0  # Индекс сбрасывается


def test_sidebar_on_search_cleared_resets_filter(
    sidebar: Sidebar,
) -> None:
    """Проверить что обработчик SearchCleared сбрасывает фильтр."""
    sidebar.search_filter = "some query"
    sidebar._selected_index = 5
    event = SearchInput.SearchCleared()

    sidebar.on_search_input_search_cleared(event)

    assert sidebar.search_filter == ""
    assert sidebar._selected_index == 0


def test_sidebar_partial_match_filter(
    sidebar: Sidebar,
    session_view_model: SessionViewModel,
    sessions: list[SessionListItem],
) -> None:
    """Проверить что фильтр работает с частичным совпадением."""
    session_view_model.sessions.value = sessions
    sidebar.search_filter = "Proj"  # Частичное совпадение с "Project"

    filtered = sidebar._get_filtered_sessions()

    assert len(filtered) == 1
    assert filtered[0].title == "Python Project"

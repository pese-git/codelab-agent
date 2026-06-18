from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from textual.app import App

from codelab.client.messages import SessionListItem
from codelab.client.tui.components.sidebar import Sidebar

if TYPE_CHECKING:
    from codelab.client.presentation.session_view_model import SessionViewModel


class _TestApp(App):
    """Минимальный app для создания Textual контекста в тестах."""

    pass


@pytest.mark.asyncio
async def test_sidebar_select_next_and_previous_wraps(
    mock_session_view_model: SessionViewModel,
) -> None:
    # Создаем app контекст для Textual компонентов
    app = _TestApp()
    async with app.run_test() as _:
        sidebar = Sidebar(mock_session_view_model)
        mock_session_view_model.sessions.value = [
            SessionListItem(sessionId="sess_1", cwd="/tmp"),
            SessionListItem(sessionId="sess_2", cwd="/tmp"),
        ]
        mock_session_view_model.selected_session_id.value = "sess_1"

        sidebar.select_next()
        assert sidebar.get_selected_session_id() == "sess_2"

        sidebar.select_next()
        assert sidebar.get_selected_session_id() == "sess_1"

        sidebar.select_previous()
        assert sidebar.get_selected_session_id() == "sess_2"

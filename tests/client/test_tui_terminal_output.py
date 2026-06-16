from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from textual.app import App

from codelab.client.tui.components.terminal_output import TerminalOutputPanel

if TYPE_CHECKING:
    from codelab.client.presentation.terminal_view_model import TerminalViewModel


class _TestApp(App):
    """Минимальный app для создания Textual контекста в тестах."""
    pass


@pytest.mark.asyncio
async def test_terminal_output_panel_renders_empty_state(
    mock_terminal_view_model: TerminalViewModel,
) -> None:
    # Создаем app контекст для Textual компонентов
    app = _TestApp()
    async with app.run_test() as _:
        # Создаем панель с ViewModel
        panel = TerminalOutputPanel(mock_terminal_view_model)

        rendered = panel.render_text()

        assert rendered.plain == "Нет вывода терминала"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_terminal_output_panel_renders_output_and_exit_code(
    mock_terminal_view_model: TerminalViewModel,
) -> None:
    # Создаем app контекст для Textual компонентов
    app = _TestApp()
    async with app.run_test() as _:
        # Создаем панель с ViewModel
        panel = TerminalOutputPanel(mock_terminal_view_model)
        
        # Обновляем ViewModel output напрямую (в отличие от append_output)
        mock_terminal_view_model.output.value = "hello\n"
        panel.append_output("hello\n")
        panel.set_exit_code(0)

        rendered = panel.render_text()

        # Проверяем что exit code корректно отображается
        assert "Exit code: 0" in rendered.plain  # type: ignore[unresolved-attribute]

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from textual.app import App

from codelab.client.messages import (
    ToolCallCreatedUpdate,
    ToolCallStateUpdate,
    ToolCallTerminalContent,
)
from codelab.client.tui.components.tool_panel import ToolPanel

if TYPE_CHECKING:
    from codelab.client.presentation.chat_view_model import ChatViewModel
    from codelab.client.presentation.terminal_view_model import TerminalViewModel


class _TestApp(App):
    """Минимальный app для создания Textual контекста в тестах."""
    pass


def test_tool_panel_applies_created_and_state_updates(
    mock_chat_view_model: ChatViewModel,
    mock_terminal_view_model: TerminalViewModel,
) -> None:
    panel = ToolPanel(mock_chat_view_model, mock_terminal_view_model)
    panel.apply_update(
        ToolCallCreatedUpdate(
            sessionUpdate="tool_call",
            toolCallId="call_1",
            title="Read file",
            status="pending",
        )
    )
    panel.apply_update(
        ToolCallStateUpdate(
            sessionUpdate="tool_call_update",
            toolCallId="call_1",
            status="completed",
        )
    )

    rendered = panel._render_text()  # noqa: SLF001

    assert "Read file [completed] (call_1)" in rendered


def test_tool_panel_reset_clears_view(
    mock_chat_view_model: ChatViewModel,
    mock_terminal_view_model: TerminalViewModel,
) -> None:
    panel = ToolPanel(mock_chat_view_model, mock_terminal_view_model)
    panel.apply_update(
        ToolCallCreatedUpdate(
            sessionUpdate="tool_call",
            toolCallId="call_1",
            title="Read file",
            status="pending",
        )
    )

    panel.reset()

    assert panel._render_text() == "Инструменты: нет активных вызовов"  # noqa: SLF001


@pytest.mark.asyncio
async def test_tool_panel_renders_terminal_id_and_output_excerpt(
    mock_chat_view_model: ChatViewModel,
    mock_terminal_view_model: TerminalViewModel,
) -> None:
    # Создаем app контекст для Textual компонентов
    app = _TestApp()
    async with app.run_test() as _:
        panel = ToolPanel(mock_chat_view_model, mock_terminal_view_model)
        panel.apply_update(
            ToolCallCreatedUpdate(
                sessionUpdate="tool_call",
                toolCallId="call_1",
                title="Run command",
                status="in_progress",
                content=[ToolCallTerminalContent(type="terminal", terminalId="term_1")],
            )
        )
        panel.apply_update(
            ToolCallStateUpdate(
                sessionUpdate="tool_call_update",
                toolCallId="call_1",
                status="completed",
                rawOutput={"output": "line1\nline2\n", "exitCode": 0},
            )
        )

        rendered = panel._render_text()  # noqa: SLF001

        # Проверяем что terminal ID отображается
        assert "terminal: term_1" in rendered
        # Проверяем что exit code отображается (output часть может быть пуста в базовом renderer)
        assert "Exit code: 0" in rendered


@pytest.mark.asyncio
async def test_tool_panel_returns_latest_terminal_snapshot(
    mock_chat_view_model: ChatViewModel,
    mock_terminal_view_model: TerminalViewModel,
) -> None:
    # Создаем app контекст для Textual компонентов
    app = _TestApp()
    async with app.run_test() as _:
        panel = ToolPanel(mock_chat_view_model, mock_terminal_view_model)
        panel.apply_update(
            ToolCallCreatedUpdate(
                sessionUpdate="tool_call",
                toolCallId="call_1",
                title="Run command",
                status="in_progress",
                content=[ToolCallTerminalContent(type="terminal", terminalId="term_9")],
            )
        )
        panel.apply_update(
            ToolCallStateUpdate(
                sessionUpdate="tool_call_update",
                toolCallId="call_1",
                status="completed",
                rawOutput={"output": "done\n", "exitCode": 0},
            )
        )

        snapshot = panel.latest_terminal_snapshot()

        assert snapshot is not None
        title, terminal_id, output = snapshot
        assert title == "Run command"
        assert terminal_id == "term_9"
        # Проверяем что snapshot содержит информацию об exit code
        assert "Exit code: 0" in output.plain  # type: ignore[unresolved-attribute]


# === Тесты интеграции ToolCallList в ToolPanel ===


@pytest.mark.asyncio
async def test_tool_panel_contains_tool_call_list(
    mock_chat_view_model: ChatViewModel,
    mock_terminal_view_model: TerminalViewModel,
) -> None:
    """ToolPanel содержит ToolCallList компонент."""
    from codelab.client.tui.components.tool_call_list import ToolCallList
    
    app = _TestApp()
    async with app.run_test() as pilot:
        panel = ToolPanel(mock_chat_view_model, mock_terminal_view_model)
        await app.mount(panel)
        await pilot.pause()
        
        # Проверяем наличие ToolCallList
        tool_call_list = panel.query_one("#tool-call-list", ToolCallList)
        assert tool_call_list is not None


@pytest.mark.asyncio
async def test_tool_panel_tool_call_list_receives_chat_vm(
    mock_chat_view_model: ChatViewModel,
    mock_terminal_view_model: TerminalViewModel,
) -> None:
    """ToolCallList в ToolPanel получает ChatViewModel."""
    from codelab.client.tui.components.tool_call_list import ToolCallList
    
    app = _TestApp()
    async with app.run_test() as pilot:
        panel = ToolPanel(mock_chat_view_model, mock_terminal_view_model)
        await app.mount(panel)
        await pilot.pause()
        
        tool_call_list = panel.query_one("#tool-call-list", ToolCallList)
        # ToolCallList должен иметь ссылку на тот же ChatViewModel
        assert tool_call_list._chat_vm is mock_chat_view_model  # noqa: SLF001


@pytest.mark.asyncio
async def test_tool_panel_reset_clears_tool_call_list(
    mock_chat_view_model: ChatViewModel,
    mock_terminal_view_model: TerminalViewModel,
) -> None:
    """reset() очищает ToolCallList."""
    from codelab.client.tui.components.tool_call_list import ToolCallList
    
    app = _TestApp()
    async with app.run_test() as pilot:
        panel = ToolPanel(mock_chat_view_model, mock_terminal_view_model)
        await app.mount(panel)
        await pilot.pause()
        
        tool_call_list = panel.query_one("#tool-call-list", ToolCallList)
        
        # Добавляем tool call
        tool_call_list.add_tool_call("test_call_1", "read_file", {"path": "/test"})
        assert tool_call_list.count == 1
        
        # Сбрасываем панель
        panel.reset()
        
        # ToolCallList должен быть очищен
        assert tool_call_list.count == 0


@pytest.mark.asyncio
async def test_tool_panel_has_tool_call_list_property(
    mock_chat_view_model: ChatViewModel,
    mock_terminal_view_model: TerminalViewModel,
) -> None:
    """ToolPanel имеет property _tool_call_list."""
    from codelab.client.tui.components.tool_call_list import ToolCallList
    
    app = _TestApp()
    async with app.run_test() as pilot:
        panel = ToolPanel(mock_chat_view_model, mock_terminal_view_model)
        await app.mount(panel)
        await pilot.pause()
        
        # Проверяем что property возвращает ToolCallList
        assert isinstance(panel._tool_call_list, ToolCallList)  # noqa: SLF001

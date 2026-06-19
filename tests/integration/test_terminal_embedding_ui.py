"""Integration тест для terminal embedding в UI.

Проверяет полный flow:
1. ToolCallHandler получает notification с terminal content
2. ChatSessionState сохраняет content в tool_calls
3. ChatViewModel обновляет tool_calls Observable
4. ToolPanel получает update и извлекает terminalId
5. TerminalOutputPanel создаётся для отображения terminal output
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from codelab.client.messages import ToolCallStateUpdate
from codelab.client.presentation.chat.chat_session_state import ChatSessionState
from codelab.client.presentation.chat.context import ChatUpdateContext
from codelab.client.presentation.chat.handlers.tool_call_handler import ToolCallHandler
from codelab.client.tui.components.tool_panel import ToolPanel


@pytest.fixture
def session_state() -> ChatSessionState:
    """Создать тестовое состояние сессии."""
    return ChatSessionState()


@pytest.fixture
def mock_context(session_state: ChatSessionState) -> ChatUpdateContext:
    """Создать mock контекст."""
    context = MagicMock(spec=ChatUpdateContext)
    context.session_id = "test-session"
    context.state = session_state
    context.sink = None
    context.logger = MagicMock()
    return context


@pytest.fixture
def handler() -> ToolCallHandler:
    """Создать handler."""
    return ToolCallHandler()


class TestTerminalEmbeddingUIIntegration:
    """Integration тесты для terminal embedding в UI."""

    def test_tool_call_handler_saves_terminal_content(
        self, handler: ToolCallHandler, mock_context: ChatUpdateContext
    ) -> None:
        """ToolCallHandler сохраняет terminal content в ChatSessionState."""
        terminal_content = [
            {"type": "terminal", "terminalId": "term_integration"},
            {
                "type": "content",
                "content": {"type": "text", "text": "Terminal created"},
            },
        ]
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": "tc_001",
                    "title": "terminal/create",
                    "status": "completed",
                    "kind": "execute",
                    "content": terminal_content,
                }
            }
        }

        handler.handle(update_data, mock_context)

        # Проверяем что content сохранён в состоянии
        assert len(mock_context.state.tool_calls) == 1
        tool_call = mock_context.state.tool_calls[0]
        assert "content" in tool_call
        assert tool_call["content"] == terminal_content

    def test_tool_panel_extracts_terminal_id_from_content(
        self, handler: ToolCallHandler, mock_context: ChatUpdateContext
    ) -> None:
        """ToolPanel извлекает terminalId из content в tool_calls."""
        terminal_content = [
            {"type": "terminal", "terminalId": "term_panel_test"},
        ]
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": "tc_002",
                    "title": "terminal/create",
                    "status": "completed",
                    "kind": "execute",
                    "content": terminal_content,
                }
            }
        }

        handler.handle(update_data, mock_context)

        # Проверяем что tool_call содержит terminal content
        tool_call = mock_context.state.tool_calls[0]
        assert tool_call["content"][0]["type"] == "terminal"
        assert tool_call["content"][0]["terminalId"] == "term_panel_test"

        # Проверяем что ToolPanel может извлечь terminalId
        terminal_id = ToolPanel._extract_terminal_id(tool_call)
        assert terminal_id == "term_panel_test"

    def test_tool_call_update_preserves_terminal_content(
        self, handler: ToolCallHandler, mock_context: ChatUpdateContext
    ) -> None:
        """Tool call update сохраняет terminal content при обновлении статуса."""
        # Создаём tool call с terminal content
        terminal_content = [
            {"type": "terminal", "terminalId": "term_update_test"},
        ]
        create_data = {
            "params": {
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": "tc_003",
                    "title": "terminal/create",
                    "status": "pending",
                    "kind": "execute",
                    "content": terminal_content,
                }
            }
        }
        handler.handle(create_data, mock_context)

        # Обновляем статус
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "tc_003",
                    "status": "completed",
                }
            }
        }
        handler.handle(update_data, mock_context)

        # Проверяем что content сохранён
        tool_call = mock_context.state.tool_calls[0]
        assert "content" in tool_call
        assert tool_call["content"][0]["terminalId"] == "term_update_test"
        assert tool_call["status"] == "completed"

    def test_apply_update_processes_terminal_content(
        self, handler: ToolCallHandler, mock_context: ChatUpdateContext
    ) -> None:
        """ToolPanel.apply_update() обрабатывает terminal content."""
        terminal_content = [
            {"type": "terminal", "terminalId": "term_apply_test"},
        ]
        
        # Создаём ToolCallStateUpdate с terminal content
        update = ToolCallStateUpdate(
            sessionUpdate="tool_call_update",
            toolCallId="tc_004",
            title="terminal/create",
            status="completed",
            kind="execute",
            content=terminal_content,
        )

        # Создаём mock ToolPanel для тестирования apply_update
        mock_terminal_vm = MagicMock()
        
        # Создаём ToolPanel без монтирования
        panel = ToolPanel.__new__(ToolPanel)
        panel._tool_calls = {}
        panel._terminal_vm = mock_terminal_vm
        
        # Вызываем apply_update
        panel.apply_update(update)

        # Проверяем что terminal_id извлечён и сохранён
        assert "tc_004" in panel._tool_calls
        tool_call_data = panel._tool_calls["tc_004"]
        assert tool_call_data["terminal_id"] == "term_apply_test"

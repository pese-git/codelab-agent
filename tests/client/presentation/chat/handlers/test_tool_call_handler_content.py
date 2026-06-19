"""Unit тесты для клиентского ToolCallHandler — сохранение content.

Проверяет:
- _handle_tool_call_created() сохраняет content из update
- _handle_tool_call_updated() обновляет content если присутствует
- Content сохраняется в состоянии сессии
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from codelab.client.presentation.chat.handlers.tool_call_handler import ToolCallHandler


@pytest.fixture
def mock_context() -> MagicMock:
    """Создать mock контекст."""
    context = MagicMock()
    context.session_id = "test-session"
    context.state = MagicMock()
    context.state.add_tool_call = MagicMock()
    context.state.update_tool_call = MagicMock()
    context.state.tool_calls = []
    context.sink = None
    context.logger = MagicMock()
    return context


@pytest.fixture
def handler() -> ToolCallHandler:
    """Создать handler."""
    return ToolCallHandler()


class TestToolCallHandlerContent:
    """Тесты сохранения content в ToolCallHandler."""

    def test_handle_tool_call_created_saves_content(
        self, handler: ToolCallHandler, mock_context: MagicMock
    ) -> None:
        """_handle_tool_call_created() сохраняет content из update."""
        terminal_content = [
            {"type": "terminal", "terminalId": "term_xyz789"},
            {
                "type": "content",
                "content": {"type": "text", "text": "Terminal created"},
            },
        ]
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": "call_001",
                    "title": "Running tests",
                    "status": "in_progress",
                    "kind": "execute",
                    "content": terminal_content,
                }
            }
        }

        handler.handle(update_data, mock_context)

        # Проверяем что add_tool_call был вызван с content
        mock_context.state.add_tool_call.assert_called_once()
        tool_call = mock_context.state.add_tool_call.call_args[0][0]
        assert "content" in tool_call
        assert tool_call["content"] == terminal_content

    def test_handle_tool_call_created_without_content(
        self, handler: ToolCallHandler, mock_context: MagicMock
    ) -> None:
        """_handle_tool_call_created() работает без content."""
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": "call_001",
                    "title": "Reading file",
                    "status": "pending",
                    "kind": "read",
                }
            }
        }

        handler.handle(update_data, mock_context)

        # Проверяем что add_tool_call был вызван без content
        mock_context.state.add_tool_call.assert_called_once()
        tool_call = mock_context.state.add_tool_call.call_args[0][0]
        assert "content" not in tool_call

    def test_handle_tool_call_updated_saves_content(
        self, handler: ToolCallHandler, mock_context: MagicMock
    ) -> None:
        """_handle_tool_call_updated() обновляет content если присутствует."""
        terminal_content = [
            {"type": "terminal", "terminalId": "term_abc123"},
        ]
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "call_001",
                    "status": "completed",
                    "content": terminal_content,
                }
            }
        }

        handler.handle(update_data, mock_context)

        # Проверяем что update_tool_call был вызван с content
        mock_context.state.update_tool_call.assert_called_once()
        call_kwargs = mock_context.state.update_tool_call.call_args[1]
        assert "content" in call_kwargs
        assert call_kwargs["content"] == terminal_content

    def test_handle_tool_call_updated_without_content(
        self, handler: ToolCallHandler, mock_context: MagicMock
    ) -> None:
        """_handle_tool_call_updated() работает без content."""
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "call_001",
                    "status": "completed",
                }
            }
        }

        handler.handle(update_data, mock_context)

        # Проверяем что update_tool_call был вызван без content
        mock_context.state.update_tool_call.assert_called_once()
        call_kwargs = mock_context.state.update_tool_call.call_args[1]
        assert "content" not in call_kwargs

    def test_handle_tool_call_created_terminal_content_format(
        self, handler: ToolCallHandler, mock_context: MagicMock
    ) -> None:
        """_handle_tool_call_created() сохраняет terminal content в правильном формате."""
        terminal_content = [
            {"type": "terminal", "terminalId": "term_test"},
            {
                "type": "content",
                "content": {
                    "type": "text",
                    "text": "Terminal term_test created for command: npm test",
                },
            },
        ]
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": "call_terminal",
                    "title": "Running npm test",
                    "status": "in_progress",
                    "kind": "execute",
                    "content": terminal_content,
                }
            }
        }

        handler.handle(update_data, mock_context)

        tool_call = mock_context.state.add_tool_call.call_args[0][0]
        assert tool_call["content"][0]["type"] == "terminal"
        assert tool_call["content"][0]["terminalId"] == "term_test"
        assert tool_call["content"][1]["type"] == "content"
        assert tool_call["content"][1]["content"]["type"] == "text"

"""Unit тесты для AgentLoop — terminal embedding через permission flow.

Проверяет:
- _execute_pending_tool() передаёт extracted_content в ToolResult
- resume_after_permission() отправляет notification клиенту с content
- Terminal content корректно передаётся после permission approval
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.agent.base import AgentResponse
from codelab.server.protocol.handlers.pipeline.stages.agent_loop import AgentLoop
from codelab.server.protocol.state import SessionState, ToolCallState


@pytest.fixture
def mock_strategy():
    """Mock LLMCallStrategy."""
    strategy = MagicMock()
    strategy.execute = AsyncMock()
    strategy.continue_execution = AsyncMock()
    return strategy


@pytest.fixture
def mock_session():
    """Mock SessionState."""
    session = MagicMock(spec=SessionState)
    session.session_id = "test_session"
    session.config_values = {}
    session.history = []
    session.tool_calls = {}
    session.active_turn = None
    session.permission_policy = {}
    session.latest_plan = None
    return session


@pytest.fixture
def mock_dependencies():
    """Mock зависимости AgentLoop."""
    mock_spb = MagicMock()
    mock_spb.build.return_value = "You are a helpful assistant."
    mock_content_validator = MagicMock()
    mock_content_validator.validate_content_list.return_value = (True, [])
    return {
        "tool_registry": MagicMock(),
        "tool_call_handler": MagicMock(),
        "permission_manager": MagicMock(),
        "state_manager": MagicMock(),
        "content_extractor": AsyncMock(),
        "content_validator": mock_content_validator,
        "content_formatter": MagicMock(),
        "replay_manager": MagicMock(),
        "plan_builder": MagicMock(),
        "system_prompt_builder": mock_spb,
    }


class TestAgentLoopPermissionFlowTerminalContent:
    """Тесты terminal embedding через permission flow."""

    @pytest.mark.asyncio
    async def test_execute_pending_tool_returns_content(
        self, mock_strategy, mock_session, mock_dependencies
    ) -> None:
        """_execute_pending_tool() возвращает ToolResult с content."""
        # Arrange
        tool_call_id = "tc_001"
        tool_call_state = ToolCallState(
            tool_call_id=tool_call_id,
            title="terminal/create",
            kind="execute",
            status="pending",
            tool_name="terminal/create",
            tool_arguments={},
        )
        mock_session.tool_calls = {tool_call_id: tool_call_state}

        # Tool execution result
        mock_tool_result = MagicMock()
        mock_tool_result.success = True
        mock_tool_result.output = "Terminal created"
        mock_tool_result.error = None
        mock_dependencies["tool_registry"].execute_tool = AsyncMock(
            return_value=mock_tool_result
        )

        # Extracted content с terminal embedding
        terminal_content = [
            {"type": "terminal", "terminalId": "term_xyz789"},
            {
                "type": "content",
                "content": {"type": "text", "text": "Terminal created"},
            },
        ]
        mock_extracted = MagicMock()
        mock_extracted.content_items = terminal_content
        mock_dependencies["content_extractor"].extract_from_result = AsyncMock(
            return_value=mock_extracted
        )

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)

        # Act
        result = await loop._execute_pending_tool(
            mock_session, "test_session", tool_call_id, None
        )

        # Assert
        assert result is not None
        assert result.success is True
        assert result.content == terminal_content

    @pytest.mark.asyncio
    async def test_resume_after_permission_sends_notification_with_content(
        self, mock_strategy, mock_session, mock_dependencies
    ) -> None:
        """resume_after_permission() отправляет notification с terminal content."""
        # Arrange
        tool_call_id = "tc_001"
        tool_call_state = ToolCallState(
            tool_call_id=tool_call_id,
            title="terminal/create",
            kind="execute",
            status="pending",
            tool_name="terminal/create",
            tool_arguments={"operation": "create", "command": "ls"},
        )
        mock_session.tool_calls = {tool_call_id: tool_call_state}

        # Tool execution result
        mock_tool_result = MagicMock()
        mock_tool_result.success = True
        mock_tool_result.output = "Terminal created"
        mock_tool_result.error = None
        mock_dependencies["tool_registry"].execute_tool = AsyncMock(
            return_value=mock_tool_result
        )

        # Extracted content с terminal embedding
        terminal_content = [
            {"type": "terminal", "terminalId": "term_resume"},
            {
                "type": "content",
                "content": {"type": "text", "text": "Terminal created"},
            },
        ]
        mock_extracted = MagicMock()
        mock_extracted.content_items = terminal_content
        mock_dependencies["content_extractor"].extract_from_result = AsyncMock(
            return_value=mock_extracted
        )

        # Mock build_tool_update_notification
        mock_notification = MagicMock()
        mock_dependencies["tool_call_handler"].build_tool_update_notification.return_value = (
            mock_notification
        )

        # Mock run() для продолжения цикла
        mock_loop_result = MagicMock()
        mock_loop_result.text = "Done"
        mock_loop_result.stop_reason = "end_turn"
        mock_loop_result.notifications = []
        mock_loop_result.pending_permission = False
        mock_loop_result.pending_tool_calls = []
        mock_loop_result.tool_results = []

        # Второй вызов LLM возвращает текст без tool calls
        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "Done"
        second_response.tool_calls = []
        mock_strategy.continue_execution.return_value = second_response

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)

        # Act
        result = await loop.resume_after_permission(
            mock_session, "test_session", tool_call_id, None
        )

        # Assert
        assert len(result.notifications) >= 1
        # Проверяем что build_tool_update_notification был вызван с content
        handler = mock_dependencies["tool_call_handler"]
        handler.build_tool_update_notification.assert_called()
        call_kwargs = handler.build_tool_update_notification.call_args.kwargs
        assert call_kwargs["content"] == terminal_content
        assert call_kwargs["status"] == "completed"

    @pytest.mark.asyncio
    async def test_resume_after_permission_saves_to_replay(
        self, mock_strategy, mock_session, mock_dependencies
    ) -> None:
        """resume_after_permission() сохраняет tool_call_update в replay."""
        # Arrange
        tool_call_id = "tc_replay"
        tool_call_state = ToolCallState(
            tool_call_id=tool_call_id,
            title="terminal/create",
            kind="execute",
            status="pending",
            tool_name="terminal/create",
            tool_arguments={"operation": "create", "command": "ls"},
        )
        mock_session.tool_calls = {tool_call_id: tool_call_state}

        mock_tool_result = MagicMock()
        mock_tool_result.success = True
        mock_tool_result.output = "OK"
        mock_tool_result.error = None
        mock_dependencies["tool_registry"].execute_tool = AsyncMock(
            return_value=mock_tool_result
        )

        terminal_content = [{"type": "terminal", "terminalId": "term_replay"}]
        mock_extracted = MagicMock()
        mock_extracted.content_items = terminal_content
        mock_dependencies["content_extractor"].extract_from_result = AsyncMock(
            return_value=mock_extracted
        )

        mock_dependencies["tool_call_handler"].build_tool_update_notification.return_value = (
            MagicMock()
        )

        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "Done"
        second_response.tool_calls = []
        mock_strategy.continue_execution.return_value = second_response

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)

        # Act
        await loop.resume_after_permission(
            mock_session, "test_session", tool_call_id, None
        )

        # Assert
        mock_dependencies["replay_manager"].save_tool_call_update.assert_called()
        call_kwargs = mock_dependencies["replay_manager"].save_tool_call_update.call_args.kwargs
        assert call_kwargs["tool_call_id"] == tool_call_id
        assert call_kwargs["status"] == "completed"
        assert call_kwargs["content"] == terminal_content

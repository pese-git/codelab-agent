"""Unit тесты для AgentLoop — передача extracted content.

Проверяет:
- Передача extracted_content.content_items в notification
- Fallback на text если content пустой
- Корректная работа с terminal content
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.agent.base import AgentResponse
from codelab.server.protocol.handlers.pipeline.stages.agent_loop import AgentLoop


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
    session = MagicMock()
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


class TestAgentLoopExtractedContent:
    """Тесты передачи extracted content в notification."""

    @pytest.mark.asyncio
    async def test_notification_uses_extracted_content_items(
        self, mock_strategy, mock_session, mock_dependencies
    ) -> None:
        """AgentLoop передаёт extracted_content.content_items в notification."""
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.name = "terminal_create"
        mock_tool_call.arguments = {"operation": "create", "command": "ls"}

        first_response = MagicMock(spec=AgentResponse)
        first_response.text = "Creating terminal..."
        first_response.tool_calls = [mock_tool_call]

        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "Done"
        second_response.tool_calls = []

        mock_strategy.execute.return_value = first_response
        mock_strategy.continue_execution.return_value = second_response

        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = False
        mock_tool_def.kind = "execute"
        mock_dependencies["tool_registry"].get.return_value = mock_tool_def
        mock_dependencies["tool_call_handler"].create_tool_call.return_value = "tc_1"
        h = mock_dependencies["tool_call_handler"]
        h.build_tool_call_notification.return_value = MagicMock()
        h.build_tool_update_notification.return_value = MagicMock()

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
        mock_dependencies["content_extractor"].extract_from_result.return_value = (
            mock_extracted
        )

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        await loop.run(mock_session, "test_session", "Run ls")

        # Проверяем что build_tool_update_notification был вызван с terminal content
        update_calls = h.build_tool_update_notification.call_args_list
        assert len(update_calls) >= 1

        # Последний вызов должен содержать extracted content
        last_call = update_calls[-1]
        notification_content = last_call.kwargs.get("content")
        assert notification_content == terminal_content

    @pytest.mark.asyncio
    async def test_notification_fallback_to_text_if_content_empty(
        self, mock_strategy, mock_session, mock_dependencies
    ) -> None:
        """AgentLoop использует text fallback если extracted content пустой."""
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.name = "fs_read_text_file"
        mock_tool_call.arguments = {"path": "test.txt"}

        first_response = MagicMock(spec=AgentResponse)
        first_response.text = "Reading file..."
        first_response.tool_calls = [mock_tool_call]

        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "Done"
        second_response.tool_calls = []

        mock_strategy.execute.return_value = first_response
        mock_strategy.continue_execution.return_value = second_response

        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = False
        mock_tool_def.kind = "read"
        mock_dependencies["tool_registry"].get.return_value = mock_tool_def
        mock_dependencies["tool_call_handler"].create_tool_call.return_value = "tc_1"
        h = mock_dependencies["tool_call_handler"]
        h.build_tool_call_notification.return_value = MagicMock()
        h.build_tool_update_notification.return_value = MagicMock()

        # Tool execution result
        mock_tool_result = MagicMock()
        mock_tool_result.success = True
        mock_tool_result.output = "File content here"
        mock_tool_result.error = None
        mock_dependencies["tool_registry"].execute_tool = AsyncMock(
            return_value=mock_tool_result
        )

        # Extracted content пустой
        mock_extracted = MagicMock()
        mock_extracted.content_items = []
        mock_dependencies["content_extractor"].extract_from_result.return_value = (
            mock_extracted
        )

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        await loop.run(mock_session, "test_session", "Read file")

        # Проверяем что build_tool_update_notification был вызван с text fallback
        update_calls = h.build_tool_update_notification.call_args_list
        assert len(update_calls) >= 1

        # Последний вызов должен содержать text fallback
        last_call = update_calls[-1]
        notification_content = last_call.kwargs.get("content")
        expected_fallback = [
            {"type": "content", "content": {"type": "text", "text": "File content here"}}
        ]
        assert notification_content == expected_fallback

    @pytest.mark.asyncio
    async def test_notification_content_none_if_no_output_and_empty_content(
        self, mock_strategy, mock_session, mock_dependencies
    ) -> None:
        """AgentLoop передаёт None если нет output и content пустой."""
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.name = "some_tool"
        mock_tool_call.arguments = {}

        first_response = MagicMock(spec=AgentResponse)
        first_response.text = "Running tool..."
        first_response.tool_calls = [mock_tool_call]

        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "Done"
        second_response.tool_calls = []

        mock_strategy.execute.return_value = first_response
        mock_strategy.continue_execution.return_value = second_response

        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = False
        mock_tool_def.kind = "other"
        mock_dependencies["tool_registry"].get.return_value = mock_tool_def
        mock_dependencies["tool_call_handler"].create_tool_call.return_value = "tc_1"
        h = mock_dependencies["tool_call_handler"]
        h.build_tool_call_notification.return_value = MagicMock()
        h.build_tool_update_notification.return_value = MagicMock()

        # Tool execution result без output
        mock_tool_result = MagicMock()
        mock_tool_result.success = True
        mock_tool_result.output = None
        mock_tool_result.error = None
        mock_dependencies["tool_registry"].execute_tool = AsyncMock(
            return_value=mock_tool_result
        )

        # Extracted content пустой
        mock_extracted = MagicMock()
        mock_extracted.content_items = []
        mock_dependencies["content_extractor"].extract_from_result.return_value = (
            mock_extracted
        )

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        await loop.run(mock_session, "test_session", "Run tool")

        # Проверяем что build_tool_update_notification был вызван с content=None
        update_calls = h.build_tool_update_notification.call_args_list
        assert len(update_calls) >= 1

        # Последний вызов должен содержать content=None
        last_call = update_calls[-1]
        notification_content = last_call.kwargs.get("content")
        assert notification_content is None

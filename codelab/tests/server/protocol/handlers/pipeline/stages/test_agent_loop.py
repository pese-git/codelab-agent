"""Тесты для AgentLoop."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.protocol.handlers.pipeline.stages.agent_loop import (
    AgentLoop,
    AgentLoopResult,
    ToolProcessingResult,
)
from codelab.server.protocol.stop_reasons import StopReason


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
    return {
        "tool_registry": MagicMock(),
        "tool_call_handler": MagicMock(),
        "permission_manager": MagicMock(),
        "state_manager": MagicMock(),
        "content_extractor": AsyncMock(),
        "content_validator": MagicMock(),
        "content_formatter": MagicMock(),
        "replay_manager": MagicMock(),
        "plan_builder": MagicMock(),
    }


class TestAgentLoopResult:
    """Тесты AgentLoopResult."""

    def test_default_values(self):
        """AgentLoopResult имеет правильные значения по умолчанию."""
        result = AgentLoopResult()
        assert result.text is None
        assert result.stop_reason == StopReason.END_TURN
        assert result.notifications == []
        assert result.pending_permission is False
        assert result.pending_tool_calls == []
        assert result.tool_results == []

    def test_custom_values(self):
        """AgentLoopResult принимает кастомные значения."""
        result = AgentLoopResult(
            text="Hello",
            stop_reason=StopReason.MAX_TURN_REQUESTS,
            pending_permission=True,
        )
        assert result.text == "Hello"
        assert result.stop_reason == StopReason.MAX_TURN_REQUESTS
        assert result.pending_permission is True


class TestToolProcessingResult:
    """Тесты ToolProcessingResult."""

    def test_default_values(self):
        """ToolProcessingResult имеет правильные значения по умолчанию."""
        result = ToolProcessingResult()
        assert result.tool_results == []
        assert result.pending_permission is False
        assert result.pending_tool_calls == []


class TestAgentLoop:
    """Тесты AgentLoop."""

    @pytest.mark.asyncio
    async def test_run_no_tool_calls(
        self, mock_strategy, mock_session, mock_dependencies
    ):
        """run() завершается без tool_calls."""
        from codelab.server.agent.base import AgentResponse

        mock_response = MagicMock(spec=AgentResponse)
        mock_response.text = "Hello!"
        mock_response.tool_calls = []
        mock_strategy.execute.return_value = mock_response

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        result = await loop.run(mock_session, "test_session", "Hello")

        assert result.text == "Hello!"
        assert result.stop_reason == StopReason.END_TURN
        mock_strategy.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_max_turn_requests(
        self, mock_strategy, mock_session, mock_dependencies
    ):
        """run() достигает max_turn_requests."""
        from codelab.server.agent.base import AgentResponse

        # Создаём response с tool_calls
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.name = "test_tool"
        mock_tool_call.arguments = {}

        mock_response = MagicMock(spec=AgentResponse)
        mock_response.text = ""
        mock_response.tool_calls = [mock_tool_call]
        mock_strategy.execute.return_value = mock_response
        mock_strategy.continue_execution.return_value = mock_response

        # Mock tool execution — tool не требует permission
        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = False
        mock_tool_def.kind = "other"
        mock_dependencies["tool_registry"].get.return_value = mock_tool_def
        mock_dependencies["tool_call_handler"].create_tool_call.return_value = "tool_1"
        mock_dependencies["tool_call_handler"].build_tool_call_notification.return_value = MagicMock()
        mock_dependencies["tool_call_handler"].build_tool_update_notification.return_value = MagicMock()
        
        # Mock tool execution result
        mock_tool_result = MagicMock()
        mock_tool_result.success = True
        mock_tool_result.output = "Success"
        mock_tool_result.error = None
        mock_dependencies["tool_registry"].execute_tool.return_value = mock_tool_result
        
        # Mock content extraction
        mock_extracted = MagicMock()
        mock_extracted.content_items = []
        mock_dependencies["content_extractor"].extract_from_result.return_value = mock_extracted

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies, max_turn_requests=2)
        result = await loop.run(mock_session, "test_session", "Hello")

        assert result.stop_reason == StopReason.MAX_TURN_REQUESTS

    @pytest.mark.asyncio
    async def test_run_cancellation(
        self, mock_strategy, mock_session, mock_dependencies
    ):
        """run() обрабатывает отмену."""
        mock_session.active_turn = MagicMock()
        mock_session.active_turn.cancel_requested = True

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        result = await loop.run(mock_session, "test_session", "Hello")

        assert result.stop_reason == StopReason.CANCELLED

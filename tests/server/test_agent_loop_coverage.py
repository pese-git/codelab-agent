"""Тесты для непокрытых веток AgentLoop.

Покрывают отмену после LLM-вызова, инициализацию стратегии при resume,
невалидные tool calls, валидацию контента и ошибки выполнения pending tool.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codelab.server.agent.base import AgentResponse
from codelab.server.protocol.handlers.pipeline.stages.agent_loop import (
    AgentLoop,
    StopReason,
    ToolResult,
)

_LOGGER_PATH = "codelab.server.protocol.handlers.pipeline.stages.agent_loop.logger"


@pytest.fixture
def mock_strategy() -> MagicMock:
    """Mock LLMCallStrategy."""
    strategy = MagicMock()
    strategy.execute = AsyncMock()
    strategy.continue_execution = AsyncMock()
    return strategy


@pytest.fixture
def mock_session() -> MagicMock:
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
def mock_dependencies() -> dict[str, MagicMock]:
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
        "system_prompt_builder": MagicMock(),
        "global_policy_manager": MagicMock(),
    }


class TestAgentLoopCancellation:
    """Тесты отмены в разные моменты цикла."""

    @pytest.mark.asyncio
    async def test_run_cancelled_after_llm_call(
        self,
        mock_strategy: MagicMock,
        mock_session: MagicMock,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """Отмена после успешного LLM-вызова возвращает CANCELLED."""
        response = MagicMock(spec=AgentResponse)
        response.text = ""
        response.tool_calls = []
        mock_strategy.execute.return_value = response

        mock_session.active_turn = MagicMock()
        mock_session.active_turn.cancel_requested = False

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)

        cancel_calls = [False, True]
        loop._is_cancel_requested = MagicMock(side_effect=cancel_calls.copy())

        result = await loop.run(mock_session, "test_session", "hello")

        assert result.stop_reason == StopReason.CANCELLED


class TestAgentLoopResume:
    """Тесты resume_after_permission."""

    @pytest.mark.asyncio
    async def test_resume_reinitializes_strategy_and_logs(
        self,
        mock_strategy: MagicMock,
        mock_session: MagicMock,
        mock_dependencies: dict[str, MagicMock],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """resume_after_permission переинициализирует стратегию и логирует это."""
        mock_strategy._current_strategy_name = None
        mock_strategy.select_strategy = MagicMock()

        tool_state = MagicMock()
        tool_state.tool_name = "test_tool"
        tool_state.tool_arguments = {}
        tool_state.tool_call_id_from_llm = "llm_1"
        mock_session.tool_calls = {"tc_1": tool_state}

        tool_result = MagicMock()
        tool_result.success = True
        tool_result.output = "ok"
        tool_result.error = None
        mock_dependencies["tool_registry"].execute_tool = AsyncMock(return_value=tool_result)

        extracted = MagicMock()
        extracted.content_items = []
        mock_dependencies["content_extractor"].extract_from_result.return_value = extracted

        final_response = MagicMock(spec=AgentResponse)
        final_response.text = "done"
        final_response.tool_calls = []
        mock_strategy.continue_execution.return_value = final_response

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)

        with patch(_LOGGER_PATH) as mock_logger:
            result = await loop.resume_after_permission(
                mock_session, "test_session", "tc_1"
            )

        assert result.stop_reason == StopReason.END_TURN
        mock_strategy.select_strategy.assert_called_once()
        assert any(
            "resume_after_permission: strategy re-initialized" in str(call)
            for call in mock_logger.debug.call_args_list
        )


class TestAgentLoopToolProcessing:
    """Тесты обработки tool calls."""

    @pytest.mark.asyncio
    async def test_tool_call_without_name_is_skipped(
        self,
        mock_strategy: MagicMock,
        mock_session: MagicMock,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """Tool call без имени пропускается с предупреждением."""
        tool_call = MagicMock()
        tool_call.name = None
        tool_call.id = "call_1"
        tool_call.arguments = {}

        first_response = MagicMock(spec=AgentResponse)
        first_response.text = ""
        first_response.tool_calls = [tool_call]

        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "done"
        second_response.tool_calls = []

        mock_strategy.execute.return_value = first_response
        mock_strategy.continue_execution.return_value = second_response

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)

        with patch(_LOGGER_PATH) as mock_logger:
            result = await loop.run(mock_session, "test_session", "hello")

        assert result.stop_reason == StopReason.END_TURN
        mock_logger.warning.assert_called_once()
        assert "tool_call has no name" in str(mock_logger.warning.call_args)
        mock_dependencies["tool_registry"].execute_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_tool_result_validation_failure_is_logged(
        self,
        mock_strategy: MagicMock,
        mock_session: MagicMock,
        mock_dependencies: dict[str, MagicMock],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Невалидный контент результата tool логируется."""
        tool_call = MagicMock()
        tool_call.id = "call_1"
        tool_call.name = "test_tool"
        tool_call.arguments = {}

        first_response = MagicMock(spec=AgentResponse)
        first_response.text = ""
        first_response.tool_calls = [tool_call]

        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "done"
        second_response.tool_calls = []

        mock_strategy.execute.return_value = first_response
        mock_strategy.continue_execution.return_value = second_response

        tool_def = MagicMock()
        tool_def.requires_permission = False
        tool_def.kind = "other"
        mock_dependencies["tool_registry"].get.return_value = tool_def

        mock_dependencies["tool_call_handler"].create_tool_call.return_value = "tc_1"
        mock_dependencies[
            "tool_call_handler"
        ].build_tool_call_notification.return_value = MagicMock()
        mock_dependencies[
            "tool_call_handler"
        ].build_tool_update_notification.return_value = MagicMock()

        tool_result = MagicMock()
        tool_result.success = True
        tool_result.output = "ok"
        tool_result.error = None
        tool_result.metadata = {}
        mock_dependencies["tool_registry"].execute_tool = AsyncMock(return_value=tool_result)

        extracted = MagicMock()
        extracted.content_items = []
        mock_dependencies["content_extractor"].extract_from_result.return_value = extracted
        mock_dependencies["content_validator"].validate_content_list.return_value = (
            False,
            ["invalid"],
        )

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)

        with patch(_LOGGER_PATH) as mock_logger:
            result = await loop.run(mock_session, "test_session", "hello")

        assert result.stop_reason == StopReason.END_TURN
        mock_logger.warning.assert_called_once()
        assert "tool_result_content_validation_failed" in str(
            mock_logger.warning.call_args
        )


class TestAgentLoopExecutePendingTool:
    """Тесты _execute_pending_tool."""

    @pytest.mark.asyncio
    async def test_execute_pending_tool_with_missing_name_returns_none(
        self,
        mock_strategy: MagicMock,
        mock_session: MagicMock,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """Если tool_name отсутствует в состоянии, возвращается None."""
        state = MagicMock()
        state.tool_name = None
        mock_session.tool_calls = {"tc_1": state}

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        result = await loop._execute_pending_tool(
            mock_session, "test_session", "tc_1", None
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_execute_pending_mcp_tool_without_manager_fails(
        self,
        mock_strategy: MagicMock,
        mock_session: MagicMock,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """MCP tool без mcp_manager возвращает ошибку, не выбрасывая исключение."""
        state = MagicMock()
        state.tool_name = "mcp_server/tool"
        state.tool_arguments = {}
        state.tool_call_id_from_llm = "llm_1"
        mock_session.tool_calls = {"tc_1": state}

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)

        with patch(
            "codelab.server.protocol.handlers.pipeline.stages.agent_loop.MCPToolExecutor.is_mcp_tool",
            return_value=True,
        ):
            result = await loop._execute_pending_tool(
                mock_session, "test_session", "tc_1", None
            )

        assert isinstance(result, ToolResult)
        assert result.success is False
        assert "MCP manager not available" in result.error

    @pytest.mark.asyncio
    async def test_execute_pending_tool_failure_result(
        self,
        mock_strategy: MagicMock,
        mock_session: MagicMock,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """Неуспешный результат tool корректно оформляется как ToolResult."""
        state = MagicMock()
        state.tool_name = "test_tool"
        state.tool_arguments = {}
        state.tool_call_id_from_llm = "llm_1"
        mock_session.tool_calls = {"tc_1": state}

        tool_result = MagicMock()
        tool_result.success = False
        tool_result.output = None
        tool_result.error = "execution failed"
        mock_dependencies["tool_registry"].execute_tool = AsyncMock(return_value=tool_result)

        extracted = MagicMock()
        extracted.content_items = []
        mock_dependencies["content_extractor"].extract_from_result.return_value = extracted

        loop = AgentLoop(strategy=mock_strategy, **mock_dependencies)
        result = await loop._execute_pending_tool(
            mock_session, "test_session", "tc_1", None
        )

        assert isinstance(result, ToolResult)
        assert result.success is False
        assert result.error == "execution failed"
        update_call = mock_dependencies[
            "tool_call_handler"
        ].update_tool_call_status.call_args
        assert update_call is not None
        assert update_call.kwargs.get("content") is not None

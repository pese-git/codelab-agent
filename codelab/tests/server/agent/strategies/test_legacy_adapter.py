"""Тесты для LegacyCallStrategy."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.agent.strategies.base import LLMCallStrategy
from codelab.server.agent.strategies.legacy_adapter import LegacyCallStrategy


@pytest.fixture
def mock_orchestrator():
    """Mock AgentOrchestrator."""
    orchestrator = MagicMock()
    orchestrator.process_prompt = AsyncMock()
    orchestrator.continue_with_tool_results = AsyncMock()
    return orchestrator


@pytest.fixture
def mock_session():
    """Mock SessionState."""
    session = MagicMock()
    session.session_id = "test_session"
    session.config_values = {}
    return session


@pytest.fixture
def mock_response():
    """Mock AgentResponse."""
    response = MagicMock()
    response.text = "Hello!"
    response.tool_calls = []
    return response


class TestLegacyCallStrategy:
    """Тесты LegacyCallStrategy."""

    def test_implements_protocol(self, mock_orchestrator):
        """LegacyCallStrategy реализует LLMCallStrategy Protocol."""
        strategy = LegacyCallStrategy(mock_orchestrator)
        assert isinstance(strategy, LLMCallStrategy)

    @pytest.mark.asyncio
    async def test_execute_with_prompt(
        self, mock_orchestrator, mock_session, mock_response
    ):
        """execute() с prompt вызывает process_prompt()."""
        mock_orchestrator.process_prompt.return_value = mock_response

        strategy = LegacyCallStrategy(mock_orchestrator)
        result = await strategy.execute(mock_session, "Hello", None)

        mock_orchestrator.process_prompt.assert_called_once_with(
            mock_session, "Hello", None
        )
        assert result == mock_response

    @pytest.mark.asyncio
    async def test_execute_without_prompt(
        self, mock_orchestrator, mock_session, mock_response
    ):
        """execute() без prompt вызывает continue_with_tool_results()."""
        mock_orchestrator.continue_with_tool_results.return_value = mock_response

        strategy = LegacyCallStrategy(mock_orchestrator)
        result = await strategy.execute(mock_session, None, None)

        mock_orchestrator.continue_with_tool_results.assert_called_once_with(
            mock_session, [], None
        )
        assert result == mock_response

    @pytest.mark.asyncio
    async def test_continue_execution(
        self, mock_orchestrator, mock_session, mock_response
    ):
        """continue_execution() вызывает continue_with_tool_results() с пустым списком."""
        mock_orchestrator.continue_with_tool_results.return_value = mock_response

        strategy = LegacyCallStrategy(mock_orchestrator)
        result = await strategy.continue_execution(mock_session, None)

        mock_orchestrator.continue_with_tool_results.assert_called_once_with(
            mock_session, [], None
        )
        assert result == mock_response

    @pytest.mark.asyncio
    async def test_execute_with_mcp_manager(
        self, mock_orchestrator, mock_session, mock_response
    ):
        """execute() передаёт mcp_manager в orchestrator."""
        mock_orchestrator.process_prompt.return_value = mock_response
        mcp_manager = MagicMock()

        strategy = LegacyCallStrategy(mock_orchestrator)
        await strategy.execute(mock_session, "Hello", mcp_manager)

        mock_orchestrator.process_prompt.assert_called_once_with(
            mock_session, "Hello", mcp_manager
        )

    @pytest.mark.asyncio
    async def test_continue_execution_with_mcp_manager(
        self, mock_orchestrator, mock_session, mock_response
    ):
        """continue_execution() передаёт mcp_manager в orchestrator."""
        mock_orchestrator.continue_with_tool_results.return_value = mock_response
        mcp_manager = MagicMock()

        strategy = LegacyCallStrategy(mock_orchestrator)
        await strategy.continue_execution(mock_session, mcp_manager)

        mock_orchestrator.continue_with_tool_results.assert_called_once_with(
            mock_session, [], mcp_manager
        )

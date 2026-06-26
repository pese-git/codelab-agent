"""Тесты для terminal tool definitions."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.protocol.state import SessionState
from codelab.server.tools.base import ToolDefinition, ToolExecutionResult
from codelab.server.tools.definitions.terminal import TerminalToolDefinitions


class FakeRegistry:
    """Фейковый реестр для захвата handlers."""

    create_handler = None
    wait_for_exit_handler = None
    release_handler = None

    def register(self, tool: ToolDefinition, handler) -> None:
        if tool.name == "terminal/create":
            FakeRegistry.create_handler = handler
        elif tool.name == "terminal/wait_for_exit":
            FakeRegistry.wait_for_exit_handler = handler
        elif tool.name == "terminal/release":
            FakeRegistry.release_handler = handler


class TestCreateHandlerCwd:
    """Тесты что create_handler подставляет session.cwd."""

    @pytest.mark.asyncio
    async def test_create_handler_sets_session_cwd_when_not_provided(self) -> None:
        """Create handler должен подставить session.cwd если cwd не передан."""
        mock_executor = MagicMock()
        mock_execute = AsyncMock(
            return_value=ToolExecutionResult(success=True, output="terminal created")
        )
        mock_executor.execute = mock_execute

        TerminalToolDefinitions.register_all(
            tool_registry=FakeRegistry(),  # type: ignore[arg-type]
            executor=mock_executor,
        )

        session = SessionState(session_id="sess_1", cwd="/workspace/project")
        handler = FakeRegistry.create_handler
        assert handler is not None

        await handler(session=session, command="ls -la")

        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        arguments = call_args[0][1]
        assert arguments["cwd"] == "/workspace/project"
        assert arguments["operation"] == "create"
        assert arguments["command"] == "ls -la"

    @pytest.mark.asyncio
    async def test_create_handler_explicit_cwd_has_priority(self) -> None:
        """Create handler должен сохранить явный cwd от LLM."""
        mock_executor = MagicMock()
        mock_execute = AsyncMock(
            return_value=ToolExecutionResult(success=True, output="terminal created")
        )
        mock_executor.execute = mock_execute

        TerminalToolDefinitions.register_all(
            tool_registry=FakeRegistry(),  # type: ignore[arg-type]
            executor=mock_executor,
        )

        session = SessionState(session_id="sess_1", cwd="/workspace/project")
        handler = FakeRegistry.create_handler
        assert handler is not None

        await handler(session=session, command="ls -la", cwd="/tmp/other")

        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        arguments = call_args[0][1]
        assert arguments["cwd"] == "/tmp/other"
        assert arguments["operation"] == "create"

    @pytest.mark.asyncio
    async def test_create_handler_no_cwd_when_session_cwd_empty(self) -> None:
        """Create handler не должен подставлять cwd если session.cwd пустой."""
        mock_executor = MagicMock()
        mock_execute = AsyncMock(
            return_value=ToolExecutionResult(success=True, output="terminal created")
        )
        mock_executor.execute = mock_execute

        TerminalToolDefinitions.register_all(
            tool_registry=FakeRegistry(),  # type: ignore[arg-type]
            executor=mock_executor,
        )

        session = SessionState(session_id="sess_1", cwd="")
        handler = FakeRegistry.create_handler
        assert handler is not None

        await handler(session=session, command="ls -la")

        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        arguments = call_args[0][1]
        assert "cwd" not in arguments
        assert arguments["operation"] == "create"

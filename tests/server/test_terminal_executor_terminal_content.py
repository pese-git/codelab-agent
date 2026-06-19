"""Unit тесты для TerminalToolExecutor — terminal embedding.

Проверяет:
- execute_create() возвращает terminal content в ToolExecutionResult
- Terminal content содержит terminalId
- Text content обёрнут в ToolCallContent.content wrapper
- Порядок content items: terminal первым, затем text
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.protocol.state import SessionState
from codelab.server.tools.executors.terminal_executor import TerminalToolExecutor
from codelab.server.tools.integrations.client_rpc_bridge import ClientRPCBridge
from codelab.server.tools.integrations.permission_checker import PermissionChecker


@pytest.fixture
def session() -> SessionState:
    """Создает тестовую сессию."""
    return SessionState(
        session_id="test_session",
        cwd="/tmp",
        mcp_servers=[],
        config_values={},
    )


@pytest.fixture
def executor() -> TerminalToolExecutor:
    """Создает executor с mock зависимостями."""
    mock_bridge = MagicMock(spec=ClientRPCBridge)
    mock_checker = MagicMock(spec=PermissionChecker)
    return TerminalToolExecutor(mock_bridge, mock_checker)


class TestTerminalExecutorCreateTerminalContent:
    """Тесты terminal content в execute_create()."""

    @pytest.mark.asyncio
    async def test_execute_create_returns_terminal_content(
        self,
        executor: TerminalToolExecutor,
        session: SessionState,
    ) -> None:
        """execute_create() возвращает content с terminal и text items."""
        executor._bridge.create_terminal = AsyncMock(return_value="term_xyz789")

        result = await executor.execute_create(
            session=session,
            command="ls -la",
        )

        assert result.success is True
        assert result.content is not None
        assert len(result.content) == 2

    @pytest.mark.asyncio
    async def test_execute_create_terminal_content_has_terminal_id(
        self,
        executor: TerminalToolExecutor,
        session: SessionState,
    ) -> None:
        """Terminal content содержит terminalId."""
        executor._bridge.create_terminal = AsyncMock(return_value="term_abc123")

        result = await executor.execute_create(
            session=session,
            command="echo hello",
        )

        assert result.content is not None
        terminal_item = result.content[0]
        assert terminal_item["type"] == "terminal"
        assert terminal_item["terminalId"] == "term_abc123"

    @pytest.mark.asyncio
    async def test_execute_create_text_content_wrapped(
        self,
        executor: TerminalToolExecutor,
        session: SessionState,
    ) -> None:
        """Text content обёрнут в ToolCallContent.content wrapper."""
        executor._bridge.create_terminal = AsyncMock(return_value="term_test")

        result = await executor.execute_create(
            session=session,
            command="pwd",
        )

        assert result.content is not None
        text_item = result.content[1]
        assert text_item["type"] == "content"
        assert "content" in text_item
        assert text_item["content"]["type"] == "text"
        assert "Terminal term_test created" in text_item["content"]["text"]

    @pytest.mark.asyncio
    async def test_execute_create_terminal_content_first(
        self,
        executor: TerminalToolExecutor,
        session: SessionState,
    ) -> None:
        """Terminal content идёт первым для быстрого отображения клиентом."""
        executor._bridge.create_terminal = AsyncMock(return_value="term_first")

        result = await executor.execute_create(
            session=session,
            command="test",
        )

        assert result.content is not None
        assert result.content[0]["type"] == "terminal"
        assert result.content[1]["type"] == "content"

    @pytest.mark.asyncio
    async def test_execute_create_content_includes_command(
        self,
        executor: TerminalToolExecutor,
        session: SessionState,
    ) -> None:
        """Text content содержит информацию о команде."""
        executor._bridge.create_terminal = AsyncMock(return_value="term_cmd")

        result = await executor.execute_create(
            session=session,
            command="npm test",
        )

        assert result.content is not None
        text_content = result.content[1]["content"]["text"]
        assert "npm test" in text_content

    @pytest.mark.asyncio
    async def test_execute_create_preserves_output_and_metadata(
        self,
        executor: TerminalToolExecutor,
        session: SessionState,
    ) -> None:
        """execute_create() сохраняет output и metadata."""
        executor._bridge.create_terminal = AsyncMock(return_value="term_full")

        result = await executor.execute_create(
            session=session,
            command="ls",
        )

        assert result.success is True
        assert result.output is not None
        assert "term_full" in result.output
        assert result.metadata is not None
        assert result.metadata["terminal_id"] == "term_full"
        assert result.metadata["command"] == "ls"
        assert result.raw_output == {"terminal_id": "term_full"}

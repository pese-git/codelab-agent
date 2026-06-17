"""Тесты покрытия непокрытых веток MCPToolExecutor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.protocol.state import SessionState
from codelab.server.tools.executors.mcp_executor import MCPToolExecutor


@pytest.fixture
def mock_mcp_manager() -> MagicMock:
    """Создаёт mock MCPManager."""
    manager = MagicMock()
    manager.call_tool = AsyncMock()
    return manager


@pytest.fixture
def session() -> SessionState:
    """Создаёт базовую сессию."""
    return SessionState(
        session_id="test-session",
        cwd="/tmp",
        mcp_servers=[],
    )


class TestMcpContentConversion:
    """Тесты конвертации MCP content."""

    def test_embedded_resource_no_content(self) -> None:
        """Embedded resource без содержимого описывается как пустой (строка 101)."""
        content = [
            {"type": "resource", "resource": {}},
        ]
        result = MCPToolExecutor._convert_mcp_content_to_text(content)
        assert result == "[Embedded resource: no content]"


class TestMcpExecuteResultContent:
    """Тесты обработки результатов MCP с content (строки 155-164)."""

    @pytest.mark.asyncio
    async def test_execute_result_with_empty_content(
        self,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Результат с пустым content возвращает строковое представление (строка 155, 164)."""
        mock_result = MagicMock()
        mock_result.content = []
        mock_mcp_manager.call_tool.return_value = mock_result

        executor = MCPToolExecutor(mock_mcp_manager)
        result = await executor.execute(
            session,
            {
                "tool_name": "mcp:fs:read_file",
                "path": "/tmp/test.txt",
            },
        )

        assert result.success is True
        assert result.output == str(mock_result)

    @pytest.mark.asyncio
    async def test_execute_result_without_content_attribute(
        self,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Результат без атрибута content возвращает строковое представление (строка 164)."""
        mock_mcp_manager.call_tool.return_value = "plain result"

        executor = MCPToolExecutor(mock_mcp_manager)
        result = await executor.execute(
            session,
            {
                "tool_name": "mcp:fs:read_file",
                "path": "/tmp/test.txt",
            },
        )

        assert result.success is True
        assert result.output == "plain result"

    @pytest.mark.asyncio
    async def test_execute_result_with_content_and_error_flag(
        self,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Результат с content и is_error=True возвращает ошибку (строки 155-162)."""
        mock_result = MagicMock()
        mock_result.content = [{"type": "text", "text": "Error details"}]
        mock_result.is_error = True
        mock_mcp_manager.call_tool.return_value = mock_result

        executor = MCPToolExecutor(mock_mcp_manager)
        result = await executor.execute(
            session,
            {
                "tool_name": "mcp:fs:read_file",
                "path": "/tmp/test.txt",
            },
        )

        assert result.success is False
        assert result.output == "Error details"
        assert result.error == "Error details"

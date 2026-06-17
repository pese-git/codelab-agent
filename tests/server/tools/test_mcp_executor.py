"""Тесты для MCPToolExecutor.

Тестирует:
- MCPToolExecutor.is_mcp_tool() — определение MCP инструментов
- MCPToolExecutor.execute() — выполнение MCP инструментов
- Обработка ошибок и отсутствующего MCPManager
- MCP content conversion (text, image, resource)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.protocol.state import SessionState
from codelab.server.tools.base import ToolExecutionResult
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


class TestIsMcpTool:
    """Тесты определения MCP инструментов."""

    def test_mcp_tool_with_namespace(self) -> None:
        """mcp:server:tool определяется как MCP инструмент."""
        assert MCPToolExecutor.is_mcp_tool("mcp:fs:read_file") is True

    def test_mcp_tool_simple(self) -> None:
        """mcp:tool определяется как MCP инструмент."""
        assert MCPToolExecutor.is_mcp_tool("mcp:read_file") is True

    def test_regular_tool_not_mcp(self) -> None:
        """Обычные инструменты не определяются как MCP."""
        assert MCPToolExecutor.is_mcp_tool("fs/read_text_file") is False
        assert MCPToolExecutor.is_mcp_tool("terminal/create") is False
        assert MCPToolExecutor.is_mcp_tool("update_plan") is False

    def test_empty_string_not_mcp(self) -> None:
        """Пустая строка не определяется как MCP."""
        assert MCPToolExecutor.is_mcp_tool("") is False


class TestExecute:
    """Тесты выполнения MCP инструментов."""

    @pytest.mark.asyncio
    async def test_execute_success(
        self,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Успешное выполнение MCP инструмента."""
        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=True,
            output="File content",
        )

        executor = MCPToolExecutor(mock_mcp_manager)
        result = await executor.execute(
            session,
            {
                "tool_name": "mcp:fs:read_file",
                "path": "/tmp/test.txt",
            },
        )

        assert result.success is True
        assert result.output == "File content"
        mock_mcp_manager.call_tool.assert_called_once_with(
            "mcp:fs:read_file",
            {"path": "/tmp/test.txt"},
        )

    @pytest.mark.asyncio
    async def test_execute_failure(
        self,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """MCP инструмент возвращает ошибку."""
        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=False,
            error="File not found",
        )

        executor = MCPToolExecutor(mock_mcp_manager)
        result = await executor.execute(
            session,
            {
                "tool_name": "mcp:fs:read_file",
                "path": "/tmp/nonexistent.txt",
            },
        )

        assert result.success is False
        assert result.error == "File not found"

    @pytest.mark.asyncio
    async def test_execute_exception(
        self,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Исключение при выполнении MCP инструмента."""
        mock_mcp_manager.call_tool.side_effect = Exception("Connection lost")

        executor = MCPToolExecutor(mock_mcp_manager)
        result = await executor.execute(
            session,
            {
                "tool_name": "mcp:fs:read_file",
                "path": "/tmp/test.txt",
            },
        )

        assert result.success is False
        assert "Connection lost" in result.error

    @pytest.mark.asyncio
    async def test_execute_not_mcp_tool(
        self,
        session: SessionState,
    ) -> None:
        """Попытка выполнить не-MCP инструмент через MCPExecutor."""
        executor = MCPToolExecutor(MagicMock())
        result = await executor.execute(
            session,
            {
                "tool_name": "fs/read_text_file",
                "path": "/tmp/test.txt",
            },
        )

        assert result.success is False
        assert "Not an MCP tool" in result.error

    @pytest.mark.asyncio
    async def test_execute_no_mcp_manager(
        self,
        session: SessionState,
    ) -> None:
        """Выполнение без MCPManager (None в конструкторе)."""
        executor = MCPToolExecutor(None)  # type: ignore[arg-type]
        result = await executor.execute(
            session,
            {
                "tool_name": "mcp:fs:read_file",
                "path": "/tmp/test.txt",
            },
        )

        assert result.success is False
        assert "MCP manager not available" in result.error


class TestExecuteTool:
    """Тесты метода execute_tool()."""

    @pytest.mark.asyncio
    async def test_execute_tool_success(
        self,
        session: SessionState,
        mock_mcp_manager: MagicMock,
    ) -> None:
        """Успешное выполнение через execute_tool()."""
        mock_mcp_manager.call_tool.return_value = ToolExecutionResult(
            success=True,
            output="Success",
        )

        executor = MCPToolExecutor(mock_mcp_manager)
        result = await executor.execute_tool(
            "test-session",
            "mcp:fs:read_file",
            {"path": "/tmp/test.txt"},
            session=session,
        )

        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_tool_no_session(self) -> None:
        """Выполнение без сессии."""
        executor = MCPToolExecutor(MagicMock())
        result = await executor.execute_tool(
            "test-session",
            "mcp:fs:read_file",
            {"path": "/tmp/test.txt"},
            session=None,
        )

        assert result.success is False
        assert "Session required" in result.error


class TestMcpContentConversion:
    """Тесты конвертации MCP content в текст."""

    def test_text_content(self) -> None:
        """Текстовый контент конвертируется корректно."""
        content = [
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "World"},
        ]
        result = MCPToolExecutor._convert_mcp_content_to_text(content)
        assert result == "Hello\nWorld"

    def test_image_content(self) -> None:
        """Изображение конвертируется в metadata строку."""
        content = [
            {"type": "image", "mimeType": "image/png", "data": "base64data"},
        ]
        result = MCPToolExecutor._convert_mcp_content_to_text(content)
        assert "[Image: image/png, 10 bytes base64 data]" in result

    def test_embedded_resource_text(self) -> None:
        """Embedded resource с текстом извлекается."""
        content = [
            {
                "type": "resource",
                "resource": {"text": "Resource content", "uri": "file:///test"},
            },
        ]
        result = MCPToolExecutor._convert_mcp_content_to_text(content)
        assert "Resource content" in result

    def test_embedded_resource_blob(self) -> None:
        """Embedded resource с blob описывается."""
        content = [
            {
                "type": "resource",
                "resource": {"blob": "binarydata", "mimeType": "application/pdf"},
            },
        ]
        result = MCPToolExecutor._convert_mcp_content_to_text(content)
        assert "[Embedded resource: application/pdf, blob data]" in result

    def test_embedded_resource_uri_only(self) -> None:
        """Embedded resource с только URI показывает ссылку."""
        content = [
            {"type": "resource", "resource": {"uri": "file:///test.txt"}},
        ]
        result = MCPToolExecutor._convert_mcp_content_to_text(content)
        assert "[Resource link: file:///test.txt]" in result

    def test_mixed_content(self) -> None:
        """Смешанный контент конвертируется."""
        content = [
            {"type": "text", "text": "Before"},
            {"type": "image", "mimeType": "image/png", "data": "img"},
            {"type": "text", "text": "After"},
        ]
        result = MCPToolExecutor._convert_mcp_content_to_text(content)
        assert "Before" in result
        assert "[Image: image/png" in result
        assert "After" in result

    def test_empty_content(self) -> None:
        """Пустой контент возвращает пустую строку."""
        assert MCPToolExecutor._convert_mcp_content_to_text([]) == ""

    def test_unknown_type_serialized(self) -> None:
        """Unknown тип сериализуется как JSON."""
        content = [{"type": "unknown", "data": "test"}]
        result = MCPToolExecutor._convert_mcp_content_to_text(content)
        assert '"type": "unknown"' in result

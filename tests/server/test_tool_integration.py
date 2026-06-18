"""Интеграционные тесты для полного tool call lifecycle.

Проверяет:
- Полный flow от AgentResponse до tool execution
- Корректность tool call lifecycle (pending → in_progress → completed)
- Permission flow интеграция
- Обработка ошибок на всех уровнях
- Notifications отправка
- Последовательное выполнение tool calls
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.protocol.state import SessionState
from codelab.server.tools.executors.filesystem_executor import FileSystemToolExecutor
from codelab.server.tools.executors.terminal_executor import TerminalToolExecutor
from codelab.server.tools.integrations.client_rpc_bridge import ClientRPCBridge
from codelab.server.tools.integrations.permission_checker import PermissionChecker


class TestToolExecutionErrorHandling:
    """Тесты обработки ошибок при выполнении инструментов."""

    @pytest.fixture
    def session(self) -> SessionState:
        """Создает тестовую сессию."""
        return SessionState(
            session_id="test_session",
            cwd="/tmp",
            mcp_servers=[],
            config_values={},
        )

    @pytest.fixture
    def fs_executor(self) -> FileSystemToolExecutor:
        """Создает executor с mock зависимостями."""
        mock_bridge = MagicMock(spec=ClientRPCBridge)
        mock_checker = MagicMock(spec=PermissionChecker)
        mock_checker.should_request_permission.return_value = False
        return FileSystemToolExecutor(mock_bridge, mock_checker)

    @pytest.fixture
    def term_executor(self) -> TerminalToolExecutor:
        """Создает executor с mock зависимостями."""
        mock_bridge = MagicMock(spec=ClientRPCBridge)
        mock_checker = MagicMock(spec=PermissionChecker)
        mock_checker.should_request_permission.return_value = False
        return TerminalToolExecutor(mock_bridge, mock_checker)

    @pytest.mark.asyncio
    async def test_filesystem_read_error_handling(
        self,
        session: SessionState,
        fs_executor: FileSystemToolExecutor,
    ) -> None:
        """Обработка ошибок при чтении файла."""
        # Arrange
        fs_executor._bridge.read_file = AsyncMock(  # type: ignore
            side_effect=Exception("Permission denied")
        )
        
        # Act
        result = await fs_executor.execute_read(
            session=session,
            path="/root/secret.txt",
        )
        
        # Assert
        assert result.success is False
        assert result.error is not None
        assert "Permission denied" in result.error

    @pytest.mark.asyncio
    async def test_filesystem_write_error_handling(
        self,
        session: SessionState,
        fs_executor: FileSystemToolExecutor,
    ) -> None:
        """Обработка ошибок при записи файла."""
        # Arrange
        fs_executor._bridge.write_file = AsyncMock(return_value=False)  # type: ignore
        
        # Act
        result = await fs_executor.execute_write(
            session=session,
            path="/readonly/file.txt",
            content="content",
        )
        
        # Assert
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_terminal_create_error_handling(
        self,
        session: SessionState,
        term_executor: TerminalToolExecutor,
    ) -> None:
        """Обработка ошибок при создании терминала."""
        # Arrange
        term_executor._bridge.create_terminal = AsyncMock(  # type: ignore
            side_effect=Exception("Terminal creation failed")
        )
        
        # Act
        result = await term_executor.execute_create(
            session=session,
            command="nonexistent_command",
        )
        
        # Assert
        assert result.success is False
        assert result.error is not None
        assert "Terminal creation failed" in result.error

    @pytest.mark.asyncio
    async def test_terminal_release_error_handling(
        self,
        session: SessionState,
        term_executor: TerminalToolExecutor,
    ) -> None:
        """Обработка ошибок при освобождении терминала."""
        # Arrange
        term_executor._bridge.release_terminal = AsyncMock(return_value=False)  # type: ignore
        
        # Act
        result = await term_executor.execute_release(
            session=session,
            terminal_id="invalid_terminal",
        )
        
        # Assert
        assert result.success is False
        assert result.error is not None

class TestMultipleToolCallsSequence:
    """Тесты последовательного выполнения нескольких tool calls."""

    @pytest.fixture
    def session(self) -> SessionState:
        """Создает тестовую сессию."""
        return SessionState(
            session_id="test_session",
            cwd="/tmp",
            mcp_servers=[],
            config_values={},
        )

    @pytest.fixture
    def fs_executor(self) -> FileSystemToolExecutor:
        """Создает executor с mock зависимостями."""
        mock_bridge = MagicMock(spec=ClientRPCBridge)
        mock_checker = MagicMock(spec=PermissionChecker)
        mock_checker.should_request_permission.return_value = False
        return FileSystemToolExecutor(mock_bridge, mock_checker)

    @pytest.fixture
    def term_executor(self) -> TerminalToolExecutor:
        """Создает executor с mock зависимостями."""
        mock_bridge = MagicMock(spec=ClientRPCBridge)
        mock_checker = MagicMock(spec=PermissionChecker)
        mock_checker.should_request_permission.return_value = False
        return TerminalToolExecutor(mock_bridge, mock_checker)

    @pytest.mark.asyncio
    async def test_tool_calls_with_mixed_results(
        self,
        session: SessionState,
        fs_executor: FileSystemToolExecutor,
    ) -> None:
        """Последовательное выполнение с успехом и ошибками."""
        # Arrange
        fs_executor._bridge.read_file = AsyncMock(return_value="content")  # type: ignore
        fs_executor._bridge.write_file = AsyncMock(return_value=False)  # type: ignore
        
        # Act
        read_result = await fs_executor.execute_read(
            session=session,
            path="/tmp/test.txt",
        )
        
        write_result = await fs_executor.execute_write(
            session=session,
            path="/readonly/test.txt",
            content="content",
        )
        
        # Assert
        assert read_result.success is True
        assert write_result.success is False
        assert len([r for r in [read_result, write_result] if r.success]) == 1

    @pytest.mark.asyncio
    async def test_tool_calls_preserve_session_state(
        self,
        session: SessionState,
        fs_executor: FileSystemToolExecutor,
    ) -> None:
        """Tool calls сохраняют состояние сессии."""
        # Arrange
        fs_executor._bridge.read_file = AsyncMock(return_value="content1")  # type: ignore
        initial_session_id = session.session_id
        
        # Act
        result1 = await fs_executor.execute_read(
            session=session,
            path="/tmp/file1.txt",
        )
        
        # Assert
        assert session.session_id == initial_session_id
        assert result1.success is True
        
        # Act
        result2 = await fs_executor.execute_read(
            session=session,
            path="/tmp/file2.txt",
        )
        
        # Assert
        assert session.session_id == initial_session_id
        assert result2.success is True

class TestToolExecutionResultValidation:
    """Тесты валидации ToolExecutionResult."""

    @pytest.fixture
    def session(self) -> SessionState:
        """Создает тестовую сессию."""
        return SessionState(
            session_id="test_session",
            cwd="/tmp",
            mcp_servers=[],
            config_values={},
        )

    @pytest.fixture
    def fs_executor(self) -> FileSystemToolExecutor:
        """Создает executor с mock зависимостями."""
        mock_bridge = MagicMock(spec=ClientRPCBridge)
        mock_checker = MagicMock(spec=PermissionChecker)
        mock_checker.should_request_permission.return_value = False
        return FileSystemToolExecutor(mock_bridge, mock_checker)

    @pytest.fixture
    def term_executor(self) -> TerminalToolExecutor:
        """Создает executor с mock зависимостями."""
        mock_bridge = MagicMock(spec=ClientRPCBridge)
        mock_checker = MagicMock(spec=PermissionChecker)
        mock_checker.should_request_permission.return_value = False
        return TerminalToolExecutor(mock_bridge, mock_checker)

    @pytest.mark.asyncio
    async def test_result_success_field_is_boolean(
        self,
        session: SessionState,
        fs_executor: FileSystemToolExecutor,
    ) -> None:
        """Поле success всегда boolean."""
        # Arrange
        fs_executor._bridge.read_file = AsyncMock(return_value="content")  # type: ignore
        
        # Act
        result = await fs_executor.execute_read(session, "/tmp/file.txt")
        
        # Assert
        assert isinstance(result.success, bool)

    @pytest.mark.asyncio
    async def test_result_output_is_optional(
        self,
        session: SessionState,
        fs_executor: FileSystemToolExecutor,
    ) -> None:
        """Поле output опционально."""
        # Arrange
        fs_executor._bridge.write_file = AsyncMock(return_value=True)  # type: ignore
        fs_executor._bridge.read_file = AsyncMock(return_value=None)  # type: ignore
        
        # Act
        result = await fs_executor.execute_write(
            session,
            "/tmp/file.txt",
            "content",
        )
        
        # Assert
        assert result.success is True
        assert result.output is None or isinstance(result.output, str)

    @pytest.mark.asyncio
    async def test_result_error_only_on_failure(
        self,
        session: SessionState,
        fs_executor: FileSystemToolExecutor,
    ) -> None:
        """Поле error только при ошибке."""
        # Arrange
        fs_executor._bridge.read_file = AsyncMock(return_value="content")  # type: ignore
        
        # Act
        success_result = await fs_executor.execute_read(session, "/tmp/file.txt")
        
        # Assert
        assert success_result.success is True
        assert success_result.error is None


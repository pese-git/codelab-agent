"""Unit тесты для FileSystemToolExecutor.

Проверяет:
- Инициализацию с зависимостями
- Успешное выполнение операций чтения и записи
- Обработку ошибок (файл не найден, доступ запрещен)
- Корректность metadata в результатах
- Валидацию ToolExecutionResult
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.client_rpc.exceptions import ClientRPCResponseError
from codelab.server.protocol.state import SessionState
from codelab.server.tools.base import ToolExecutionResult
from codelab.server.tools.executors.filesystem_executor import FileSystemToolExecutor
from codelab.server.tools.integrations.client_rpc_bridge import ClientRPCBridge
from codelab.server.tools.integrations.permission_checker import PermissionChecker


class TestFileSystemExecutorInit:
    """Тесты инициализации FileSystemToolExecutor."""

    def test_filesystem_executor_init(self) -> None:
        """Инициализация с зависимостями."""
        # Arrange
        mock_bridge = MagicMock(spec=ClientRPCBridge)
        mock_checker = MagicMock(spec=PermissionChecker)
        
        # Act
        executor = FileSystemToolExecutor(mock_bridge, mock_checker)
        
        # Assert
        assert executor._bridge == mock_bridge
        assert executor._permission_checker == mock_checker




class TestFileSystemExecutorRead:
    """Тесты операции чтения файлов."""

    @pytest.fixture
    def executor(self) -> FileSystemToolExecutor:
        """Создает executor с mock зависимостями."""
        mock_bridge = MagicMock(spec=ClientRPCBridge)
        mock_checker = MagicMock(spec=PermissionChecker)
        mock_checker.should_request_permission.return_value = False
        return FileSystemToolExecutor(mock_bridge, mock_checker)

    @pytest.fixture
    def session(self) -> SessionState:
        """Создает тестовую сессию."""
        return SessionState(
            session_id="test_session",
            cwd="/tmp",
            mcp_servers=[],
            config_values={},
        )

    @pytest.mark.asyncio
    async def test_execute_read_success(
        self,
        executor: FileSystemToolExecutor,
        session: SessionState,
    ) -> None:
        """Успешное чтение файла."""
        # Arrange
        file_content = "Hello, World!"
        executor._bridge.read_file = AsyncMock(return_value=file_content)  # type: ignore
        executor._bridge.write_file = AsyncMock(return_value=True)  # type: ignore  # type: ignore
        
        # Act
        result = await executor.execute_read(
            session=session,
            path="/tmp/test.txt",
        )
        
        # Assert
        assert result.success is True
        assert result.output == file_content
        assert result.error is None
        executor._bridge.read_file.assert_called_once_with(  # type: ignore
            session=session,
            path="/tmp/test.txt",
            line=None,
            limit=None,
        )

    @pytest.mark.asyncio
    async def test_execute_read_with_line_and_limit(
        self,
        executor: FileSystemToolExecutor,
        session: SessionState,
    ) -> None:
        """Чтение с параметрами line и limit."""
        # Arrange
        file_content = "Line 5\nLine 6\nLine 7"
        executor._bridge.read_file = AsyncMock(return_value=file_content)  # type: ignore
        
        # Act
        result = await executor.execute_read(
            session=session,
            path="/tmp/test.txt",
            line=5,
            limit=3,
        )
        
        # Assert
        assert result.success is True
        assert result.output == file_content
        executor._bridge.read_file.assert_called_once_with(  # type: ignore
            session=session,
            path="/tmp/test.txt",
            line=5,
            limit=3,
        )

    @pytest.mark.asyncio
    async def test_execute_read_file_not_found(
        self,
        executor: FileSystemToolExecutor,
        session: SessionState,
    ) -> None:
        """Обработка ошибки 'файл не найден'."""
        # Arrange
        executor._bridge.read_file = AsyncMock(return_value=None)  # type: ignore
        
        # Act
        result = await executor.execute_read(
            session=session,
            path="/nonexistent/file.txt",
        )
        
        # Assert
        assert result.success is False
        assert result.error is not None
        assert "Ошибка при чтении файла" in result.error
        assert result.output is None

    @pytest.mark.asyncio
    async def test_execute_read_permission_denied(
        self,
        executor: FileSystemToolExecutor,
        session: SessionState,
    ) -> None:
        """Обработка ошибки доступа."""
        # Arrange
        executor._bridge.read_file = AsyncMock(return_value=None)  # type: ignore
        
        # Act
        result = await executor.execute_read(
            session=session,
            path="/root/secret.txt",
        )
        
        # Assert
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_execute_read_exception_handling(
        self,
        executor: FileSystemToolExecutor,
        session: SessionState,
    ) -> None:
        """Обработка исключений при чтении."""
        # Arrange
        executor._bridge.read_file = AsyncMock(  # type: ignore
            side_effect=Exception("Network error")
        )
        
        # Act
        result = await executor.execute_read(
            session=session,
            path="/tmp/test.txt",
        )
        
        # Assert
        assert result.success is False
        assert result.error is not None
        assert "Network error" in result.error

    @pytest.mark.asyncio
    async def test_read_file_directory_returns_error_message(
        self,
        executor: FileSystemToolExecutor,
        session: SessionState,
    ) -> None:
        """Сообщение ClientRPCResponseError доходит до LLM."""
        # Arrange
        executor._bridge.read_file = AsyncMock(  # type: ignore
            side_effect=ClientRPCResponseError(
                code=-32000,
                message="Not a file: /tmp/directory",
            )
        )
        
        # Act
        result = await executor.execute_read(
            session=session,
            path="/tmp/directory",
        )
        
        # Assert
        assert result.success is False
        assert result.error is not None
        assert "Not a file: /tmp/directory" in result.error


class TestFileSystemExecutorWrite:
    """Тесты операции записи файлов."""

    @pytest.fixture
    def executor(self) -> FileSystemToolExecutor:
        """Создает executor с mock зависимостями."""
        mock_bridge = MagicMock(spec=ClientRPCBridge)
        mock_checker = MagicMock(spec=PermissionChecker)
        mock_checker.should_request_permission.return_value = False
        return FileSystemToolExecutor(mock_bridge, mock_checker)

    @pytest.fixture
    def session(self) -> SessionState:
        """Создает тестовую сессию."""
        return SessionState(
            session_id="test_session",
            cwd="/tmp",
            mcp_servers=[],
            config_values={},
        )

    @pytest.mark.asyncio
    async def test_execute_write_success(
        self,
        executor: FileSystemToolExecutor,
        session: SessionState,
    ) -> None:
        """Успешная запись файла."""
        # Arrange
        content = "New file content"
        executor._bridge.write_file = AsyncMock(return_value=True)  # type: ignore
        executor._bridge.read_file = AsyncMock(return_value=None)  # type: ignore
        
        # Act
        result = await executor.execute_write(
            session=session,
            path="/tmp/new_file.txt",
            content=content,
        )
        
        # Assert
        assert result.success is True
        executor._bridge.write_file.assert_called_once_with(  # type: ignore
            session=session,
            path="/tmp/new_file.txt",
            content=content,
        )

    @pytest.mark.asyncio
    async def test_execute_write_permission_denied(
        self,
        executor: FileSystemToolExecutor,
        session: SessionState,
    ) -> None:
        """Обработка ошибки доступа при записи."""
        # Arrange
        executor._bridge.write_file = AsyncMock(return_value=False)  # type: ignore
        
        # Act
        result = await executor.execute_write(
            session=session,
            path="/root/protected.txt",
            content="content",
        )
        
        # Assert
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_execute_write_exception_handling(
        self,
        executor: FileSystemToolExecutor,
        session: SessionState,
    ) -> None:
        """Обработка исключений при записи."""
        # Arrange
        executor._bridge.write_file = AsyncMock(  # type: ignore
            side_effect=Exception("Disk full")
        )
        
        # Act
        result = await executor.execute_write(
            session=session,
            path="/tmp/file.txt",
            content="content",
        )
        
        # Assert
        assert result.success is False
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_write_file_error_propagation(
        self,
        executor: FileSystemToolExecutor,
        session: SessionState,
    ) -> None:
        """Сообщение ClientRPCResponseError при записи доходит до LLM."""
        # Arrange
        executor._bridge.write_file = AsyncMock(  # type: ignore
            side_effect=ClientRPCResponseError(
                code=-32000,
                message="Permission denied: /etc/passwd",
            )
        )
        
        # Act
        result = await executor.execute_write(
            session=session,
            path="/etc/passwd",
            content="malicious content",
        )
        
        # Assert
        assert result.success is False
        assert result.error is not None
        assert "Permission denied: /etc/passwd" in result.error


class TestFileSystemExecutorDispatch:
    """Тесты dispatch методов через execute()."""

    @pytest.fixture
    def executor(self) -> FileSystemToolExecutor:
        """Создает executor с mock зависимостями."""
        mock_bridge = MagicMock(spec=ClientRPCBridge)
        mock_checker = MagicMock(spec=PermissionChecker)
        mock_checker.should_request_permission.return_value = False
        return FileSystemToolExecutor(mock_bridge, mock_checker)

    @pytest.fixture
    def session(self) -> SessionState:
        """Создает тестовую сессию."""
        return SessionState(
            session_id="test_session",
            cwd="/tmp",
            mcp_servers=[],
            config_values={},
        )

    @pytest.mark.asyncio
    async def test_execute_with_read_operation(
        self,
        executor: FileSystemToolExecutor,
        session: SessionState,
    ) -> None:
        """Выполнение операции read через execute()."""
        # Arrange
        executor._bridge.read_file = AsyncMock(return_value="content")  # type: ignore
        arguments = {
            "operation": "read",
            "path": "/tmp/file.txt",
            "line": None,
            "limit": None,
        }
        
        # Act
        result = await executor.execute(session=session, arguments=arguments)
        
        # Assert
        assert result.success is True
        assert result.output == "content"

    @pytest.mark.asyncio
    async def test_execute_with_write_operation(
        self,
        executor: FileSystemToolExecutor,
        session: SessionState,
    ) -> None:
        """Выполнение операции write через execute()."""
        # Arrange
        executor._bridge.write_file = AsyncMock(return_value=True)  # type: ignore
        executor._bridge.read_file = AsyncMock(return_value=None)  # type: ignore
        arguments = {
            "operation": "write",
            "path": "/tmp/file.txt",
            "content": "new content",
        }
        
        # Act
        result = await executor.execute(session=session, arguments=arguments)
        
        # Assert
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_unknown_operation(
        self,
        executor: FileSystemToolExecutor,
        session: SessionState,
    ) -> None:
        """Обработка неизвестной операции."""
        # Arrange
        arguments = {
            "operation": "delete",
            "path": "/tmp/file.txt",
        }
        
        # Act
        result = await executor.execute(session=session, arguments=arguments)
        
        # Assert
        assert result.success is False
        assert result.error is not None
        assert "Неизвестная операция" in result.error

    @pytest.mark.asyncio
    async def test_execute_missing_operation(
        self,
        executor: FileSystemToolExecutor,
        session: SessionState,
    ) -> None:
        """Обработка отсутствия поля operation."""
        # Arrange
        arguments = {
            "path": "/tmp/file.txt",
        }
        
        # Act
        result = await executor.execute(session=session, arguments=arguments)
        
        # Assert
        assert result.success is False
        assert result.error is not None


class TestFileSystemExecutorToolExecutionResult:
    """Тесты структуры ToolExecutionResult."""

    @pytest.fixture
    def executor(self) -> FileSystemToolExecutor:
        """Создает executor с mock зависимостями."""
        mock_bridge = MagicMock(spec=ClientRPCBridge)
        mock_checker = MagicMock(spec=PermissionChecker)
        mock_checker.should_request_permission.return_value = False
        return FileSystemToolExecutor(mock_bridge, mock_checker)

    @pytest.fixture
    def session(self) -> SessionState:
        """Создает тестовую сессию."""
        return SessionState(
            session_id="test_session",
            cwd="/tmp",
            mcp_servers=[],
            config_values={},
        )

    @pytest.mark.asyncio
    async def test_result_has_success_field(
        self,
        executor: FileSystemToolExecutor,
        session: SessionState,
    ) -> None:
        """Результат имеет поле success."""
        # Arrange
        executor._bridge.read_file = AsyncMock(return_value="content")  # type: ignore
        
        # Act
        result = await executor.execute_read(session, "/tmp/file.txt")
        
        # Assert
        assert isinstance(result, ToolExecutionResult)
        assert isinstance(result.success, bool)

    @pytest.mark.asyncio
    async def test_result_success_true_has_output(
        self,
        executor: FileSystemToolExecutor,
        session: SessionState,
    ) -> None:
        """Успешный результат имеет output."""
        # Arrange
        executor._bridge.read_file = AsyncMock(return_value="content")  # type: ignore
        
        # Act
        result = await executor.execute_read(session, "/tmp/file.txt")
        
        # Assert
        assert result.success is True
        assert result.output is not None
        assert result.error is None

    @pytest.mark.asyncio
    async def test_result_failure_has_error(
        self,
        executor: FileSystemToolExecutor,
        session: SessionState,
    ) -> None:
        """Неудачный результат имеет error."""
        # Arrange
        executor._bridge.read_file = AsyncMock(return_value=None)  # type: ignore
        
        # Act
        result = await executor.execute_read(session, "/tmp/file.txt")
        
        # Assert
        assert result.success is False
        assert result.error is not None
        assert result.output is None

    @pytest.mark.asyncio
    async def test_result_metadata_for_write(
        self,
        executor: FileSystemToolExecutor,
        session: SessionState,
    ) -> None:
        """Результат write содержит metadata с bytes."""
        # Arrange
        executor._bridge.write_file = AsyncMock(return_value=True)  # type: ignore
        
        # Act
        result = await executor.execute_write(
            session,
            "/tmp/file.txt",
            "new\ncontent",
        )
        
        # Assert
        assert result.success is True
        assert result.metadata is not None
        assert isinstance(result.metadata, dict)
        assert "bytes" in result.metadata
        assert result.metadata["bytes"] == len("new\ncontent")

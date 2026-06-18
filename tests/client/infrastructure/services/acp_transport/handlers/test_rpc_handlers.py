"""Тесты для RPC обработчиков."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.client.infrastructure.services.acp_transport.contracts import RpcHandler
from codelab.client.infrastructure.services.acp_transport.handlers.fs_read_handler import (
    FsReadHandler,
)
from codelab.client.infrastructure.services.acp_transport.handlers.fs_write_handler import (
    FsWriteHandler,
)
from codelab.client.infrastructure.services.acp_transport.handlers.terminal_create_handler import (
    TerminalCreateHandler,
)
from codelab.client.infrastructure.services.acp_transport.handlers.terminal_kill_handler import (
    TerminalKillHandler,
)
from codelab.client.infrastructure.services.acp_transport.handlers.terminal_output_handler import (
    TerminalOutputHandler,
)
from codelab.client.infrastructure.services.acp_transport.handlers.terminal_release_handler import (
    TerminalReleaseHandler,
)
from codelab.client.infrastructure.services.acp_transport.handlers.terminal_wait_handler import (
    TerminalWaitHandler,
)
from codelab.client.presentation.chat.executors.fs_callback_executor import (
    FsCallbackExecutor,
)
from codelab.client.presentation.chat.executors.terminal_callback_executor import (
    TerminalCallbackExecutor,
)


class TestRpcHandlerProtocol:
    """Тесты для Protocol RpcHandler."""

    def test_fs_read_handler_implements_protocol(self) -> None:
        mock_executor = MagicMock(spec=FsCallbackExecutor)
        handler = FsReadHandler(mock_executor)
        assert isinstance(handler, RpcHandler)

    def test_fs_write_handler_implements_protocol(self) -> None:
        mock_executor = MagicMock(spec=FsCallbackExecutor)
        handler = FsWriteHandler(mock_executor)
        assert isinstance(handler, RpcHandler)

    def test_terminal_create_handler_implements_protocol(self) -> None:
        mock_executor = MagicMock(spec=TerminalCallbackExecutor)
        handler = TerminalCreateHandler(mock_executor)
        assert isinstance(handler, RpcHandler)

    def test_terminal_output_handler_implements_protocol(self) -> None:
        mock_executor = MagicMock(spec=TerminalCallbackExecutor)
        handler = TerminalOutputHandler(mock_executor)
        assert isinstance(handler, RpcHandler)

    def test_terminal_wait_handler_implements_protocol(self) -> None:
        mock_executor = MagicMock(spec=TerminalCallbackExecutor)
        handler = TerminalWaitHandler(mock_executor)
        assert isinstance(handler, RpcHandler)

    def test_terminal_release_handler_implements_protocol(self) -> None:
        mock_executor = MagicMock(spec=TerminalCallbackExecutor)
        handler = TerminalReleaseHandler(mock_executor)
        assert isinstance(handler, RpcHandler)

    def test_terminal_kill_handler_implements_protocol(self) -> None:
        mock_executor = MagicMock(spec=TerminalCallbackExecutor)
        handler = TerminalKillHandler(mock_executor)
        assert isinstance(handler, RpcHandler)


class TestFsReadHandler:
    """Тесты для FsReadHandler."""

    @pytest.fixture
    def mock_executor(self) -> AsyncMock:
        return AsyncMock(spec=FsCallbackExecutor)

    @pytest.fixture
    def handler(self, mock_executor: AsyncMock) -> FsReadHandler:
        return FsReadHandler(mock_executor)

    def test_can_handle_fs_read_text_file(self, handler: FsReadHandler) -> None:
        assert handler.can_handle("fs/read_text_file") is True

    def test_cannot_handle_other_methods(self, handler: FsReadHandler) -> None:
        assert handler.can_handle("fs/write_text_file") is False
        assert handler.can_handle("terminal/create") is False
        assert handler.can_handle("unknown") is False

    async def test_handle_success(
        self, handler: FsReadHandler, mock_executor: AsyncMock
    ) -> None:
        mock_executor.read_file.return_value = ("file content", None)

        result = await handler.handle("rpc-1", {"path": "test.txt"})

        assert result == {"content": "file content"}
        mock_executor.read_file.assert_called_once_with("test.txt")

    async def test_handle_missing_path(
        self, handler: FsReadHandler, mock_executor: AsyncMock
    ) -> None:
        result = await handler.handle("rpc-1", {})

        assert result == {"error": {"code": -32602, "message": "Missing required parameter: path"}}
        mock_executor.read_file.assert_not_called()

    async def test_handle_path_not_string(
        self, handler: FsReadHandler, mock_executor: AsyncMock
    ) -> None:
        result = await handler.handle("rpc-1", {"path": 123})

        assert result == {"error": {"code": -32602, "message": "Missing required parameter: path"}}
        mock_executor.read_file.assert_not_called()

    async def test_handle_executor_error(
        self, handler: FsReadHandler, mock_executor: AsyncMock
    ) -> None:
        mock_executor.read_file.return_value = (None, "File not found: missing.txt")

        result = await handler.handle("rpc-1", {"path": "missing.txt"})

        assert result == {"error": {"code": -32603, "message": "File not found: missing.txt"}}

    async def test_handle_permission_denied(
        self, handler: FsReadHandler, mock_executor: AsyncMock
    ) -> None:
        mock_executor.read_file.return_value = (None, "Permission denied: secret.txt")

        result = await handler.handle("rpc-1", {"path": "secret.txt"})

        assert result == {"error": {"code": -32603, "message": "Permission denied: secret.txt"}}


class TestFsWriteHandler:
    """Тесты для FsWriteHandler."""

    @pytest.fixture
    def mock_executor(self) -> AsyncMock:
        return AsyncMock(spec=FsCallbackExecutor)

    @pytest.fixture
    def handler(self, mock_executor: AsyncMock) -> FsWriteHandler:
        return FsWriteHandler(mock_executor)

    def test_can_handle_fs_write_text_file(self, handler: FsWriteHandler) -> None:
        assert handler.can_handle("fs/write_text_file") is True

    def test_cannot_handle_other_methods(self, handler: FsWriteHandler) -> None:
        assert handler.can_handle("fs/read_text_file") is False
        assert handler.can_handle("terminal/create") is False

    async def test_handle_success(
        self, handler: FsWriteHandler, mock_executor: AsyncMock
    ) -> None:
        mock_executor.write_file.return_value = (True, None)

        result = await handler.handle("rpc-1", {"path": "test.txt", "content": "hello"})

        assert result == {}
        mock_executor.write_file.assert_called_once_with("test.txt", "hello")

    async def test_handle_missing_path(
        self, handler: FsWriteHandler, mock_executor: AsyncMock
    ) -> None:
        result = await handler.handle("rpc-1", {"content": "hello"})

        assert result == {"error": {"code": -32602, "message": "Missing required parameter: path"}}
        mock_executor.write_file.assert_not_called()

    async def test_handle_missing_content(
        self, handler: FsWriteHandler, mock_executor: AsyncMock
    ) -> None:
        result = await handler.handle("rpc-1", {"path": "test.txt"})

        expected = {"error": {"code": -32602, "message": "Missing required parameter: content"}}
        assert result == expected
        mock_executor.write_file.assert_not_called()

    async def test_handle_executor_error(
        self, handler: FsWriteHandler, mock_executor: AsyncMock
    ) -> None:
        mock_executor.write_file.return_value = (False, "Permission denied")

        result = await handler.handle("rpc-1", {"path": "test.txt", "content": "hello"})

        assert result == {"error": {"code": -32603, "message": "Permission denied"}}


class TestTerminalCreateHandler:
    """Тесты для TerminalCreateHandler."""

    @pytest.fixture
    def mock_executor(self) -> AsyncMock:
        return AsyncMock(spec=TerminalCallbackExecutor)

    @pytest.fixture
    def handler(self, mock_executor: AsyncMock) -> TerminalCreateHandler:
        return TerminalCreateHandler(mock_executor)

    def test_can_handle_terminal_create(self, handler: TerminalCreateHandler) -> None:
        assert handler.can_handle("terminal/create") is True

    def test_cannot_handle_other_methods(self, handler: TerminalCreateHandler) -> None:
        assert handler.can_handle("terminal/output") is False
        assert handler.can_handle("fs/read_text_file") is False

    async def test_handle_success(
        self, handler: TerminalCreateHandler, mock_executor: AsyncMock
    ) -> None:
        mock_executor.create_terminal.return_value = ("term-123", None)

        result = await handler.handle("rpc-1", {"command": "ls -la"})

        assert result == {"terminalId": "term-123"}
        mock_executor.create_terminal.assert_called_once_with("ls -la")

    async def test_handle_missing_command(
        self, handler: TerminalCreateHandler, mock_executor: AsyncMock
    ) -> None:
        result = await handler.handle("rpc-1", {})

        expected = {"error": {"code": -32602, "message": "Missing required parameter: command"}}
        assert result == expected
        mock_executor.create_terminal.assert_not_called()

    async def test_handle_executor_error(
        self, handler: TerminalCreateHandler, mock_executor: AsyncMock
    ) -> None:
        mock_executor.create_terminal.return_value = (None, "Failed to create terminal")

        result = await handler.handle("rpc-1", {"command": "ls"})

        assert result == {"error": {"code": -32603, "message": "Failed to create terminal"}}

    async def test_handle_empty_command_error(
        self, handler: TerminalCreateHandler, mock_executor: AsyncMock
    ) -> None:
        mock_executor.create_terminal.return_value = (None, "Command cannot be empty")

        result = await handler.handle("rpc-1", {"command": ""})

        assert result == {"error": {"code": -32603, "message": "Command cannot be empty"}}


class TestTerminalOutputHandler:
    """Тесты для TerminalOutputHandler."""

    @pytest.fixture
    def mock_executor(self) -> AsyncMock:
        return AsyncMock(spec=TerminalCallbackExecutor)

    @pytest.fixture
    def handler(self, mock_executor: AsyncMock) -> TerminalOutputHandler:
        return TerminalOutputHandler(mock_executor)

    def test_can_handle_terminal_output(self, handler: TerminalOutputHandler) -> None:
        assert handler.can_handle("terminal/output") is True

    def test_cannot_handle_other_methods(self, handler: TerminalOutputHandler) -> None:
        assert handler.can_handle("terminal/create") is False
        assert handler.can_handle("terminal/wait_for_exit") is False

    async def test_handle_success(
        self, handler: TerminalOutputHandler, mock_executor: AsyncMock
    ) -> None:
        output_data = {"output": "hello world", "isComplete": True, "exitCode": 0}
        mock_executor.get_output.return_value = (output_data, None)

        result = await handler.handle("rpc-1", {"terminalId": "term-123"})

        assert result == output_data
        mock_executor.get_output.assert_called_once_with("term-123")

    async def test_handle_missing_terminal_id(
        self, handler: TerminalOutputHandler, mock_executor: AsyncMock
    ) -> None:
        result = await handler.handle("rpc-1", {})

        expected = {"error": {"code": -32602, "message": "Missing required parameter: terminalId"}}
        assert result == expected
        mock_executor.get_output.assert_not_called()

    async def test_handle_terminal_not_found(
        self, handler: TerminalOutputHandler, mock_executor: AsyncMock
    ) -> None:
        mock_executor.get_output.return_value = (None, "Terminal not found: term-999")

        result = await handler.handle("rpc-1", {"terminalId": "term-999"})

        assert result == {"error": {"code": -32603, "message": "Terminal not found: term-999"}}


class TestTerminalWaitHandler:
    """Тесты для TerminalWaitHandler."""

    @pytest.fixture
    def mock_executor(self) -> AsyncMock:
        return AsyncMock(spec=TerminalCallbackExecutor)

    @pytest.fixture
    def handler(self, mock_executor: AsyncMock) -> TerminalWaitHandler:
        return TerminalWaitHandler(mock_executor)

    def test_can_handle_terminal_wait_for_exit(self, handler: TerminalWaitHandler) -> None:
        assert handler.can_handle("terminal/wait_for_exit") is True

    def test_cannot_handle_other_methods(self, handler: TerminalWaitHandler) -> None:
        assert handler.can_handle("terminal/output") is False
        assert handler.can_handle("terminal/release") is False

    async def test_handle_success_with_exit_code_and_output(
        self, handler: TerminalWaitHandler, mock_executor: AsyncMock
    ) -> None:
        mock_executor.wait_for_exit.return_value = ((0, "done"), None)

        result = await handler.handle("rpc-1", {"terminalId": "term-123"})

        assert result == {"exitCode": 0, "output": "done"}

    async def test_handle_success_with_exit_code_only(
        self, handler: TerminalWaitHandler, mock_executor: AsyncMock
    ) -> None:
        mock_executor.wait_for_exit.return_value = ((1, None), None)

        result = await handler.handle("rpc-1", {"terminalId": "term-123"})

        assert result == {"exitCode": 1}

    async def test_handle_success_with_output_only(
        self, handler: TerminalWaitHandler, mock_executor: AsyncMock
    ) -> None:
        mock_executor.wait_for_exit.return_value = ((None, "partial output"), None)

        result = await handler.handle("rpc-1", {"terminalId": "term-123"})

        assert result == {"output": "partial output"}

    async def test_handle_missing_terminal_id(
        self, handler: TerminalWaitHandler, mock_executor: AsyncMock
    ) -> None:
        result = await handler.handle("rpc-1", {})

        expected = {"error": {"code": -32602, "message": "Missing required parameter: terminalId"}}
        assert result == expected

    async def test_handle_error(
        self, handler: TerminalWaitHandler, mock_executor: AsyncMock
    ) -> None:
        mock_executor.wait_for_exit.return_value = (None, "Terminal not found")

        result = await handler.handle("rpc-1", {"terminalId": "term-999"})

        assert result == {"error": {"code": -32603, "message": "Terminal not found"}}


class TestTerminalReleaseHandler:
    """Тесты для TerminalReleaseHandler."""

    @pytest.fixture
    def mock_executor(self) -> AsyncMock:
        return AsyncMock(spec=TerminalCallbackExecutor)

    @pytest.fixture
    def handler(self, mock_executor: AsyncMock) -> TerminalReleaseHandler:
        return TerminalReleaseHandler(mock_executor)

    def test_can_handle_terminal_release(self, handler: TerminalReleaseHandler) -> None:
        assert handler.can_handle("terminal/release") is True

    def test_cannot_handle_other_methods(self, handler: TerminalReleaseHandler) -> None:
        assert handler.can_handle("terminal/kill") is False
        assert handler.can_handle("terminal/create") is False

    async def test_handle_success(
        self, handler: TerminalReleaseHandler, mock_executor: AsyncMock
    ) -> None:
        mock_executor.release_terminal.return_value = None

        result = await handler.handle("rpc-1", {"terminalId": "term-123"})

        assert result == {}
        mock_executor.release_terminal.assert_called_once_with("term-123")

    async def test_handle_missing_terminal_id(
        self, handler: TerminalReleaseHandler, mock_executor: AsyncMock
    ) -> None:
        result = await handler.handle("rpc-1", {})

        expected = {"error": {"code": -32602, "message": "Missing required parameter: terminalId"}}
        assert result == expected

    async def test_handle_error(
        self, handler: TerminalReleaseHandler, mock_executor: AsyncMock
    ) -> None:
        mock_executor.release_terminal.return_value = "Terminal not found"

        result = await handler.handle("rpc-1", {"terminalId": "term-999"})

        assert result == {"error": {"code": -32603, "message": "Terminal not found"}}


class TestTerminalKillHandler:
    """Тесты для TerminalKillHandler."""

    @pytest.fixture
    def mock_executor(self) -> AsyncMock:
        return AsyncMock(spec=TerminalCallbackExecutor)

    @pytest.fixture
    def handler(self, mock_executor: AsyncMock) -> TerminalKillHandler:
        return TerminalKillHandler(mock_executor)

    def test_can_handle_terminal_kill(self, handler: TerminalKillHandler) -> None:
        assert handler.can_handle("terminal/kill") is True

    def test_cannot_handle_other_methods(self, handler: TerminalKillHandler) -> None:
        assert handler.can_handle("terminal/release") is False
        assert handler.can_handle("terminal/create") is False

    async def test_handle_success(
        self, handler: TerminalKillHandler, mock_executor: AsyncMock
    ) -> None:
        mock_executor.kill_terminal.return_value = (True, None)

        result = await handler.handle("rpc-1", {"terminalId": "term-123"})

        assert result == {}
        mock_executor.kill_terminal.assert_called_once_with("term-123")

    async def test_handle_missing_terminal_id(
        self, handler: TerminalKillHandler, mock_executor: AsyncMock
    ) -> None:
        result = await handler.handle("rpc-1", {})

        expected = {"error": {"code": -32602, "message": "Missing required parameter: terminalId"}}
        assert result == expected

    async def test_handle_error(
        self, handler: TerminalKillHandler, mock_executor: AsyncMock
    ) -> None:
        mock_executor.kill_terminal.return_value = (False, "Terminal not found")

        result = await handler.handle("rpc-1", {"terminalId": "term-999"})

        assert result == {"error": {"code": -32603, "message": "Terminal not found"}}

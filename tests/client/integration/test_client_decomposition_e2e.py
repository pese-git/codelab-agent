"""End-to-end интеграционные тесты для декомпозиции клиента.

Тестируют полные потоки данных через все слои архитектуры:
- Session update flow: сервер → транспорт → диспетчер → обработчик → UI
- Chat persistence flow: сохранение → загрузка → проверка
- FS callback flow: RPC сервера → диспетчер → обработчик → исполнитель → ответ
- Terminal callback flow: создание → вывод → ожидание → освобождение
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from codelab.client.infrastructure.services.acp_transport.client_rpc_dispatcher import (
    ClientRpcDispatcher,
)
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
from codelab.client.presentation.chat.chat_session_state import ChatSessionState
from codelab.client.presentation.chat.context import ChatUpdateContext
from codelab.client.presentation.chat.dispatcher.session_update_dispatcher import (
    SessionUpdateDispatcher,
)
from codelab.client.presentation.chat.executors.fs_callback_executor import (
    FsCallbackExecutor,
)
from codelab.client.presentation.chat.executors.terminal_callback_executor import (
    TerminalCallbackExecutor,
    TerminalExecutorPort,
)
from codelab.client.presentation.chat.handlers.config_option_handler import (
    ConfigOptionHandler,
)
from codelab.client.presentation.chat.handlers.message_chunk_handler import (
    MessageChunkHandler,
)
from codelab.client.presentation.chat.handlers.plan_update_handler import (
    PlanUpdateHandler,
)
from codelab.client.presentation.chat.handlers.tool_call_handler import (
    ToolCallHandler,
)
from codelab.client.presentation.chat.persistence.file_chat_persistence import (
    FileChatPersistence,
)


class MockSink:
    """Mock реализация ChatUpdateSink для тестов."""

    def __init__(self) -> None:
        self.synced_messages: list[tuple[str, list[dict[str, str]]]] = []
        self.synced_tool_calls: list[tuple[str, list[dict[str, Any]]]] = []
        self.synced_streaming: list[tuple[str, str, bool]] = []

    def sync_messages(self, session_id: str, messages: list[dict[str, str]]) -> None:
        self.synced_messages.append((session_id, list(messages)))

    def sync_tool_calls(
        self, session_id: str, tool_calls: list[dict[str, Any]]
    ) -> None:
        self.synced_tool_calls.append((session_id, list(tool_calls)))

    def sync_streaming(
        self, session_id: str, text: str, is_streaming: bool
    ) -> None:
        self.synced_streaming.append((session_id, text, is_streaming))


class MockTerminalExecutor(TerminalExecutorPort):
    """Mock реализация TerminalExecutorPort для тестов."""

    def __init__(self) -> None:
        self._terminals: dict[str, dict[str, Any]] = {}
        self._counter = 0

    async def create_terminal(self, command: str) -> str:
        self._counter += 1
        terminal_id = f"real-term-{self._counter}"
        self._terminals[terminal_id] = {
            "command": command,
            "output": f"Output of: {command}",
            "exit_code": 0,
            "released": False,
        }
        return terminal_id

    async def get_output(self, terminal_id: str) -> dict[str, Any]:
        terminal = self._terminals.get(terminal_id)
        if terminal is None:
            raise ValueError(f"Terminal not found: {terminal_id}")
        return {
            "output": terminal["output"],
            "isComplete": True,
            "exitCode": terminal["exit_code"],
        }

    async def wait_for_exit(self, terminal_id: str) -> tuple[int | None, str | None]:
        terminal = self._terminals.get(terminal_id)
        if terminal is None:
            raise ValueError(f"Terminal not found: {terminal_id}")
        return (terminal["exit_code"], terminal["output"])

    async def release_terminal(self, terminal_id: str) -> None:
        terminal = self._terminals.get(terminal_id)
        if terminal is None:
            raise ValueError(f"Terminal not found: {terminal_id}")
        terminal["released"] = True

    async def kill_terminal(self, terminal_id: str) -> bool:
        terminal = self._terminals.get(terminal_id)
        if terminal is None:
            return False
        self._terminals.pop(terminal_id, None)
        return True


class TestSessionUpdateFlowE2E:
    """End-to-end тесты для потока обновления сессии.

    Тестирует полный поток: сервер → диспетчер → обработчик → sink → UI
    """

    @pytest.fixture
    def session_state(self) -> ChatSessionState:
        """Создаёт ChatSessionState."""
        return ChatSessionState()

    @pytest.fixture
    def sink(self) -> MockSink:
        """Создаёт MockSink."""
        return MockSink()

    @pytest.fixture
    def dispatcher(self) -> SessionUpdateDispatcher:
        """Создаёт SessionUpdateDispatcher с реальными обработчиками."""
        return SessionUpdateDispatcher(
            message_chunk_handler=MessageChunkHandler(),
            tool_call_handler=ToolCallHandler(),
            plan_update_handler=PlanUpdateHandler(),
            config_option_handler=ConfigOptionHandler(),
        )

    @pytest.fixture
    def context(
        self, session_state: ChatSessionState, sink: MockSink
    ) -> ChatUpdateContext:
        """Создаёт ChatUpdateContext."""
        return ChatUpdateContext(
            session_id="test-session",
            state=session_state,
            sink=sink,
        )

    def test_agent_message_chunk_flow(
        self,
        dispatcher: SessionUpdateDispatcher,
        context: ChatUpdateContext,
        sink: MockSink,
    ) -> None:
        """Тестирует полный поток agent_message_chunk."""
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": "Hello, world!"},
                }
            }
        }

        dispatcher.dispatch_with_context(update_data, context)

        assert len(sink.synced_streaming) == 1
        session_id, text, is_streaming = sink.synced_streaming[0]
        assert session_id == "test-session"
        assert text == "Hello, world!"
        assert is_streaming is True

    def test_tool_call_flow(
        self,
        dispatcher: SessionUpdateDispatcher,
        context: ChatUpdateContext,
        sink: MockSink,
    ) -> None:
        """Тестирует полный поток tool_call."""
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": "tool-1",
                    "title": "Read file",
                    "status": "pending",
                    "kind": "fs",
                }
            }
        }

        dispatcher.dispatch_with_context(update_data, context)

        assert len(sink.synced_tool_calls) == 1
        session_id, tool_calls = sink.synced_tool_calls[0]
        assert session_id == "test-session"
        assert len(tool_calls) == 1
        assert tool_calls[0]["toolCallId"] == "tool-1"
        assert tool_calls[0]["title"] == "Read file"

    def test_multiple_updates_flow(
        self,
        dispatcher: SessionUpdateDispatcher,
        context: ChatUpdateContext,
        sink: MockSink,
    ) -> None:
        """Тестирует поток множественных обновлений."""
        updates = [
            {
                "params": {
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": "First"},
                    }
                }
            },
            {
                "params": {
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": "Second"},
                    }
                }
            },
            {
                "params": {
                    "update": {
                        "sessionUpdate": "tool_call",
                        "toolCallId": "tool-1",
                        "title": "Tool 1",
                        "status": "pending",
                    }
                }
            },
        ]

        for update in updates:
            dispatcher.dispatch_with_context(update, context)

        assert len(sink.synced_streaming) == 2
        assert len(sink.synced_tool_calls) == 1


class TestChatPersistenceFlowE2E:
    """End-to-end тесты для потока сохранения чата.

    Тестирует полный поток: сохранение → загрузка → проверка
    """

    @pytest.fixture
    def temp_dir(self, tmp_path: Path) -> Path:
        """Создаёт временную директорию для тестов."""
        return tmp_path / "history"

    @pytest.fixture
    def persistence(self, temp_dir: Path) -> FileChatPersistence:
        """Создаёт FileChatPersistence."""
        return FileChatPersistence(temp_dir)

    async def test_save_and_load_messages_flow(
        self, persistence: FileChatPersistence
    ) -> None:
        """Тестирует полный поток сохранения и загрузки сообщений."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
        ]

        await persistence.save_messages("session-1", messages)
        loaded = await persistence.load_messages("session-1")

        assert loaded == messages

    async def test_save_and_load_with_replay_updates_flow(
        self, persistence: FileChatPersistence
    ) -> None:
        """Тестирует полный поток с replay updates."""
        messages = [{"role": "user", "content": "Hello"}]
        replay_updates = [
            {"params": {"update": {"sessionUpdate": "agent_message_chunk", "content": "Hi"}}},
            {"params": {"update": {"sessionUpdate": "tool_call", "toolCallId": "tool-1"}}},
        ]

        await persistence.save_messages("session-1", messages, replay_updates)

        loaded_messages = await persistence.load_messages("session-1")
        loaded_updates = await persistence.load_replay_updates("session-1")

        assert loaded_messages == messages
        assert loaded_updates == replay_updates

    async def test_multiple_sessions_flow(
        self, persistence: FileChatPersistence
    ) -> None:
        """Тестирует поток с множественными сессиями."""
        session1_messages = [{"role": "user", "content": "Session 1"}]
        session2_messages = [{"role": "user", "content": "Session 2"}]

        await persistence.save_messages("session-1", session1_messages)
        await persistence.save_messages("session-2", session2_messages)

        loaded1 = await persistence.load_messages("session-1")
        loaded2 = await persistence.load_messages("session-2")

        assert loaded1 == session1_messages
        assert loaded2 == session2_messages


class TestFsCallbackFlowE2E:
    """End-to-end тесты для потока FS callback.

    Тестирует полный поток: RPC сервера → диспетчер → обработчик → исполнитель → ответ
    """

    @pytest.fixture
    def temp_dir(self, tmp_path: Path) -> Path:
        """Создаёт временную директорию для FS операций."""
        test_dir = tmp_path / "workspace"
        test_dir.mkdir()
        return test_dir

    @pytest.fixture
    def fs_executor(self, temp_dir: Path) -> FsCallbackExecutor:
        """Создаёт FsCallbackExecutor."""
        return FsCallbackExecutor(temp_dir)

    @pytest.fixture
    def fs_read_handler(self, fs_executor: FsCallbackExecutor) -> FsReadHandler:
        """Создаёт FsReadHandler."""
        return FsReadHandler(fs_executor)

    @pytest.fixture
    def fs_write_handler(self, fs_executor: FsCallbackExecutor) -> FsWriteHandler:
        """Создаёт FsWriteHandler."""
        return FsWriteHandler(fs_executor)

    @pytest.fixture
    def dispatcher(
        self, fs_read_handler: FsReadHandler, fs_write_handler: FsWriteHandler
    ) -> ClientRpcDispatcher:
        """Создаёт ClientRpcDispatcher."""
        handlers: list[RpcHandler] = [fs_read_handler, fs_write_handler]
        return ClientRpcDispatcher(handlers)

    async def test_fs_write_and_read_flow(
        self, dispatcher: ClientRpcDispatcher, temp_dir: Path
    ) -> None:
        """Тестирует полный поток записи и чтения файла."""
        write_result = await dispatcher.dispatch(
            "fs/write_text_file",
            "rpc-1",
            {"path": "test.txt", "content": "Hello, World!"},
        )

        assert "error" not in write_result

        read_result = await dispatcher.dispatch(
            "fs/read_text_file",
            "rpc-2",
            {"path": "test.txt"},
        )

        assert read_result == {"content": "Hello, World!"}

    async def test_fs_read_nonexistent_file_flow(
        self, dispatcher: ClientRpcDispatcher
    ) -> None:
        """Тестирует поток чтения несуществующего файла."""
        result = await dispatcher.dispatch(
            "fs/read_text_file",
            "rpc-1",
            {"path": "nonexistent.txt"},
        )

        assert "error" in result
        assert result["error"]["code"] == -32603

    async def test_fs_path_traversal_protection_flow(
        self, dispatcher: ClientRpcDispatcher
    ) -> None:
        """Тестирует защиту от path traversal атак."""
        result = await dispatcher.dispatch(
            "fs/read_text_file",
            "rpc-1",
            {"path": "../../../etc/passwd"},
        )

        assert "error" in result
        assert result["error"]["code"] == -32603


class TestTerminalCallbackFlowE2E:
    """End-to-end тесты для потока Terminal callback.

    Тестирует полный поток: создание → вывод → ожидание → освобождение
    """

    @pytest.fixture
    def mock_terminal_executor(self) -> MockTerminalExecutor:
        """Создаёт MockTerminalExecutor."""
        return MockTerminalExecutor()

    @pytest.fixture
    def terminal_executor(
        self, mock_terminal_executor: MockTerminalExecutor
    ) -> TerminalCallbackExecutor:
        """Создаёт TerminalCallbackExecutor."""
        return TerminalCallbackExecutor(mock_terminal_executor)

    @pytest.fixture
    def terminal_create_handler(
        self, terminal_executor: TerminalCallbackExecutor
    ) -> TerminalCreateHandler:
        """Создаёт TerminalCreateHandler."""
        return TerminalCreateHandler(terminal_executor)

    @pytest.fixture
    def terminal_output_handler(
        self, terminal_executor: TerminalCallbackExecutor
    ) -> TerminalOutputHandler:
        """Создаёт TerminalOutputHandler."""
        return TerminalOutputHandler(terminal_executor)

    @pytest.fixture
    def terminal_wait_handler(
        self, terminal_executor: TerminalCallbackExecutor
    ) -> TerminalWaitHandler:
        """Создаёт TerminalWaitHandler."""
        return TerminalWaitHandler(terminal_executor)

    @pytest.fixture
    def terminal_release_handler(
        self, terminal_executor: TerminalCallbackExecutor
    ) -> TerminalReleaseHandler:
        """Создаёт TerminalReleaseHandler."""
        return TerminalReleaseHandler(terminal_executor)

    @pytest.fixture
    def terminal_kill_handler(
        self, terminal_executor: TerminalCallbackExecutor
    ) -> TerminalKillHandler:
        """Создаёт TerminalKillHandler."""
        return TerminalKillHandler(terminal_executor)

    @pytest.fixture
    def dispatcher(
        self,
        terminal_create_handler: TerminalCreateHandler,
        terminal_output_handler: TerminalOutputHandler,
        terminal_wait_handler: TerminalWaitHandler,
        terminal_release_handler: TerminalReleaseHandler,
        terminal_kill_handler: TerminalKillHandler,
    ) -> ClientRpcDispatcher:
        """Создаёт ClientRpcDispatcher."""
        handlers: list[RpcHandler] = [
            terminal_create_handler,
            terminal_output_handler,
            terminal_wait_handler,
            terminal_release_handler,
            terminal_kill_handler,
        ]
        return ClientRpcDispatcher(handlers)

    async def test_terminal_lifecycle_flow(
        self, dispatcher: ClientRpcDispatcher
    ) -> None:
        """Тестирует полный жизненный цикл терминала."""
        create_result = await dispatcher.dispatch(
            "terminal/create",
            "rpc-1",
            {"command": "ls -la"},
        )

        assert "error" not in create_result
        assert "terminalId" in create_result
        terminal_id = create_result["terminalId"]

        output_result = await dispatcher.dispatch(
            "terminal/output",
            "rpc-2",
            {"terminalId": terminal_id},
        )

        assert "error" not in output_result
        assert "output" in output_result

        wait_result = await dispatcher.dispatch(
            "terminal/wait_for_exit",
            "rpc-3",
            {"terminalId": terminal_id},
        )

        assert "error" not in wait_result
        assert "exitCode" in wait_result

        release_result = await dispatcher.dispatch(
            "terminal/release",
            "rpc-4",
            {"terminalId": terminal_id},
        )

        assert "error" not in release_result

    async def test_terminal_kill_flow(
        self, dispatcher: ClientRpcDispatcher
    ) -> None:
        """Тестирует поток принудительного завершения терминала."""
        create_result = await dispatcher.dispatch(
            "terminal/create",
            "rpc-1",
            {"command": "sleep 100"},
        )

        assert "error" not in create_result
        terminal_id = create_result["terminalId"]

        kill_result = await dispatcher.dispatch(
            "terminal/kill",
            "rpc-2",
            {"terminalId": terminal_id},
        )

        assert "error" not in kill_result

        output_result = await dispatcher.dispatch(
            "terminal/output",
            "rpc-3",
            {"terminalId": terminal_id},
        )

        assert "error" in output_result


class TestErrorScenariosE2E:
    """End-to-end тесты для сценариев ошибок.

    Тестирует обработку ошибок во всех потоках.
    """

    @pytest.fixture
    def temp_dir(self, tmp_path: Path) -> Path:
        """Создаёт временную директорию для FS операций."""
        test_dir = tmp_path / "workspace"
        test_dir.mkdir()
        return test_dir

    @pytest.fixture
    def fs_executor(self, temp_dir: Path) -> FsCallbackExecutor:
        """Создаёт FsCallbackExecutor."""
        return FsCallbackExecutor(temp_dir)

    @pytest.fixture
    def dispatcher(self, fs_executor: FsCallbackExecutor) -> ClientRpcDispatcher:
        """Создаёт ClientRpcDispatcher."""
        handlers: list[RpcHandler] = [
            FsReadHandler(fs_executor),
            FsWriteHandler(fs_executor),
        ]
        return ClientRpcDispatcher(handlers)

    async def test_missing_required_parameter_flow(
        self, dispatcher: ClientRpcDispatcher
    ) -> None:
        """Тестирует поток с отсутствующими обязательными параметрами."""
        result = await dispatcher.dispatch(
            "fs/read_text_file",
            "rpc-1",
            {},
        )

        assert "error" in result
        assert result["error"]["code"] == -32602
        assert "Missing required parameter" in result["error"]["message"]

    async def test_unknown_rpc_method_flow(
        self, dispatcher: ClientRpcDispatcher
    ) -> None:
        """Тестирует поток с неизвестным методом RPC."""
        result = await dispatcher.dispatch(
            "unknown/method",
            "rpc-1",
            {},
        )

        assert "error" in result
        assert result["error"]["code"] == -32601
        assert "Method not found" in result["error"]["message"]

    async def test_handler_exception_flow(
        self, dispatcher: ClientRpcDispatcher
    ) -> None:
        """Тестирует поток с исключением в обработчике."""
        result = await dispatcher.dispatch(
            "fs/read_text_file",
            "rpc-1",
            {"path": "nonexistent.txt"},
        )

        assert "error" in result
        assert result["error"]["code"] == -32603

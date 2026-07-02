"""Интеграционные тесты для компонентов декомпозиции ChatViewModel.

Проверяют работу всех компонентов вместе:
- SessionUpdateDispatcher → handlers → ChatUpdateSink
- ChatPersistencePort → FileChatPersistence
- FsCallbackExecutor → файловые операции
- TerminalCallbackExecutor → терминальные операции
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from codelab.client.infrastructure.events.bus import EventBus
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
from codelab.client.presentation.chat.handlers.tool_call_handler import ToolCallHandler
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
        self.terminals: dict[str, dict[str, Any]] = {}
        self._counter = 0

    async def create_terminal(self, command: str) -> str:
        self._counter += 1
        terminal_id = f"term_{self._counter}"
        self.terminals[terminal_id] = {
            "command": command,
            "output": f"Output for: {command}",
            "exit_code": 0,
            "is_released": False,
        }
        return terminal_id

    async def get_output(self, terminal_id: str) -> tuple[str, bool, int | None, bool]:
        terminal = self.terminals.get(terminal_id)
        if not terminal:
            return ("", True, None, False)
        return (
            terminal["output"],
            True,
            terminal["exit_code"],
            False,
        )

    async def wait_for_exit(self, terminal_id: str) -> tuple[int | None, str | None]:
        terminal = self.terminals.get(terminal_id)
        if not terminal:
            return (None, None)
        return (terminal["exit_code"], terminal["output"])

    async def release_terminal(self, terminal_id: str) -> None:
        if terminal_id in self.terminals:
            self.terminals[terminal_id]["is_released"] = True

    async def kill_terminal(self, terminal_id: str) -> bool:
        if terminal_id in self.terminals:
            del self.terminals[terminal_id]
            return True
        return False


class TestDispatcherIntegration:
    """Интеграционные тесты для SessionUpdateDispatcher."""

    @pytest.fixture
    def dispatcher(self) -> SessionUpdateDispatcher:
        """Создает SessionUpdateDispatcher с реальными handlers."""
        return SessionUpdateDispatcher(
            message_chunk_handler=MessageChunkHandler(),
            tool_call_handler=ToolCallHandler(),
            plan_update_handler=PlanUpdateHandler(),
            config_option_handler=ConfigOptionHandler(),
        )

    @pytest.fixture
    def session_state(self) -> ChatSessionState:
        """Создает ChatSessionState."""
        return ChatSessionState()

    @pytest.fixture
    def sink(self) -> MockSink:
        """Создает MockSink."""
        return MockSink()

    @pytest.fixture
    def context(
        self, session_state: ChatSessionState, sink: MockSink
    ) -> ChatUpdateContext:
        """Создает ChatUpdateContext с sink."""
        event_bus = EventBus()
        plan_vm = MagicMock()
        return ChatUpdateContext(
            session_id="test-session",
            state=session_state,
            sink=sink,
            plan_vm=plan_vm,
            event_bus=event_bus,
        )

    def test_full_conversation_flow(
        self,
        dispatcher: SessionUpdateDispatcher,
        context: ChatUpdateContext,
        sink: MockSink,
    ) -> None:
        """Тест полного потока диалога: user message → agent response → tool call."""
        # 1. User message
        user_update = {
            "params": {
                "sessionId": "test-session",
                "update": {
                    "sessionUpdate": "user_message_chunk",
                    "content": {"text": "Read file.txt"},
                },
            }
        }
        dispatcher.dispatch_with_context(user_update, context)

        assert len(context.state.messages) == 1
        assert context.state.messages[0]["role"] == "user"
        assert len(sink.synced_messages) == 1

        # 2. Agent response (streaming)
        agent_updates = [
            {
                "params": {
                    "sessionId": "test-session",
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"text": "I'll "},
                    },
                }
            },
            {
                "params": {
                    "sessionId": "test-session",
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"text": "read the file."},
                    },
                }
            },
        ]
        for update in agent_updates:
            dispatcher.dispatch_with_context(update, context)

        assert context.state.streaming_text == "I'll read the file."
        assert len(sink.synced_streaming) == 2

        # 3. Tool call
        tool_update = {
            "params": {
                "sessionId": "test-session",
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": "tc-1",
                    "title": "Read file",
                    "status": "pending",
                },
            }
        }
        dispatcher.dispatch_with_context(tool_update, context)

        assert len(context.state.tool_calls) == 1
        assert context.state.tool_calls[0]["toolCallId"] == "tc-1"
        assert len(sink.synced_tool_calls) == 1

        # 4. Tool call update
        tool_update_status = {
            "params": {
                "sessionId": "test-session",
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "tc-1",
                    "status": "completed",
                },
            }
        }
        dispatcher.dispatch_with_context(tool_update_status, context)

        assert context.state.tool_calls[0]["status"] == "completed"

    def test_multiple_sessions_isolation(
        self,
        dispatcher: SessionUpdateDispatcher,
    ) -> None:
        """Тест изоляции состояния между сессиями."""
        # Создаем два контекста для разных сессий
        state1 = ChatSessionState()
        state2 = ChatSessionState()
        sink1 = MockSink()
        sink2 = MockSink()

        context1 = ChatUpdateContext(
            session_id="session-1",
            state=state1,
            sink=sink1,
        )
        context2 = ChatUpdateContext(
            session_id="session-2",
            state=state2,
            sink=sink2,
        )

        # Отправляем сообщения в первую сессию
        update1 = {
            "params": {
                "sessionId": "session-1",
                "update": {
                    "sessionUpdate": "user_message_chunk",
                    "content": {"text": "Message for session 1"},
                },
            }
        }
        dispatcher.dispatch_with_context(update1, context1)

        # Отправляем сообщения во вторую сессию
        update2 = {
            "params": {
                "sessionId": "session-2",
                "update": {
                    "sessionUpdate": "user_message_chunk",
                    "content": {"text": "Message for session 2"},
                },
            }
        }
        dispatcher.dispatch_with_context(update2, context2)

        # Проверяем изоляцию
        assert len(state1.messages) == 1
        assert state1.messages[0]["content"] == "Message for session 1"
        assert len(state2.messages) == 1
        assert state2.messages[0]["content"] == "Message for session 2"

        # Проверяем что sink'и получили правильные данные
        assert len(sink1.synced_messages) == 1
        assert sink1.synced_messages[0][0] == "session-1"
        assert len(sink2.synced_messages) == 1
        assert sink2.synced_messages[0][0] == "session-2"


class TestPersistenceIntegration:
    """Интеграционные тесты для FileChatPersistence."""

    @pytest.fixture
    def persistence(self, tmp_path: Path) -> FileChatPersistence:
        """Создает FileChatPersistence."""
        return FileChatPersistence(tmp_path / "history")

    async def test_save_and_load_messages(
        self, persistence: FileChatPersistence
    ) -> None:
        """Тест сохранения и загрузки сообщений."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        replay_updates = [
            {
                "params": {
                    "sessionId": "test-session",
                    "update": {
                        "sessionUpdate": "user_message_chunk",
                        "content": {"text": "Hello"},
                    },
                }
            }
        ]

        # Сохраняем
        await persistence.save_messages(
            "test-session", messages, replay_updates=replay_updates
        )

        # Загружаем
        loaded_messages = await persistence.load_messages("test-session")
        loaded_updates = await persistence.load_replay_updates("test-session")

        assert loaded_messages == messages
        assert loaded_updates == replay_updates

    async def test_sync_methods(
        self, persistence: FileChatPersistence
    ) -> None:
        """Тест sync методов для использования в sync контексте."""
        messages = [
            {"role": "user", "content": "Test message"},
        ]
        replay_updates = [
            {
                "params": {
                    "sessionId": "test-session",
                    "update": {
                        "sessionUpdate": "user_message_chunk",
                        "content": {"text": "Test message"},
                    },
                }
            }
        ]

        # Сохраняем через async
        await persistence.save_messages(
            "test-session", messages, replay_updates=replay_updates
        )

        # Загружаем через sync
        loaded_messages = persistence.load_messages_sync("test-session")
        loaded_updates = persistence.load_replay_updates_sync("test-session")

        assert loaded_messages == messages
        assert loaded_updates == replay_updates

    async def test_multiple_sessions_persistence(
        self, persistence: FileChatPersistence
    ) -> None:
        """Тест persistence для нескольких сессий."""
        # Сохраняем данные для двух сессий
        await persistence.save_messages(
            "session-1",
            [{"role": "user", "content": "Session 1"}],
        )
        await persistence.save_messages(
            "session-2",
            [{"role": "user", "content": "Session 2"}],
        )

        # Загружаем и проверяем изоляцию
        messages1 = await persistence.load_messages("session-1")
        messages2 = await persistence.load_messages("session-2")

        assert len(messages1) == 1
        assert messages1[0]["content"] == "Session 1"
        assert len(messages2) == 1
        assert messages2[0]["content"] == "Session 2"


class TestFsCallbackExecutorIntegration:
    """Интеграционные тесты для FsCallbackExecutor."""

    @pytest.fixture
    def executor(self, tmp_path: Path) -> FsCallbackExecutor:
        """Создает FsCallbackExecutor."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        return FsCallbackExecutor(workspace)

    async def test_write_and_read_file(
        self, executor: FsCallbackExecutor
    ) -> None:
        """Тест записи и чтения файла."""
        content = "Hello, World!"

        # Записываем
        success, error = await executor.write_file("test.txt", content)
        assert success is True
        assert error is None

        # Читаем
        read_content, read_error = await executor.read_file("test.txt")
        assert read_content == content
        assert read_error is None

    async def test_nested_directory_creation(
        self, executor: FsCallbackExecutor
    ) -> None:
        """Тест создания вложенных директорий при записи."""
        content = "Nested content"

        # Записываем в вложенную директорию
        success, error = await executor.write_file(
            "level1/level2/level3/test.txt", content
        )
        assert success is True
        assert error is None

        # Читаем
        read_content, read_error = await executor.read_file(
            "level1/level2/level3/test.txt"
        )
        assert read_content == content
        assert read_error is None

    async def test_path_traversal_protection(
        self, executor: FsCallbackExecutor
    ) -> None:
        """Тест защиты от path traversal."""
        # Пытаемся прочитать файл вне sandbox
        content, error = await executor.read_file("../../etc/passwd")
        assert content is None
        assert error is not None
        assert "traversal" in error.lower()

        # Пытаемся записать файл вне sandbox
        success, error = await executor.write_file(
            "../../etc/malicious.txt", "bad content"
        )
        assert success is False
        assert error is not None
        assert "traversal" in error.lower()


class TestTerminalCallbackExecutorIntegration:
    """Интеграционные тесты для TerminalCallbackExecutor."""

    @pytest.fixture
    def mock_executor(self) -> MockTerminalExecutor:
        """Создает MockTerminalExecutor."""
        return MockTerminalExecutor()

    @pytest.fixture
    def executor(self, mock_executor: MockTerminalExecutor) -> TerminalCallbackExecutor:
        """Создает TerminalCallbackExecutor."""
        return TerminalCallbackExecutor(mock_executor)

    async def test_terminal_lifecycle(
        self, executor: TerminalCallbackExecutor
    ) -> None:
        """Тест полного жизненного цикла терминала."""
        # Создаем терминал
        terminal_id, error = await executor.create_terminal("ls -la")
        assert terminal_id is not None
        assert error is None

        # Получаем вывод
        output, error = await executor.get_output(terminal_id)
        assert output is not None
        assert error is None
        assert "ls -la" in output["output"]

        # Ждем завершения
        exit_result, error = await executor.wait_for_exit(terminal_id)
        assert exit_result is not None
        assert error is None
        assert exit_result[0] == 0  # exit_code

        # Освобождаем ресурсы
        release_error = await executor.release_terminal(terminal_id)
        assert release_error is None

    async def test_multiple_terminals(
        self, executor: TerminalCallbackExecutor
    ) -> None:
        """Тест работы с несколькими терминалами одновременно."""
        # Создаем два терминала
        terminal1, _ = await executor.create_terminal("command1")
        terminal2, _ = await executor.create_terminal("command2")

        assert terminal1 != terminal2

        # Получаем вывод обоих
        output1, _ = await executor.get_output(terminal1)
        output2, _ = await executor.get_output(terminal2)

        assert "command1" in output1["output"]
        assert "command2" in output2["output"]

        # Освобождаем оба
        await executor.release_terminal(terminal1)
        await executor.release_terminal(terminal2)

    async def test_kill_terminal(
        self, executor: TerminalCallbackExecutor
    ) -> None:
        """Тест принудительного завершения терминала."""
        terminal_id, _ = await executor.create_terminal("long_running_command")

        # Убиваем терминал
        success, error = await executor.kill_terminal(terminal_id)
        assert success is True
        assert error is None

        # Пытаемся получить вывод убитого терминала
        output, error = await executor.get_output(terminal_id)
        assert output is None
        assert error is not None
        assert "not found" in error.lower()


class TestEndToEndWorkflow:
    """End-to-end тесты полного workflow."""

    async def test_complete_session_workflow(
        self, tmp_path: Path
    ) -> None:
        """Тест полного workflow сессии: создание → отправка → получение → сохранение."""
        # Инициализируем компоненты
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        history_dir = tmp_path / "history"
        history_dir.mkdir()

        dispatcher = SessionUpdateDispatcher(
            message_chunk_handler=MessageChunkHandler(),
            tool_call_handler=ToolCallHandler(),
            plan_update_handler=PlanUpdateHandler(),
            config_option_handler=ConfigOptionHandler(),
        )
        persistence = FileChatPersistence(history_dir)
        fs_executor = FsCallbackExecutor(workspace)
        terminal_executor = TerminalCallbackExecutor(MockTerminalExecutor())

        # Создаем состояние сессии
        session_state = ChatSessionState()
        sink = MockSink()
        event_bus = EventBus()
        context = ChatUpdateContext(
            session_id="test-session",
            state=session_state,
            sink=sink,
            event_bus=event_bus,
        )

        # 1. Пользователь отправляет сообщение
        user_update = {
            "params": {
                "sessionId": "test-session",
                "update": {
                    "sessionUpdate": "user_message_chunk",
                    "content": {"text": "List files"},
                },
            }
        }
        dispatcher.dispatch_with_context(user_update, context)

        # 2. Агент отвечает с tool call
        agent_updates = [
            {
                "params": {
                    "sessionId": "test-session",
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"text": "I'll list the files."},
                    },
                }
            },
            {
                "params": {
                    "sessionId": "test-session",
                    "update": {
                        "sessionUpdate": "tool_call",
                        "toolCallId": "tc-1",
                        "title": "List files",
                        "status": "pending",
                    },
                }
            },
        ]

        for update in agent_updates:
            dispatcher.dispatch_with_context(update, context)

        # 3. Выполняем terminal команду
        terminal_id, _ = await terminal_executor.create_terminal("ls -la")
        output, _ = await terminal_executor.get_output(terminal_id)
        await terminal_executor.release_terminal(terminal_id)

        # 4. Выполняем fs операцию
        file_content = "File listing:\n" + output["output"]
        await fs_executor.write_file("output.txt", file_content)

        # 5. Сохраняем состояние в persistence
        await persistence.save_messages(
            "test-session",
            session_state.messages,
            replay_updates=[user_update] + agent_updates,
        )

        # 6. Проверяем что все данные сохранены
        loaded_messages = await persistence.load_messages("test-session")
        # В messages только user message (agent message в streaming_text)
        assert len(loaded_messages) == 1
        assert loaded_messages[0]["role"] == "user"
        assert loaded_messages[0]["content"] == "List files"

        # Проверяем что agent текст в streaming_text
        assert session_state.streaming_text == "I'll list the files."

        # Проверяем что tool call сохранен
        assert len(session_state.tool_calls) == 1
        assert session_state.tool_calls[0]["toolCallId"] == "tc-1"

        # 7. Проверяем что файл создан
        read_content, _ = await fs_executor.read_file("output.txt")
        assert "File listing:" in read_content

        # 8. Проверяем что sink получил все обновления
        assert len(sink.synced_messages) == 1
        assert len(sink.synced_streaming) == 1
        assert len(sink.synced_tool_calls) == 1

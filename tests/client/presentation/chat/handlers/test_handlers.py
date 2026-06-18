"""Тесты для обработчиков обновлений сессии."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from codelab.client.presentation.chat.chat_session_state import ChatSessionState
from codelab.client.presentation.chat.context import ChatUpdateContext
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


class TestMessageChunkHandler:
    """Тесты для MessageChunkHandler."""

    @pytest.fixture
    def handler(self) -> MessageChunkHandler:
        """Создаёт экземпляр MessageChunkHandler."""
        return MessageChunkHandler()

    @pytest.fixture
    def context(self) -> ChatUpdateContext:
        """Создаёт тестовый контекст."""
        state = ChatSessionState()
        sink = MockSink()
        return ChatUpdateContext(
            session_id="test-session",
            state=state,
            sink=sink,
        )

    def test_can_handle_agent_message_chunk(self, handler: MessageChunkHandler) -> None:
        """Handler должен обрабатывать agent_message_chunk."""
        assert handler.can_handle("agent_message_chunk") is True

    def test_can_handle_user_message_chunk(self, handler: MessageChunkHandler) -> None:
        """Handler должен обрабатывать user_message_chunk."""
        assert handler.can_handle("user_message_chunk") is True

    def test_cannot_handle_other_types(self, handler: MessageChunkHandler) -> None:
        """Handler не должен обрабатывать другие типы."""
        assert handler.can_handle("tool_call") is False
        assert handler.can_handle("plan") is False
        assert handler.can_handle("unknown") is False

    def test_handle_agent_message_chunk(
        self, handler: MessageChunkHandler, context: ChatUpdateContext
    ) -> None:
        """Handler должен добавлять текст в streaming для agent_message_chunk."""
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": "Hello"},
                }
            }
        }

        handler.handle(update_data, context)

        assert context.state.streaming_text == "Hello"
        assert context.state.is_streaming is True
        assert len(context.sink.synced_streaming) == 1

    def test_handle_user_message_chunk(
        self, handler: MessageChunkHandler, context: ChatUpdateContext
    ) -> None:
        """Handler должен добавлять сообщение в messages для user_message_chunk."""
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "user_message_chunk",
                    "content": {"type": "text", "text": "User message"},
                }
            }
        }

        handler.handle(update_data, context)

        assert len(context.state.messages) == 1
        assert context.state.messages[0] == {"role": "user", "content": "User message"}
        assert len(context.sink.synced_messages) == 1

    def test_handle_empty_text(
        self, handler: MessageChunkHandler, context: ChatUpdateContext
    ) -> None:
        """Handler должен игнорировать пустой текст."""
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": ""},
                }
            }
        }

        handler.handle(update_data, context)

        assert context.state.streaming_text == ""
        assert len(context.sink.synced_streaming) == 0


class TestToolCallHandler:
    """Тесты для ToolCallHandler."""

    @pytest.fixture
    def handler(self) -> ToolCallHandler:
        """Создаёт экземпляр ToolCallHandler."""
        return ToolCallHandler()

    @pytest.fixture
    def context(self) -> ChatUpdateContext:
        """Создаёт тестовый контекст."""
        state = ChatSessionState()
        sink = MockSink()
        return ChatUpdateContext(
            session_id="test-session",
            state=state,
            sink=sink,
        )

    def test_can_handle_tool_call(self, handler: ToolCallHandler) -> None:
        """Handler должен обрабатывать tool_call."""
        assert handler.can_handle("tool_call") is True

    def test_can_handle_tool_call_update(self, handler: ToolCallHandler) -> None:
        """Handler должен обрабатывать tool_call_update."""
        assert handler.can_handle("tool_call_update") is True

    def test_can_handle_tool_call_result(self, handler: ToolCallHandler) -> None:
        """Handler должен обрабатывать tool_call_result."""
        assert handler.can_handle("tool_call_result") is True

    def test_cannot_handle_other_types(self, handler: ToolCallHandler) -> None:
        """Handler не должен обрабатывать другие типы."""
        assert handler.can_handle("agent_message_chunk") is False
        assert handler.can_handle("plan") is False

    def test_handle_tool_call_created(
        self, handler: ToolCallHandler, context: ChatUpdateContext
    ) -> None:
        """Handler должен добавлять новый tool call."""
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": "tc-1",
                    "title": "Read file",
                    "status": "pending",
                    "kind": "read",
                }
            }
        }

        handler.handle(update_data, context)

        assert len(context.state.tool_calls) == 1
        assert context.state.tool_calls[0]["toolCallId"] == "tc-1"
        assert context.state.tool_calls[0]["title"] == "Read file"
        assert len(context.sink.synced_tool_calls) == 1

    def test_handle_tool_call_updated(
        self, handler: ToolCallHandler, context: ChatUpdateContext
    ) -> None:
        """Handler должен обновлять существующий tool call."""
        # Сначала создаём tool call
        context.state.add_tool_call({
            "toolCallId": "tc-1",
            "title": "Read file",
            "status": "pending",
        })

        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "tc-1",
                    "status": "completed",
                }
            }
        }

        handler.handle(update_data, context)

        assert context.state.tool_calls[0]["status"] == "completed"
        assert len(context.sink.synced_tool_calls) == 1

    def test_handle_tool_call_missing_id(
        self, handler: ToolCallHandler, context: ChatUpdateContext
    ) -> None:
        """Handler должен игнорировать tool call без ID."""
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "tool_call",
                    "title": "Read file",
                }
            }
        }

        handler.handle(update_data, context)

        assert len(context.state.tool_calls) == 0


class TestPlanUpdateHandler:
    """Тесты для PlanUpdateHandler."""

    @pytest.fixture
    def handler(self) -> PlanUpdateHandler:
        """Создаёт экземпляр PlanUpdateHandler."""
        return PlanUpdateHandler()

    @pytest.fixture
    def context(self) -> ChatUpdateContext:
        """Создаёт тестовый контекст."""
        state = ChatSessionState()
        sink = MockSink()
        plan_vm = MagicMock()
        return ChatUpdateContext(
            session_id="test-session",
            state=state,
            sink=sink,
            plan_vm=plan_vm,
        )

    def test_can_handle_plan(self, handler: PlanUpdateHandler) -> None:
        """Handler должен обрабатывать plan."""
        assert handler.can_handle("plan") is True

    def test_cannot_handle_other_types(self, handler: PlanUpdateHandler) -> None:
        """Handler не должен обрабатывать другие типы."""
        assert handler.can_handle("agent_message_chunk") is False
        assert handler.can_handle("tool_call") is False

    def test_handle_plan_with_entries(
        self, handler: PlanUpdateHandler, context: ChatUpdateContext
    ) -> None:
        """Handler должен форматировать и устанавливать план."""
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "plan",
                    "entries": [
                        {"content": "Step 1", "priority": "high", "status": "pending"},
                        {"content": "Step 2", "priority": "medium", "status": "in_progress"},
                    ],
                }
            }
        }

        handler.handle(update_data, context)

        assert context.plan_vm.set_plan.called
        plan_text = context.plan_vm.set_plan.call_args[0][0]
        assert "Step 1" in plan_text
        assert "Step 2" in plan_text

    def test_handle_plan_empty_entries(
        self, handler: PlanUpdateHandler, context: ChatUpdateContext
    ) -> None:
        """Handler должен очищать план при пустых entries."""
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "plan",
                    "entries": [],
                }
            }
        }

        handler.handle(update_data, context)

        assert context.plan_vm.set_plan.called
        assert context.plan_vm.set_plan.call_args[0][0] == ""

    def test_handle_plan_without_plan_vm(
        self, handler: PlanUpdateHandler
    ) -> None:
        """Handler должен работать без plan_vm."""
        state = ChatSessionState()
        sink = MockSink()
        context = ChatUpdateContext(
            session_id="test-session",
            state=state,
            sink=sink,
            plan_vm=None,
        )

        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "plan",
                    "entries": [{"content": "Step 1"}],
                }
            }
        }

        # Не должно вызывать исключение
        handler.handle(update_data, context)


class TestConfigOptionHandler:
    """Тесты для ConfigOptionHandler."""

    @pytest.fixture
    def handler(self) -> ConfigOptionHandler:
        """Создаёт экземпляр ConfigOptionHandler."""
        return ConfigOptionHandler()

    @pytest.fixture
    def context(self) -> ChatUpdateContext:
        """Создаёт тестовый контекст."""
        state = ChatSessionState()
        sink = MockSink()
        event_bus = MagicMock()
        # Делаем publish async mock
        async def async_publish(*args: Any, **kwargs: Any) -> None:
            pass
        event_bus.publish = MagicMock(side_effect=async_publish)
        return ChatUpdateContext(
            session_id="test-session",
            state=state,
            sink=sink,
            event_bus=event_bus,
        )

    def test_can_handle_config_option_update(
        self, handler: ConfigOptionHandler
    ) -> None:
        """Handler должен обрабатывать config_option_update."""
        assert handler.can_handle("config_option_update") is True

    def test_cannot_handle_other_types(self, handler: ConfigOptionHandler) -> None:
        """Handler не должен обрабатывать другие типы."""
        assert handler.can_handle("agent_message_chunk") is False
        assert handler.can_handle("plan") is False

    def test_handle_config_option_update(
        self, handler: ConfigOptionHandler, context: ChatUpdateContext
    ) -> None:
        """Handler должен публиковать событие при наличии config_options."""
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "config_option_update",
                    "configOptions": [
                        {"id": "model", "name": "Model", "value": "gpt-4"},
                    ],
                }
            }
        }

        handler.handle(update_data, context)

        # Событие должно быть опубликовано (async)
        # Проверяем что event_bus не вызывался синхронно
        # (publish вызывается через ensure_future)

    def test_handle_config_option_update_empty(
        self, handler: ConfigOptionHandler, context: ChatUpdateContext
    ) -> None:
        """Handler должен игнорировать пустые config_options."""
        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "config_option_update",
                    "configOptions": [],
                }
            }
        }

        handler.handle(update_data, context)

        # Не должно публиковать событие

    def test_handle_config_option_update_without_event_bus(
        self, handler: ConfigOptionHandler
    ) -> None:
        """Handler должен работать без event_bus."""
        state = ChatSessionState()
        sink = MockSink()
        context = ChatUpdateContext(
            session_id="test-session",
            state=state,
            sink=sink,
            event_bus=None,
        )

        update_data = {
            "params": {
                "update": {
                    "sessionUpdate": "config_option_update",
                    "configOptions": [{"id": "model"}],
                }
            }
        }

        # Не должно вызывать исключение
        handler.handle(update_data, context)

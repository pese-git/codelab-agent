"""Тесты для SessionUpdateDispatcher."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from codelab.client.presentation.chat.chat_session_state import ChatSessionState
from codelab.client.presentation.chat.context import ChatUpdateContext
from codelab.client.presentation.chat.dispatcher.session_update_dispatcher import (
    SessionUpdateDispatcher,
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


class TestSessionUpdateDispatcher:
    """Тесты для SessionUpdateDispatcher."""

    @pytest.fixture
    def message_handler(self) -> MessageChunkHandler:
        """Создаёт MessageChunkHandler."""
        return MessageChunkHandler()

    @pytest.fixture
    def tool_handler(self) -> ToolCallHandler:
        """Создаёт ToolCallHandler."""
        return ToolCallHandler()

    @pytest.fixture
    def plan_handler(self) -> PlanUpdateHandler:
        """Создаёт PlanUpdateHandler."""
        return PlanUpdateHandler()

    @pytest.fixture
    def config_handler(self) -> ConfigOptionHandler:
        """Создаёт ConfigOptionHandler."""
        return ConfigOptionHandler()

    @pytest.fixture
    def dispatcher(
        self,
        message_handler: MessageChunkHandler,
        tool_handler: ToolCallHandler,
        plan_handler: PlanUpdateHandler,
        config_handler: ConfigOptionHandler,
    ) -> SessionUpdateDispatcher:
        """Создаёт SessionUpdateDispatcher."""
        return SessionUpdateDispatcher(
            message_chunk_handler=message_handler,
            tool_call_handler=tool_handler,
            plan_update_handler=plan_handler,
            config_option_handler=config_handler,
        )

    @pytest.fixture
    def session_state(self) -> ChatSessionState:
        """Создаёт ChatSessionState."""
        return ChatSessionState()

    @pytest.fixture
    def context(self, session_state: ChatSessionState) -> ChatUpdateContext:
        """Создаёт ChatUpdateContext."""
        sink = MockSink()
        plan_vm = MagicMock()
        event_bus = MagicMock()
        # Делаем publish async mock
        async def async_publish(*args: Any, **kwargs: Any) -> None:
            pass
        event_bus.publish = MagicMock(side_effect=async_publish)

        return ChatUpdateContext(
            session_id="test-session",
            state=session_state,
            sink=sink,
            plan_vm=plan_vm,
            event_bus=event_bus,
        )

    def test_dispatch_agent_message_chunk(
        self,
        dispatcher: SessionUpdateDispatcher,
        context: ChatUpdateContext,
    ) -> None:
        """Диспетчер должен маршрутизировать agent_message_chunk к MessageChunkHandler."""
        update_data = {
            "params": {
                "sessionId": "test-session",
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": "Hello"},
                },
            }
        }

        dispatcher.dispatch_with_context(update_data, context)

        assert context.state.streaming_text == "Hello"
        assert len(context.sink.synced_streaming) == 1

    def test_dispatch_user_message_chunk(
        self,
        dispatcher: SessionUpdateDispatcher,
        context: ChatUpdateContext,
    ) -> None:
        """Диспетчер должен маршрутизировать user_message_chunk к MessageChunkHandler."""
        update_data = {
            "params": {
                "sessionId": "test-session",
                "update": {
                    "sessionUpdate": "user_message_chunk",
                    "content": {"type": "text", "text": "User message"},
                },
            }
        }

        dispatcher.dispatch_with_context(update_data, context)

        assert len(context.state.messages) == 1
        assert context.state.messages[0]["content"] == "User message"

    def test_dispatch_tool_call(
        self,
        dispatcher: SessionUpdateDispatcher,
        context: ChatUpdateContext,
    ) -> None:
        """Диспетчер должен маршрутизировать tool_call к ToolCallHandler."""
        update_data = {
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

        dispatcher.dispatch_with_context(update_data, context)

        assert len(context.state.tool_calls) == 1
        assert context.state.tool_calls[0]["toolCallId"] == "tc-1"

    def test_dispatch_tool_call_update(
        self,
        dispatcher: SessionUpdateDispatcher,
        context: ChatUpdateContext,
    ) -> None:
        """Диспетчер должен маршрутизировать tool_call_update к ToolCallHandler."""
        # Сначала создаём tool call
        context.state.add_tool_call({
            "toolCallId": "tc-1",
            "title": "Read file",
            "status": "pending",
        })

        update_data = {
            "params": {
                "sessionId": "test-session",
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "tc-1",
                    "status": "completed",
                },
            }
        }

        dispatcher.dispatch_with_context(update_data, context)

        assert context.state.tool_calls[0]["status"] == "completed"

    def test_dispatch_plan(
        self,
        dispatcher: SessionUpdateDispatcher,
        context: ChatUpdateContext,
    ) -> None:
        """Диспетчер должен маршрутизировать plan к PlanUpdateHandler."""
        update_data = {
            "params": {
                "sessionId": "test-session",
                "update": {
                    "sessionUpdate": "plan",
                    "entries": [
                        {"content": "Step 1", "priority": "high", "status": "pending"},
                    ],
                },
            }
        }

        dispatcher.dispatch_with_context(update_data, context)

        assert context.plan_vm.set_plan.called

    def test_dispatch_config_option_update(
        self,
        dispatcher: SessionUpdateDispatcher,
        context: ChatUpdateContext,
    ) -> None:
        """Диспетчер должен маршрутизировать config_option_update к ConfigOptionHandler."""
        update_data = {
            "params": {
                "sessionId": "test-session",
                "update": {
                    "sessionUpdate": "config_option_update",
                    "configOptions": [
                        {"id": "model", "name": "Model", "value": "gpt-4"},
                    ],
                },
            }
        }

        dispatcher.dispatch_with_context(update_data, context)

        # Событие должно быть опубликовано (async)

    def test_dispatch_unknown_update_type(
        self,
        dispatcher: SessionUpdateDispatcher,
        context: ChatUpdateContext,
    ) -> None:
        """Диспетчер должен логировать warning для неизвестного типа обновления."""
        update_data = {
            "params": {
                "sessionId": "test-session",
                "update": {
                    "sessionUpdate": "unknown_type",
                },
            }
        }

        # Не должно вызывать исключение
        dispatcher.dispatch_with_context(update_data, context)

    def test_dispatch_missing_update_type(
        self,
        dispatcher: SessionUpdateDispatcher,
        context: ChatUpdateContext,
    ) -> None:
        """Диспетчер должен логировать warning если update_type отсутствует."""
        update_data = {
            "params": {
                "sessionId": "test-session",
                "update": {},
            }
        }

        # Не должно вызывать исключение
        dispatcher.dispatch_with_context(update_data, context)

    def test_dispatch_handler_exception(
        self,
        dispatcher: SessionUpdateDispatcher,
        context: ChatUpdateContext,
    ) -> None:
        """Диспетчер должен перехватывать исключения в обработчиках."""
        # Создаём обработку которая вызывает исключение
        update_data = {
            "params": {
                "sessionId": "test-session",
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": "Hello"},
                },
            }
        }

        # Патчим handler чтобы он вызывал исключение
        original_handle = dispatcher._handlers[0].handle
        def failing_handle(*args: Any, **kwargs: Any) -> None:
            raise ValueError("Test error")
        dispatcher._handlers[0].handle = failing_handle

        # Не должно вызывать исключение
        dispatcher.dispatch_with_context(update_data, context)

        # Восстанавливаем оригинальный handler
        dispatcher._handlers[0].handle = original_handle

    def test_dispatch_multiple_updates(
        self,
        dispatcher: SessionUpdateDispatcher,
        context: ChatUpdateContext,
    ) -> None:
        """Диспетчер должен обрабатывать несколько обновлений последовательно."""
        updates = [
            {
                "params": {
                    "sessionId": "test-session",
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": "Hello"},
                    },
                }
            },
            {
                "params": {
                    "sessionId": "test-session",
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": " World"},
                    },
                }
            },
        ]

        for update_data in updates:
            dispatcher.dispatch_with_context(update_data, context)

        assert context.state.streaming_text == "Hello World"

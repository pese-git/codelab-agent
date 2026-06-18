"""Тесты для Protocol интерфейсов."""

from __future__ import annotations

from typing import Any

import pytest

from codelab.client.presentation.chat.chat_session_state import ChatSessionState
from codelab.client.presentation.chat.context import ChatUpdateContext
from codelab.client.presentation.chat.contracts import (
    ChatPersistencePort,
    ChatUpdateSink,
    SessionUpdateHandler,
)


class MockSink:
    """Mock реализация ChatUpdateSink для тестов."""

    def __init__(self) -> None:
        self.synced_messages: list[tuple[str, list[dict[str, str]]]] = []
        self.synced_tool_calls: list[tuple[str, list[dict[str, Any]]]] = []
        self.synced_streaming: list[tuple[str, str, bool]] = []

    def sync_messages(self, session_id: str, messages: list[dict[str, str]]) -> None:
        self.synced_messages.append((session_id, messages))

    def sync_tool_calls(
        self, session_id: str, tool_calls: list[dict[str, Any]]
    ) -> None:
        self.synced_tool_calls.append((session_id, tool_calls))

    def sync_streaming(
        self, session_id: str, text: str, is_streaming: bool
    ) -> None:
        self.synced_streaming.append((session_id, text, is_streaming))


class MockHandler:
    """Mock реализация SessionUpdateHandler для тестов."""

    def __init__(self, handled_types: set[str]) -> None:
        self.handled_types = handled_types
        self.handled_updates: list[dict[str, Any]] = []

    def can_handle(self, update_type: str) -> bool:
        return update_type in self.handled_types

    def handle(self, update_data: dict[str, Any], context: ChatUpdateContext) -> None:
        self.handled_updates.append(update_data)


class MockPersistence:
    """Mock реализация ChatPersistencePort для тестов."""

    def __init__(self) -> None:
        self.saved_messages: dict[str, list[dict[str, str]]] = {}
        self.saved_replay_updates: dict[str, list[dict[str, Any]]] = {}

    async def save_messages(
        self,
        session_id: str,
        messages: list[dict[str, str]],
        replay_updates: list[dict[str, Any]] | None = None,
    ) -> None:
        self.saved_messages[session_id] = messages
        if replay_updates is not None:
            self.saved_replay_updates[session_id] = replay_updates

    async def load_messages(self, session_id: str) -> list[dict[str, str]]:
        return self.saved_messages.get(session_id, [])

    async def load_replay_updates(self, session_id: str) -> list[dict[str, Any]]:
        return self.saved_replay_updates.get(session_id, [])


class TestSessionUpdateHandlerProtocol:
    """Тесты для Protocol SessionUpdateHandler."""

    def test_mock_handler_implements_protocol(self) -> None:
        """MockHandler должен реализовывать SessionUpdateHandler."""
        handler = MockHandler({"agent_message_chunk"})
        assert isinstance(handler, SessionUpdateHandler)

    def test_handler_can_handle_returns_true_for_matching_type(self) -> None:
        """can_handle должен возвращать True для поддерживаемых типов."""
        handler = MockHandler({"agent_message_chunk", "user_message_chunk"})
        assert handler.can_handle("agent_message_chunk") is True
        assert handler.can_handle("user_message_chunk") is True

    def test_handler_can_handle_returns_false_for_unknown_type(self) -> None:
        """can_handle должен возвращать False для неподдерживаемых типов."""
        handler = MockHandler({"agent_message_chunk"})
        assert handler.can_handle("tool_call") is False
        assert handler.can_handle("unknown_type") is False

    def test_handler_handle_receives_update_data(self) -> None:
        """handle должен получать update_data и context."""
        handler = MockHandler({"agent_message_chunk"})
        state = ChatSessionState()
        sink = MockSink()
        context = ChatUpdateContext(
            session_id="test-session",
            state=state,
            sink=sink,
        )

        update_data = {
            "params": {
                "sessionId": "test-session",
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": "Hello"},
                },
            }
        }

        handler.handle(update_data, context)

        assert len(handler.handled_updates) == 1
        assert handler.handled_updates[0] == update_data


class TestChatPersistencePortProtocol:
    """Тесты для Protocol ChatPersistencePort."""

    def test_mock_persistence_implements_protocol(self) -> None:
        """MockPersistence должен реализовывать ChatPersistencePort."""
        persistence = MockPersistence()
        assert isinstance(persistence, ChatPersistencePort)

    @pytest.mark.asyncio
    async def test_persistence_save_and_load_messages(self) -> None:
        """Persistence должен сохранять и загружать сообщения."""
        persistence = MockPersistence()
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        await persistence.save_messages("session-1", messages)
        loaded = await persistence.load_messages("session-1")

        assert loaded == messages

    @pytest.mark.asyncio
    async def test_persistence_load_nonexistent_returns_empty(self) -> None:
        """Загрузка несуществующей сессии должна возвращать пустой список."""
        persistence = MockPersistence()
        loaded = await persistence.load_messages("nonexistent")
        assert loaded == []

    @pytest.mark.asyncio
    async def test_persistence_save_and_load_replay_updates(self) -> None:
        """Persistence должен сохранять и загружать replay updates."""
        persistence = MockPersistence()
        updates = [
            {"params": {"update": {"sessionUpdate": "agent_message_chunk"}}},
        ]

        await persistence.save_messages("session-1", [], replay_updates=updates)
        loaded = await persistence.load_replay_updates("session-1")

        assert loaded == updates


class TestChatUpdateSinkProtocol:
    """Тесты для Protocol ChatUpdateSink."""

    def test_mock_sink_implements_protocol(self) -> None:
        """MockSink должен реализовывать ChatUpdateSink."""
        sink = MockSink()
        assert isinstance(sink, ChatUpdateSink)

    def test_sink_sync_messages(self) -> None:
        """Sink должен синхронизировать сообщения."""
        sink = MockSink()
        messages = [{"role": "user", "content": "Hello"}]

        sink.sync_messages("session-1", messages)

        assert len(sink.synced_messages) == 1
        assert sink.synced_messages[0] == ("session-1", messages)

    def test_sink_sync_tool_calls(self) -> None:
        """Sink должен синхронизировать tool calls."""
        sink = MockSink()
        tool_calls = [{"toolCallId": "tc-1", "title": "Read file"}]

        sink.sync_tool_calls("session-1", tool_calls)

        assert len(sink.synced_tool_calls) == 1
        assert sink.synced_tool_calls[0] == ("session-1", tool_calls)

    def test_sink_sync_streaming(self) -> None:
        """Sink должен синхронизировать streaming текст."""
        sink = MockSink()

        sink.sync_streaming("session-1", "Hello", True)

        assert len(sink.synced_streaming) == 1
        assert sink.synced_streaming[0] == ("session-1", "Hello", True)

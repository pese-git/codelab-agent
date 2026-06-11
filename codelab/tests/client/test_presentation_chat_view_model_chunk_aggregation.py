"""Тесты для агрегации message chunks при восстановлении сессии."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from codelab.client.presentation.chat_view_model import ChatViewModel


class TestChunkAggregation:
    """Тесты агрегации последовательных chunks одного типа."""

    def test_aggregates_sequential_user_chunks(self) -> None:
        """Последовательные user_message_chunk агрегируются в одно сообщение."""
        # Arrange
        coordinator = MagicMock()
        vm = ChatViewModel(coordinator=coordinator)
        
        replay_updates = [
            {
                "params": {
                    "sessionId": "test_session",
                    "update": {
                        "sessionUpdate": "user_message_chunk",
                        "content": {"type": "text", "text": "Hello"},
                    },
                },
            },
            {
                "params": {
                    "sessionId": "test_session",
                    "update": {
                        "sessionUpdate": "user_message_chunk",
                        "content": {"type": "text", "text": " World"},
                    },
                },
            },
        ]
        
        # Act
        vm.restore_session_from_replay("test_session", replay_updates)
        
        # Assert
        messages = vm.messages.value
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello World"

    def test_aggregates_sequential_agent_chunks(self) -> None:
        """Последовательные agent_message_chunk агрегируются в одно сообщение."""
        # Arrange
        coordinator = MagicMock()
        vm = ChatViewModel(coordinator=coordinator)
        
        replay_updates = [
            {
                "params": {
                    "sessionId": "test_session",
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": "Hello"},
                    },
                },
            },
            {
                "params": {
                    "sessionId": "test_session",
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": " World"},
                    },
                },
            },
        ]
        
        # Act
        vm.restore_session_from_replay("test_session", replay_updates)
        
        # Assert
        messages = vm.messages.value
        assert len(messages) == 1
        assert messages[0]["role"] == "assistant"
        assert messages[0]["content"] == "Hello World"

    def test_separates_different_roles(self) -> None:
        """Сообщения разных ролей не агрегируются вместе."""
        # Arrange
        coordinator = MagicMock()
        vm = ChatViewModel(coordinator=coordinator)
        
        replay_updates = [
            {
                "params": {
                    "sessionId": "test_session",
                    "update": {
                        "sessionUpdate": "user_message_chunk",
                        "content": {"type": "text", "text": "Hello"},
                    },
                },
            },
            {
                "params": {
                    "sessionId": "test_session",
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": "Hi there"},
                    },
                },
            },
        ]
        
        # Act
        vm.restore_session_from_replay("test_session", replay_updates)
        
        # Assert
        messages = vm.messages.value
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Hi there"

    def test_aggregates_streaming_response(self) -> None:
        """Streaming response (множество маленьких chunks) агрегируется в одно сообщение."""
        # Arrange
        coordinator = MagicMock()
        vm = ChatViewModel(coordinator=coordinator)
        
        # Имитация streaming: много маленьких chunks
        chunks = ["I", "'ll", " help", " you", " with", " that."]
        replay_updates = [
            {
                "params": {
                    "sessionId": "test_session",
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": chunk},
                    },
                },
            }
            for chunk in chunks
        ]
        
        # Act
        vm.restore_session_from_replay("test_session", replay_updates)
        
        # Assert
        messages = vm.messages.value
        assert len(messages) == 1
        assert messages[0]["role"] == "assistant"
        assert messages[0]["content"] == "I'll help you with that."

    def test_complex_conversation_flow(self) -> None:
        """Сложный диалог с чередованием ролей агрегируется корректно."""
        # Arrange
        coordinator = MagicMock()
        vm = ChatViewModel(coordinator=coordinator)
        
        replay_updates = [
            # User message (2 chunks)
            {"params": {"sessionId": "s", "update": {"sessionUpdate": "user_message_chunk", "content": {"type": "text", "text": "Hello"}}}},
            {"params": {"sessionId": "s", "update": {"sessionUpdate": "user_message_chunk", "content": {"type": "text", "text": " World"}}}},
            # Agent response (3 chunks)
            {"params": {"sessionId": "s", "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "Hi"}}}},
            {"params": {"sessionId": "s", "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": " there"}}}},
            {"params": {"sessionId": "s", "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "!"}}}},
            # User message (1 chunk)
            {"params": {"sessionId": "s", "update": {"sessionUpdate": "user_message_chunk", "content": {"type": "text", "text": "How are you?"}}}},
            # Agent response (2 chunks)
            {"params": {"sessionId": "s", "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "I'm"}}}},
            {"params": {"sessionId": "s", "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": " good!"}}}},
        ]
        
        # Act
        vm.restore_session_from_replay("s", replay_updates)
        
        # Assert
        messages = vm.messages.value
        assert len(messages) == 4
        
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello World"
        
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Hi there!"
        
        assert messages[2]["role"] == "user"
        assert messages[2]["content"] == "How are you?"
        
        assert messages[3]["role"] == "assistant"
        assert messages[3]["content"] == "I'm good!"

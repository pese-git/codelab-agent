"""Тесты для MessageSanitizer."""

import pytest

from codelab.server.agent.message_sanitizer import MessageSanitizer
from codelab.server.llm.models import LLMMessage, LLMToolCall


class TestMessageSanitizer:
    """3.4, 3.5 — обнаружение и исправление orphaned tool calls."""

    @pytest.fixture
    def sanitizer(self):
        return MessageSanitizer()

    def test_orphaned_tool_call_fixed(self, sanitizer):
        """Orphaned tool call получает synthetic error response."""
        messages = [
            LLMMessage(
                role="assistant",
                content="",
                tool_calls=[LLMToolCall(id="tc1", name="read_file")],
            ),
        ]
        result = sanitizer.sanitize(messages)
        assert len(result) == 2
        assert result[0].role == "assistant"
        assert result[1].role == "tool"
        assert result[1].tool_call_id == "tc1"
        assert "Error" in result[1].content

    def test_satisfied_tool_calls_unchanged(self, sanitizer):
        """Корректная история без изменений."""
        messages = [
            LLMMessage(
                role="assistant",
                content="",
                tool_calls=[LLMToolCall(id="tc1", name="read_file")],
            ),
            LLMMessage(
                role="tool",
                content="file content",
                tool_call_id="tc1",
            ),
        ]
        result = sanitizer.sanitize(messages)
        assert len(result) == 2
        assert result[0].role == "assistant"
        assert result[1].role == "tool"

    def test_multiple_tool_calls_partial_satisfied(self, sanitizer):
        """Несколько tool_calls, один удовлетворён, один orphaned."""
        messages = [
            LLMMessage(
                role="assistant",
                content="",
                tool_calls=[
                    LLMToolCall(id="tc1", name="read_file"),
                    LLMToolCall(id="tc2", name="write_file"),
                ],
            ),
            LLMMessage(
                role="tool",
                content="read ok",
                tool_call_id="tc1",
            ),
        ]
        result = sanitizer.sanitize(messages)
        assert len(result) == 3
        assert result[2].role == "tool"
        assert result[2].tool_call_id == "tc2"

    def test_non_tool_messages_unchanged(self, sanitizer):
        """Сообщения без tool_calls не изменяются."""
        messages = [
            LLMMessage(role="user", content="Hello"),
            LLMMessage(role="assistant", content="Hi there"),
        ]
        result = sanitizer.sanitize(messages)
        assert len(result) == 2
        assert result == messages

    def test_empty_messages(self, sanitizer):
        """Пустой список сообщений."""
        result = sanitizer.sanitize([])
        assert result == []

    def test_multiple_assistant_messages(self, sanitizer):
        """Несколько assistant сообщений с tool_calls."""
        messages = [
            LLMMessage(
                role="assistant",
                content="",
                tool_calls=[LLMToolCall(id="tc1", name="read")],
            ),
            LLMMessage(role="tool", content="ok", tool_call_id="tc1"),
            LLMMessage(
                role="assistant",
                content="",
                tool_calls=[LLMToolCall(id="tc2", name="write")],
            ),
        ]
        result = sanitizer.sanitize(messages)
        assert len(result) == 4  # 3 original + 1 synthetic error
        assert result[-1].tool_call_id == "tc2"

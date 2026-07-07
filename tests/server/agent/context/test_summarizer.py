"""Тесты для LLMConversationSummarizer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.agent.context.summarizer import LLMConversationSummarizer
from codelab.server.agent.context.token_counter import ApproximateTokenCounter
from codelab.server.llm.models import CompletionResponse, LLMMessage


@pytest.fixture
def token_counter():
    return ApproximateTokenCounter()


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.create_completion = AsyncMock()
    return llm


@pytest.fixture
def sample_messages():
    return [
        LLMMessage(role="user", content="Fix the login bug in auth.py"),
        LLMMessage(
            role="assistant",
            content="I'll look at the authentication module",
        ),
        LLMMessage(role="tool", content="File contents of auth.py...", tool_call_id="tc1"),
        LLMMessage(
            role="assistant",
            content="Found the bug: missing null check on line 42",
        ),
        LLMMessage(role="user", content="Please fix it"),
    ]


class TestLLMConversationSummarizer:
    async def test_summarize_with_llm_success(self, mock_llm, token_counter, sample_messages):
        mock_llm.create_completion.return_value = CompletionResponse(
            text=(
                "User asked to fix login bug. "
                "Found missing null check on line 42 in auth.py. Fix applied."
            ),
        )

        summarizer = LLMConversationSummarizer(
            llm=mock_llm,
            model="openai/gpt-4o-mini",
            token_counter=token_counter,
        )

        result = await summarizer.summarize(sample_messages, target_tokens=100)

        assert result.role == "assistant"
        assert "Summary of 5 messages" in result.content
        assert "login bug" in result.content
        mock_llm.create_completion.assert_called_once()

    async def test_summarize_no_llm_fallback(self, token_counter, sample_messages):
        summarizer = LLMConversationSummarizer(
            llm=None,
            token_counter=token_counter,
        )

        result = await summarizer.summarize(sample_messages, target_tokens=50)

        assert result.role == "assistant"
        assert "Truncated summary" in result.content

    async def test_summarize_llm_exception_fallback(self, mock_llm, token_counter, sample_messages):
        mock_llm.create_completion.side_effect = Exception("LLM unavailable")

        summarizer = LLMConversationSummarizer(
            llm=mock_llm,
            model="openai/gpt-4o-mini",
            token_counter=token_counter,
        )

        result = await summarizer.summarize(sample_messages, target_tokens=50)

        assert result.role == "assistant"
        assert "Truncated summary" in result.content

    async def test_summarize_empty_result_fallback(self, mock_llm, token_counter, sample_messages):
        mock_llm.create_completion.return_value = CompletionResponse(text="")

        summarizer = LLMConversationSummarizer(
            llm=mock_llm,
            model="openai/gpt-4o-mini",
            token_counter=token_counter,
        )

        result = await summarizer.summarize(sample_messages, target_tokens=50)

        assert result.role == "assistant"
        assert "Truncated summary" in result.content

    async def test_summarize_empty_messages(self, mock_llm, token_counter):
        summarizer = LLMConversationSummarizer(
            llm=mock_llm,
            token_counter=token_counter,
        )

        result = await summarizer.summarize([], target_tokens=50)

        assert result.role == "assistant"
        assert "Empty conversation" in result.content
        mock_llm.create_completion.assert_not_called()

    async def test_summarize_preserves_tool_calls_in_format(self, mock_llm, token_counter):
        messages = [
            LLMMessage(role="user", content="Read the file"),
            LLMMessage(
                role="assistant",
                content=None,
                tool_calls=[MagicMock(id="tc1", name="fs_read", arguments={"path": "test.py"})],
            ),
            LLMMessage(role="tool", content="file content here", tool_call_id="tc1"),
        ]

        mock_llm.create_completion.return_value = CompletionResponse(
            text="User asked to read test.py. File was read successfully.",
        )

        summarizer = LLMConversationSummarizer(
            llm=mock_llm,
            token_counter=token_counter,
        )

        result = await summarizer.summarize(messages, target_tokens=50)

        assert result.role == "assistant"
        assert "Summary of 3 messages" in result.content

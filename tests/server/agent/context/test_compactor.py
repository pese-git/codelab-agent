"""Тесты для ThreePhaseCompactor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.agent.context.compactor import ThreePhaseCompactor
from codelab.server.agent.context.models import ContextConfig
from codelab.server.agent.context.skeletonizer.composite import CompositeSkeletonizer
from codelab.server.agent.context.summarizer import LLMConversationSummarizer
from codelab.server.agent.context.token_counter import ApproximateTokenCounter
from codelab.server.llm.models import CompletionResponse, LLMMessage, LLMToolCall


@pytest.fixture
def token_counter():
    return ApproximateTokenCounter()


@pytest.fixture
def skeletonizer():
    return CompositeSkeletonizer()


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.create_completion = AsyncMock()
    return llm


@pytest.fixture
def summarizer(mock_llm, token_counter):
    return LLMConversationSummarizer(
        llm=mock_llm,
        model="openai/gpt-4o-mini",
        token_counter=token_counter,
    )


@pytest.fixture
def config():
    return ContextConfig()


def _make_tool_messages(count: int) -> list[LLMMessage]:
    """Создать набор сообщений с tool calls и results."""
    messages: list[LLMMessage] = [
        LLMMessage(role="system", content="You are a helpful assistant."),
        LLMMessage(role="user", content="Do many things"),
    ]
    for i in range(count):
        tc_id = f"tc_{i}"
        messages.append(LLMMessage(
            role="assistant",
            content=None,
            tool_calls=[LLMToolCall(id=tc_id, name="fs_read", arguments={"path": f"file_{i}.py"})],
        ))
        messages.append(LLMMessage(
            role="tool",
            content=f"Content of file {i} " * 50,
            tool_call_id=tc_id,
        ))
    messages.append(LLMMessage(role="assistant", content="Done!"))
    messages.append(LLMMessage(role="user", content="Continue"))
    messages.append(LLMMessage(role="assistant", content="Working..."))
    return messages


def _make_long_messages(total_tokens: int) -> list[LLMMessage]:
    """Создать сообщения с заданным приблизительным количеством токенов."""
    content = "x" * (total_tokens * 4)
    return [
        LLMMessage(role="system", content="System prompt"),
        LLMMessage(role="user", content=content),
        LLMMessage(role="assistant", content="Response"),
        LLMMessage(role="user", content="More"),
        LLMMessage(role="assistant", content="More response"),
    ]


class TestThreePhaseCompactor:
    async def test_guard_short_history(self, token_counter, config):
        compactor = ThreePhaseCompactor(
            token_counter=token_counter,
            config=config,
        )
        messages = [
            LLMMessage(role="user", content="Hi"),
            LLMMessage(role="assistant", content="Hello"),
        ]

        result = await compactor.compact_if_needed(
            messages, max_context_tokens=1000, reserved_tokens=100,
        )

        assert result == messages

    async def test_guard_within_limit(self, token_counter, config):
        compactor = ThreePhaseCompactor(
            token_counter=token_counter,
            config=config,
        )
        messages = _make_long_messages(100)

        result = await compactor.compact_if_needed(
            messages, max_context_tokens=100000, reserved_tokens=100,
        )

        assert result == messages

    async def test_prune_only_sufficient(self, token_counter, config):
        compactor = ThreePhaseCompactor(
            token_counter=token_counter,
            config=config,
        )
        messages = _make_tool_messages(20)

        total_tokens = token_counter.count_messages(messages)
        trigger = total_tokens // 2

        result = await compactor.compact_if_needed(
            messages, max_context_tokens=trigger + 100, reserved_tokens=100,
        )

        result_tokens = token_counter.count_messages(result)
        assert result_tokens < total_tokens
        assert len(result) < len(messages)

    async def test_prune_preserves_tool_pairs(self, token_counter, config):
        compactor = ThreePhaseCompactor(
            token_counter=token_counter,
            config=config,
        )
        messages = _make_tool_messages(10)

        result = await compactor.compact_if_needed(
            messages, max_context_tokens=50, reserved_tokens=10,
        )

        tool_call_ids: set[str] = set()
        tool_result_ids: set[str] = set()
        for msg in result:
            if msg.role == "assistant" and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_call_ids.add(tc.id)
            if msg.role == "tool" and msg.tool_call_id:
                tool_result_ids.add(msg.tool_call_id)

        orphaned_results = tool_result_ids - tool_call_ids
        assert len(orphaned_results) == 0

    async def test_skeletonize_reduces_tokens(self, token_counter, skeletonizer, config):
        compactor = ThreePhaseCompactor(
            token_counter=token_counter,
            skeletonizer=skeletonizer,
            config=config,
        )

        file_content = "def foo():\n    return 42\n" * 50
        messages = [
            LLMMessage(role="system", content="System"),
            LLMMessage(
                role="system",
                content=f'<context>\n<file path="test.py">\n{file_content}</file>\n</context>',
            ),
            LLMMessage(role="user", content="Analyze this code"),
            LLMMessage(role="assistant", content="Looking at it..."),
            LLMMessage(role="user", content="Go on"),
        ]

        total_tokens = token_counter.count_messages(messages)

        result = await compactor.compact_if_needed(
            messages, max_context_tokens=total_tokens // 2, reserved_tokens=10,
        )

        result_tokens = token_counter.count_messages(result)
        assert result_tokens < total_tokens

    async def test_summarize_when_needed(self, token_counter, skeletonizer, summarizer, config):
        mock_llm = MagicMock()
        mock_llm.create_completion = AsyncMock(return_value=CompletionResponse(
            text="Summary of conversation",
        ))
        summarizer._llm = mock_llm

        compactor = ThreePhaseCompactor(
            token_counter=token_counter,
            skeletonizer=skeletonizer,
            summarizer=summarizer,
            config=config,
        )

        messages = _make_long_messages(500)
        total_tokens = token_counter.count_messages(messages)

        result = await compactor.compact_if_needed(
            messages, max_context_tokens=100, reserved_tokens=10,
        )

        result_tokens = token_counter.count_messages(result)
        assert result_tokens < total_tokens

    async def test_degradation_without_llm(self, token_counter, skeletonizer, config):
        compactor = ThreePhaseCompactor(
            token_counter=token_counter,
            skeletonizer=skeletonizer,
            summarizer=None,
            config=config,
        )

        messages = _make_long_messages(500)
        total_tokens = token_counter.count_messages(messages)

        result = await compactor.compact_if_needed(
            messages, max_context_tokens=100, reserved_tokens=10,
        )

        result_tokens = token_counter.count_messages(result)
        assert result_tokens < total_tokens

    async def test_hard_truncate_as_last_resort(self, token_counter, config):
        compactor = ThreePhaseCompactor(
            token_counter=token_counter,
            config=config,
        )

        content = "x" * 10000
        messages = [
            LLMMessage(role="system", content="System"),
            LLMMessage(role="user", content=content),
            LLMMessage(role="assistant", content="Response"),
            LLMMessage(role="user", content="More"),
            LLMMessage(role="assistant", content="More response"),
        ]

        result = await compactor.compact_if_needed(
            messages, max_context_tokens=50, reserved_tokens=10,
        )

        result_tokens = token_counter.count_messages(result)
        assert result_tokens <= 50

    async def test_orphaned_tool_results_removed(self, token_counter, config):
        compactor = ThreePhaseCompactor(
            token_counter=token_counter,
            config=config,
        )

        messages = [
            LLMMessage(role="system", content="System"),
            LLMMessage(
                role="assistant",
                content=None,
                tool_calls=[LLMToolCall(id="tc1", name="read", arguments={})],
            ),
            LLMMessage(role="tool", content="result", tool_call_id="tc1"),
            LLMMessage(role="tool", content="orphaned", tool_call_id="tc_orphan"),
            LLMMessage(role="user", content="Continue"),
            LLMMessage(role="assistant", content="OK"),
            LLMMessage(role="user", content="More"),
        ]

        result = await compactor.compact_if_needed(
            messages, max_context_tokens=100000, reserved_tokens=100,
        )

        tool_result_ids = {
            msg.tool_call_id for msg in result
            if msg.role == "tool" and msg.tool_call_id
        }
        assert "tc_orphan" not in tool_result_ids

    async def test_priority_protection_in_hard_truncate(self, token_counter, config):
        compactor = ThreePhaseCompactor(
            token_counter=token_counter,
            config=config,
        )

        messages = [
            LLMMessage(role="system", content="Critical system rules " * 100),
            LLMMessage(role="user", content="x" * 10000),
            LLMMessage(role="assistant", content="Response"),
            LLMMessage(role="user", content="More"),
            LLMMessage(role="assistant", content="More response"),
        ]

        result = await compactor.compact_if_needed(
            messages, max_context_tokens=200, reserved_tokens=10,
        )

        assert result[0].role == "system"
        assert result[0].content is not None

    async def test_metrics_recorded(self, token_counter, config):
        metrics_tracker = MagicMock()
        metrics_tracker.record_context_compaction = MagicMock()

        compactor = ThreePhaseCompactor(
            token_counter=token_counter,
            config=config,
            metrics_tracker=metrics_tracker,
        )

        messages = _make_tool_messages(20)

        await compactor.compact_if_needed(
            messages, max_context_tokens=50, reserved_tokens=10,
        )

        metrics_tracker.record_context_compaction.assert_called_once()

    async def test_span_created(self, token_counter, config):
        mock_span = MagicMock()
        tracer = MagicMock()
        tracer.start_span.return_value = mock_span

        compactor = ThreePhaseCompactor(
            token_counter=token_counter,
            config=config,
            tracer=tracer,
        )

        messages = _make_tool_messages(20)

        await compactor.compact_if_needed(
            messages, max_context_tokens=50, reserved_tokens=10,
        )

        tracer.start_span.assert_called_once_with(name="context.compact")
        tracer.end_span.assert_called_once()

    async def test_priority_eviction_tool_messages_first(self, token_counter, config):
        """Tool messages (priority=4) должны удаляться первыми."""
        compactor = ThreePhaseCompactor(
            token_counter=token_counter,
            config=config,
        )

        messages = [
            LLMMessage(role="system", content="System"),
            LLMMessage(role="user", content="User question"),
            LLMMessage(role="assistant", content="Assistant response"),
            LLMMessage(role="tool", content="Tool result 1", tool_call_id="tc1"),
            LLMMessage(role="tool", content="Tool result 2", tool_call_id="tc2"),
            LLMMessage(role="user", content="Another question"),
            LLMMessage(role="assistant", content="Another response"),
        ]

        result = await compactor.compact_if_needed(
            messages, max_context_tokens=50, reserved_tokens=10,
        )

        # Tool messages должны быть удалены
        tool_count = sum(1 for msg in result if msg.role == "tool")
        assert tool_count < 2  # Меньше чем было изначально

    async def test_system_messages_protected(self, token_counter, config):
        """System messages (priority=10) не должны вытесняться при обычном переполнении."""
        compactor = ThreePhaseCompactor(
            token_counter=token_counter,
            config=config,
        )

        messages = [
            LLMMessage(role="system", content="Critical system rules " * 10),
            LLMMessage(role="user", content="x" * 1000),
            LLMMessage(role="assistant", content="Response"),
            LLMMessage(role="user", content="More"),
            LLMMessage(role="assistant", content="More response"),
        ]

        result = await compactor.compact_if_needed(
            messages, max_context_tokens=200, reserved_tokens=10,
        )

        # System message должен остаться
        assert any(msg.role == "system" for msg in result)

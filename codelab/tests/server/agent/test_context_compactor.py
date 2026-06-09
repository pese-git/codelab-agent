"""Тесты для ContextCompactor."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.agent.context_compactor import ContextCompactor
from codelab.server.llm.models import CompletionResponse, LLMMessage


@pytest.fixture
def compactor():
    return ContextCompactor(
        max_context_tokens=1000,
        reserved_tokens=200,
    )


def make_messages(count, role="user"):
    """Создать N сообщений."""
    return [
        LLMMessage(role=role, content=f"Message {i} " * 50)
        for i in range(count)
    ]


class TestCompactionGuards:
    """4.13 — короткая история (<= 5) → без compaction."""

    @pytest.mark.asyncio
    async def test_short_history_no_compaction(self, compactor):
        history = make_messages(3)
        result, changed, reason = await compactor.compact_if_needed(history)
        assert changed is False
        assert reason == "history_too_short"
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_exact_min_history(self, compactor):
        history = make_messages(5)
        result, changed, reason = await compactor.compact_if_needed(history)
        assert changed is False
        assert reason == "history_too_short"


class TestPrunePhase:
    """4.10 — prune с достаточным уменьшением."""

    @pytest.mark.asyncio
    async def test_prune_removes_tool_outputs(self, compactor):
        history = [
            LLMMessage(role="system", content="System"),
            LLMMessage(role="user", content="Initial " * 100),
            LLMMessage(role="assistant", content="Response " * 50),
            LLMMessage(role="tool", content="Old tool result " * 100),
            LLMMessage(role="tool", content="Another old result " * 100),
            LLMMessage(role="user", content="Recent " * 50),
            LLMMessage(role="assistant", content="Recent response " * 50),
            LLMMessage(role="user", content="Latest " * 50),
        ]
        result, changed, reason = await compactor.compact_if_needed(history)
        assert changed is True
        # Tool messages из middle должны быть удалены
        tool_count = sum(1 for m in result if m.role == "tool")
        assert tool_count == 0  # Все tool messages из middle удалены

    @pytest.mark.asyncio
    async def test_prune_preserves_start_and_end(self, compactor):
        history = [
            LLMMessage(role="system", content="System"),
            LLMMessage(role="user", content="First"),
            LLMMessage(role="tool", content="Old tool " * 100),
            LLMMessage(role="tool", content="Old tool 2 " * 100),
            LLMMessage(role="user", content="Recent"),
            LLMMessage(role="assistant", content="Response"),
            LLMMessage(role="user", content="Latest"),
        ]
        result, changed, reason = await compactor.compact_if_needed(history)
        # Первые 2 сохранены
        assert result[0].content == "System"
        assert result[1].content == "First"
        # Последние 3 сохранены
        assert result[-3].content == "Recent"
        assert result[-2].content == "Response"
        assert result[-1].content == "Latest"


class TestSummarizePhase:
    """4.11 — prune недостаточно → summarize."""

    @pytest.mark.asyncio
    async def test_summarize_when_prune_insufficient(self):
        llm = MagicMock()
        llm.create_completion = AsyncMock(
            return_value=CompletionResponse(
                text="Summary of conversation",
            )
        )
        compactor = ContextCompactor(
            llm=llm,
            max_context_tokens=1000,
            reserved_tokens=200,
        )

        # Много сообщений с большим контентом
        history = [
            LLMMessage(role="system", content="System"),
            LLMMessage(role="user", content="A " * 500),
            LLMMessage(role="assistant", content="B " * 500),
            LLMMessage(role="user", content="C " * 500),
            LLMMessage(role="assistant", content="D " * 500),
            LLMMessage(role="user", content="E " * 500),
            LLMMessage(role="assistant", content="F " * 500),
            LLMMessage(role="user", content="G " * 500),
            LLMMessage(role="user", content="Recent " * 100),
            LLMMessage(role="assistant", content="Response " * 100),
            LLMMessage(role="user", content="Latest " * 100),
        ]

        result, changed, reason = await compactor.compact_if_needed(history)
        assert changed is True
        assert reason == "summarized"


class TestCompactionTrigger:
    """4.12 — условие срабатывания (limit - reserved)."""

    @pytest.mark.asyncio
    async def test_within_limit_no_compaction(self, compactor):
        history = make_messages(6, role="user")
        # Маленький контент — не превышает лимит
        for msg in history:
            msg.content = "short"

        result, changed, reason = await compactor.compact_if_needed(history)
        assert changed is False
        assert reason == "within_limit"

    @pytest.mark.asyncio
    async def test_exceeds_limit_triggers_compaction(self, compactor):
        history = make_messages(10, role="user")
        # Большой контент — превышает лимит
        for msg in history:
            msg.content = "X " * 200

        result, changed, reason = await compactor.compact_if_needed(history)
        assert changed is True

    @pytest.mark.asyncio
    async def test_no_llm_fallback_to_prune_only(self):
        compactor = ContextCompactor(
            llm=None,
            max_context_tokens=1000,
            reserved_tokens=200,
        )
        history = [
            LLMMessage(role="system", content="System"),
            LLMMessage(role="user", content="A " * 500),
            LLMMessage(role="tool", content="Tool " * 500),
            LLMMessage(role="user", content="B " * 500),
            LLMMessage(role="user", content="Recent " * 100),
            LLMMessage(role="assistant", content="Response " * 100),
            LLMMessage(role="user", content="Latest " * 100),
        ]

        result, changed, reason = await compactor.compact_if_needed(history)
        assert changed is True
        assert reason == "pruned_only"

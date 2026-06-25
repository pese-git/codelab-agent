"""Unit тесты для LegacyContextCompactorAdapter."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.agent.context.legacy_bridge import (
    LegacyContextCompactorAdapter,
)
from codelab.server.agent.context_compactor import (
    ContextCompactor as LegacyContextCompactor,
)
from codelab.server.llm.models import LLMMessage


@pytest.fixture
def legacy_compactor():
    return LegacyContextCompactor(
        max_context_tokens=1000,
        reserved_tokens=200,
    )


@pytest.fixture
def adapter(legacy_compactor):
    return LegacyContextCompactorAdapter(legacy_compactor)


def make_messages(count, role="user"):
    return [
        LLMMessage(role=role, content=f"Message {i} " * 50)
        for i in range(count)
    ]


class TestLegacyContextCompactorAdapter:
    """Тесты адаптера legacy ContextCompactor."""

    @pytest.mark.asyncio
    async def test_delegates_to_legacy(self, adapter):
        """Адаптер делегирует legacy compactor."""
        history = make_messages(3)

        result = await adapter.compact_if_needed(
            history,
            max_context_tokens=1000,
            reserved_tokens=200,
        )

        assert isinstance(result, list)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_overrides_max_context_tokens(self, adapter, legacy_compactor):
        """Адаптер временно переопределяет max_context_tokens."""
        history = make_messages(10)
        for msg in history:
            msg.content = "X " * 200

        original_max = legacy_compactor.max_context_tokens
        result = await adapter.compact_if_needed(
            history,
            max_context_tokens=500,
            reserved_tokens=100,
        )

        assert legacy_compactor.max_context_tokens == original_max
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_restores_values_on_exception(self):
        """Адаптер восстанавливает значения при исключении."""
        legacy = MagicMock()
        legacy.max_context_tokens = 1000
        legacy.reserved_tokens = 200
        legacy.compact_if_needed = AsyncMock(side_effect=RuntimeError("fail"))

        adapter = LegacyContextCompactorAdapter(legacy)

        with pytest.raises(RuntimeError):
            await adapter.compact_if_needed(
                [],
                max_context_tokens=500,
                reserved_tokens=100,
            )

        assert legacy.max_context_tokens == 1000
        assert legacy.reserved_tokens == 200

    @pytest.mark.asyncio
    async def test_short_history_no_compaction(self, adapter):
        """Короткая история возвращается без изменений."""
        history = make_messages(3)

        result = await adapter.compact_if_needed(
            history,
            max_context_tokens=1000,
            reserved_tokens=200,
        )

        assert len(result) == 3

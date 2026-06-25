"""Legacy-мост: обёртка вокруг существующего ContextCompactor.

Оборачивает legacy context_compactor.py в реализацию ContextCompactor(ABC)
без изменения логики. Сигнатура compact_if_needed() совместима.

Используется при agents.context.enabled=false (default).
"""

from __future__ import annotations

from codelab.server.agent.context.interfaces import (
    ContextCompactor as ContextCompactorABC,
)
from codelab.server.agent.context_compactor import (
    ContextCompactor as LegacyContextCompactor,
)
from codelab.server.llm.models import LLMMessage


class LegacyContextCompactorAdapter(ContextCompactorABC):
    """Адаптер legacy ContextCompactor к ABC интерфейсу.

    Делегирует всю работу существующему ContextCompactor,
    адаптируя сигнатуры.
    """

    def __init__(self, legacy: LegacyContextCompactor) -> None:
        self._legacy = legacy

    async def compact_if_needed(
        self,
        messages: list[LLMMessage],
        *,
        max_context_tokens: int,
        reserved_tokens: int,
    ) -> list[LLMMessage]:
        """Сжать историю если превышает лимит.

        Делегирует legacy ContextCompactor, временно переопределяя
        max_context_tokens и reserved_tokens для этого вызова.
        """
        original_max = self._legacy.max_context_tokens
        original_reserved = self._legacy.reserved_tokens

        self._legacy.max_context_tokens = max_context_tokens
        self._legacy.reserved_tokens = reserved_tokens

        try:
            result, _, _ = await self._legacy.compact_if_needed(messages)
            return result
        finally:
            self._legacy.max_context_tokens = original_max
            self._legacy.reserved_tokens = original_reserved

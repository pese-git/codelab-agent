"""ContextCompactor — двухфазное сжатие контекста.

Фаза 1: Prune — FIFO удаление старых tool outputs (без LLM)
Фаза 2: LLM Summarize — суммаризация средних сообщений

Гарды:
- history <= 5 → вернуть без изменений
- Сохранить первые 2 сообщения, последние 3, prune middle
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from codelab.server.llm.base import LLMProvider
from codelab.server.llm.models import CompletionRequest, LLMMessage

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Минимальная длина истории для compaction
_MIN_HISTORY_LENGTH = 5


class ContextCompactor:
    """Двухфазное сжатие контекста.

    Attributes:
        llm: LLM провайдер для суммаризации
        model: Модель для суммаризации
        max_context_tokens: Лимит контекстного окна
        reserved_tokens: Зарезервированные токены
    """

    def __init__(
        self,
        llm: LLMProvider | None = None,
        model: str = "openai/gpt-4o-mini",
        max_context_tokens: int = 128000,
        reserved_tokens: int = 4096,
    ) -> None:
        self.llm = llm
        self.model = model
        self.max_context_tokens = max_context_tokens
        self.reserved_tokens = reserved_tokens

    async def compact_if_needed(
        self,
        history: list[LLMMessage],
    ) -> tuple[list[LLMMessage], bool, str]:
        """Сжать историю если превышает лимит.

        Args:
            history: Текущая история сообщений.

        Returns:
            Кортеж (новая история, была ли compaction, причина).
        """
        # Guard: короткая история
        if len(history) <= _MIN_HISTORY_LENGTH:
            return history, False, "history_too_short"

        trigger = self.max_context_tokens - self.reserved_tokens

        # Оценка текущих токенов (приблизительно)
        current_tokens = self._estimate_tokens(history)
        if current_tokens <= trigger:
            return history, False, "within_limit"

        # Фаза 1: Prune
        pruned = self._prune_old_tool_outputs(history)
        pruned_tokens = self._estimate_tokens(pruned)

        if pruned_tokens <= trigger:
            return pruned, True, "pruned"

        # Фаза 2: Summarize (если есть LLM)
        if self.llm is not None:
            summarized = await self._summarize_conversation(pruned)
            return summarized, True, "summarized"

        return pruned, True, "pruned_only"

    def _estimate_tokens(self, messages: list[LLMMessage]) -> int:
        """Приблизительная оценка токенов в сообщениях.

        Простая эвристика: ~4 символа на токен.
        """
        total = 0
        for msg in messages:
            if msg.content:
                total += len(msg.content) // 4
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    total += len(tc.name) // 4
                    total += len(str(tc.arguments)) // 4
        return total

    def _prune_old_tool_outputs(
        self, history: list[LLMMessage]
    ) -> list[LLMMessage]:
        """Фаза 1: FIFO удаление старых tool results.

        Сохраняет первые 2 сообщения, последние 3, prune middle tool results.
        """
        if len(history) <= _MIN_HISTORY_LENGTH:
            return list(history)

        # Сохраняем начало и конец
        keep_start = 2
        keep_end = 3

        start = history[:keep_start]
        end = history[-keep_end:]
        middle = history[keep_start:-keep_end]

        # Удаляем tool messages из middle (FIFO)
        pruned_middle = [msg for msg in middle if msg.role != "tool"]

        return start + pruned_middle + end

    async def _summarize_conversation(
        self, history: list[LLMMessage]
    ) -> list[LLMMessage]:
        """Фаза 2: LLM суммаризация средних сообщений.

        Сохраняет начало + конец, суммаризирует середину.
        """
        if len(history) <= _MIN_HISTORY_LENGTH:
            return list(history)

        keep_start = 2
        keep_end = 3

        start = history[:keep_start]
        end = history[-keep_end:]
        middle = history[keep_start:-keep_end]

        if not middle:
            return list(history)

        # Формируем текст для суммаризации
        middle_text = "\n".join(
            f"[{msg.role}] {msg.content or ''}" for msg in middle
        )

        if not self.llm:
            # Без LLM — просто удаляем середину
            return start + end

        # Запрос на суммаризацию
        prompt = (
            "Summarize the following conversation concisely. "
            "Preserve key information, decisions, and context. "
            "Keep it under 200 words.\n\n"
            f"Conversation:\n{middle_text}"
        )

        try:
            request = CompletionRequest(
                model=self.model,
                messages=[LLMMessage(role="user", content=prompt)],
                max_tokens=500,
                temperature=0.0,
            )
            response = await self.llm.create_completion(request)
            summary = response.text

            # Вставляем summary как assistant message
            summary_msg = LLMMessage(
                role="assistant",
                content=f"[Summary of {len(middle)} messages] {summary}",
            )
            return start + [summary_msg] + end
        except Exception:
            logger.exception("Failed to summarize conversation, using pruned history")
            return start + end

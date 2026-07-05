"""TokenCounter — подсчёт токенов для контекста.

Слой C — Хранение (Phase 2).

Реализации:
- TiktokenCounter: точный подсчёт через tiktoken (cl100k_base)
- ApproximateTokenCounter: fallback через len(text) // 4
- create_token_counter(): фабрика с try import tiktoken → fallback
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from codelab.server.agent.context.interfaces import TokenCounter

if TYPE_CHECKING:
    from codelab.server.llm.models import LLMMessage

logger = logging.getLogger(__name__)


class TiktokenCounter(TokenCounter):
    """Точный подсчёт токенов через библиотеку tiktoken.

    Использует кодировку cl100k_base (GPT-4, GPT-3.5-turbo).
    При сбое кодировки — fallback на approximate для конкретного вызова.
    """

    def __init__(self) -> None:
        import tiktoken  # type: ignore[import-untyped]

        self._encoding = tiktoken.get_encoding("cl100k_base")

    def count(self, text: str) -> int:
        """Подсчитать токены в тексте через tiktoken."""
        try:
            return len(self._encoding.encode(text))
        except Exception:
            logger.error(
                "tiktoken_encoding_failed_using_fallback",
                text_length=len(text),
            )
            return len(text) // 4

    def count_messages(self, messages: list[LLMMessage]) -> int:
        """Подсчитать токены в списке сообщений."""
        total = 0
        for msg in messages:
            if isinstance(msg.content, str):
                total += self.count(msg.content)
            elif isinstance(msg.content, list):
                for part in msg.content:
                    if hasattr(part, "text") and part.text:
                        total += self.count(part.text)
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    total += self.count(tc.name)
                    total += self.count(str(tc.arguments))
            if msg.tool_call_id:
                total += self.count(msg.tool_call_id)
            if msg.name:
                total += self.count(msg.name)
        return total


class ApproximateTokenCounter(TokenCounter):
    """Приблизительный подсчёт токенов: len(text) // 4.

    Fallback когда tiktoken недоступен.
    """

    def count(self, text: str) -> int:
        """Приблизительный подсчёт: ~4 символа на токен."""
        return len(text) // 4

    def count_messages(self, messages: list[LLMMessage]) -> int:
        """Приблизительный подсчёт токенов в сообщениях."""
        total = 0
        for msg in messages:
            if isinstance(msg.content, str):
                total += self.count(msg.content)
            elif isinstance(msg.content, list):
                for part in msg.content:
                    if hasattr(part, "text") and part.text:
                        total += self.count(part.text)
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    total += self.count(tc.name)
                    total += self.count(str(tc.arguments))
            if msg.tool_call_id:
                total += self.count(msg.tool_call_id)
            if msg.name:
                total += self.count(msg.name)
        return total


def create_token_counter() -> TokenCounter:
    """Фабрика: попробовать tiktoken, fallback на approximate.

    Returns:
        TiktokenCounter если tiktoken доступен, иначе ApproximateTokenCounter.
    """
    try:
        counter = TiktokenCounter()
        logger.debug("tiktoken_counter_initialized")
        return counter
    except ImportError:
        logger.warning("tiktoken_not_available_using_fallback")
        return ApproximateTokenCounter()

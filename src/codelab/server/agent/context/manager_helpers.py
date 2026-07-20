"""Чистые вспомогательные функции ContextManager.

Выделены из manager.py: не зависят от состояния менеджера, детерминированы.
compute_fingerprint обязан оставаться байт-идентичным для стабильности prompt-cache.
"""

from __future__ import annotations

import hashlib

from codelab.server.agent.context.budget import DefaultTokenBudgetManager
from codelab.server.llm.models import LLMMessage


def extract_prompt_text(prompt: list[dict]) -> str:
    """Извлечь текст из prompt блоков."""
    parts: list[str] = []
    for block in prompt:
        if block.get("type") == "text":
            text = block.get("text", "")
            if text:
                parts.append(text)
    return " ".join(parts)


def compute_fingerprint(messages: list[LLMMessage]) -> str:
    """Вычислить fingerprint для baseline.

    Детерминированный хэш содержимого (role:content); без timestamps —
    требование стабильности prompt-cache.
    """
    content_parts: list[str] = []
    for msg in messages:
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        content_parts.append(f"{msg.role}:{content}")

    combined = "|".join(content_parts)
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def estimate_total_tokens(
    baseline: list[LLMMessage],
    tail: list[LLMMessage],
) -> int:
    """Оценить общее количество токенов."""
    total = 0
    for msg in baseline + tail:
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        total += DefaultTokenBudgetManager.estimate_tokens(content)
    return total


def split_baseline_tail(
    messages: list[LLMMessage],
) -> tuple[list[LLMMessage], list[LLMMessage]]:
    """Разделить плоский список на baseline (ведущие system) и tail."""
    baseline: list[LLMMessage] = []
    tail: list[LLMMessage] = []
    for msg in messages:
        if msg.role == "system" and not tail:
            baseline.append(msg)
        else:
            tail.append(msg)
    return baseline, tail

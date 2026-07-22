"""Backward-compatibility package re-export. Will be removed in Phase 1.

Сохранён как тонкий re-export, чтобы строки долга в ``import-linter``
``ignore_imports`` (для ``agent.strategies.dispatcher``,
``agent.strategies.base``) продолжали матчиться.
Канонический путь — ``codelab.server.agent.core.strategies``.

Удаляется в Фазе 1 вместе со строками ``ignore_imports``.
"""

from __future__ import annotations

from codelab.server.agent.core.strategies.base import LLMCallStrategy
from codelab.server.agent.core.strategies.dispatcher import (
    StrategyDispatcher,
)

__all__ = ["LLMCallStrategy", "StrategyDispatcher"]

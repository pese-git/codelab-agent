"""Backward-compatibility re-export. Will be removed in Phase 1.

Сохранён как тонкий re-export, чтобы строки долга в ``import-linter``
``ignore_imports`` (для ``agent.strategies.dispatcher``) продолжали
матчиться. Канонический путь — ``codelab.server.agent.core.strategies.dispatcher``.

Удаляется в Фазе 1 вместе со строкой ``ignore_imports``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codelab.server.agent.core.strategies.dispatcher import (
    StrategyDispatcher,
)

if TYPE_CHECKING:
    pass

__all__ = ["StrategyDispatcher"]

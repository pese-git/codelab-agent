"""Backward-compatibility re-export. Will be removed in Phase 1.

Этот модуль сохранён как тонкий re-export, чтобы строка долга
``codelab.server.agent.base -> codelab.server.protocol.state`` в
``pyproject.toml [tool.importlinter] ignore_imports`` продолжала
матчиться (ratchet-контракт). Канонический путь — ``codelab.server.agent.core.agent_base``.

Удаляется в Фазе 1 вместе со строкой ``ignore_imports``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codelab.server.agent.core.agent_base import (
    AgentContext,
    AgentResponse,
    ContinuationContext,
    LLMAgent,
)

if TYPE_CHECKING:
    pass

__all__ = [
    "AgentContext",
    "AgentResponse",
    "ContinuationContext",
    "LLMAgent",
]

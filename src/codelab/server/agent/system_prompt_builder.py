"""Backward-compatibility re-export. Will be removed in Phase 1.

Сохранён как тонкий re-export, чтобы строка долга в ``import-linter``
``ignore_imports`` продолжала матчиться. Канонический путь —
``codelab.server.agent.core.system_prompt_builder``.

Удаляется в Фазе 1 вместе со строкой ``ignore_imports``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codelab.server.agent.core.system_prompt_builder import SystemPromptBuilder

if TYPE_CHECKING:
    pass

__all__ = ["SystemPromptBuilder"]

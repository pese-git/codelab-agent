"""Backward-compatibility re-export. Will be removed in Phase 1.

Сохранён как тонкий re-export, чтобы строка долга в ``import-linter``
``ignore_imports`` продолжала матчиться. Канонический путь —
``codelab.server.agent.core.tool_filter``.

Удаляется в Фазе 1 вместе со строкой ``ignore_imports``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codelab.server.agent.core.tool_filter import ToolFilter

if TYPE_CHECKING:
    pass

__all__ = ["ToolFilter"]

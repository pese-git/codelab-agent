"""NoOpStrategy — возврат оригинального кода.

Fallback для неподдерживаемых языков или бинарных файлов.
"""

from __future__ import annotations

from codelab.server.agent.context.skeletonizer.strategy import SkeletonizerStrategy


class NoOpStrategy(SkeletonizerStrategy):
    """Стратегия без операций — возвращает оригинальный код."""

    def can_handle(self, path: str) -> bool:
        """Поддерживает любые файлы."""
        return True

    def skeletonize(self, code: str, path: str) -> str:
        """Вернуть оригинальный код без изменений."""
        return code

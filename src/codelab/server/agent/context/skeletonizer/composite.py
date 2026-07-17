"""CompositeSkeletonizer — роутер стратегий скелетирования.

Выбирает стратегию по расширению файла:
1. TreeSitterStrategy — для поддерживаемых языков (Python, TypeScript, etc.)
2. RegexStrategy — для остальных текстовых файлов
3. NoOpStrategy — для бинарных файлов

Также реализует интерфейс CodeSkeletonizer из interfaces.py
для обратной совместимости с существующим кодом.
"""

from __future__ import annotations

from pathlib import Path

import structlog

from codelab.server.agent.context.interfaces import CodeSkeletonizer
from codelab.server.agent.context.skeletonizer.noop import NoOpStrategy
from codelab.server.agent.context.skeletonizer.regex import RegexStrategy
from codelab.server.agent.context.skeletonizer.strategy import SkeletonizerStrategy
from codelab.server.agent.context.skeletonizer.treesitter import TreeSitterStrategy

logger = structlog.get_logger(__name__)

BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".svg",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".7z",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".mp3",
    ".mp4",
    ".avi",
    ".mov",
    ".wav",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
}


class CompositeSkeletonizer(CodeSkeletonizer):
    """Роутер стратегий скелетирования.

    Реализует интерфейс CodeSkeletonizer для интеграции
    с существующим кодом (interfaces.py).
    """

    def __init__(
        self,
        strategies: list[SkeletonizerStrategy] | None = None,
    ) -> None:
        self._strategies = strategies or [
            TreeSitterStrategy(),
            RegexStrategy(),
        ]
        self._noop = NoOpStrategy()

    def can_handle(self, path: str) -> bool:
        """Поддерживается ли файл.

        Бинарные файлы не поддерживаются.
        """
        ext = Path(path).suffix.lower()
        return ext not in BINARY_EXTENSIONS

    def skeletonize(self, code: str) -> str:
        """Скелетировать код без пути к файлу.

        Метод ABC CodeSkeletonizer. Без пути язык определить нельзя,
        поэтому выбор стратегии невозможен и код возвращается БЕЗ изменений
        (no-op). Для реальной скелетизации используйте skeletonize_file(code,
        path) — именно его вызывает ThreePhaseCompactor.
        """
        return self._noop.skeletonize(code, "")

    def skeletonize_file(self, code: str, path: str) -> str:
        """Скелетировать код с учётом пути к файлу.

        Основной метод для использования.
        """
        ext = Path(path).suffix.lower()
        if ext in BINARY_EXTENSIONS:
            return code

        for strategy in self._strategies:
            if strategy.can_handle(path):
                try:
                    return strategy.skeletonize(code, path)
                except SyntaxError:
                    logger.warning(
                        "skeletonize_syntax_error",
                        strategy=type(strategy).__name__,
                        path=path,
                    )
                    return code
                except Exception:
                    logger.exception(
                        "skeletonize_failed",
                        strategy=type(strategy).__name__,
                        path=path,
                    )
                    return code

        return code

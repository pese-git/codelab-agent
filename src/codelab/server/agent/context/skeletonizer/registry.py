"""LanguageRegistry — реестр tree-sitter грамматик.

Загружает и кэширует tree-sitter parsers для поддерживаемых языков.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

try:
    import tree_sitter
except ImportError:
    tree_sitter = None  # type: ignore[assignment]
    logger.warning(
        "tree_sitter_not_available",
        detail="skeletonizer falls back to regex/noop",
    )


def _load_grammars() -> dict[str, Callable[[], object]]:
    """Загрузить доступные tree-sitter грамматики, пропуская отсутствующие.

    Отсутствие tree_sitter или отдельной грамматики не является ошибкой:
    скелетизатор деградирует до regex/noop (см. CompositeSkeletonizer).
    """
    loaders: dict[str, Callable[[], object]] = {}
    if tree_sitter is None:
        return loaders

    specs = [
        ("python", "tree_sitter_python", "language"),
        ("typescript", "tree_sitter_typescript", "language_typescript"),
        ("dart", "tree_sitter_dart", "language"),
        ("go", "tree_sitter_go", "language"),
        ("rust", "tree_sitter_rust", "language"),
        ("java", "tree_sitter_java", "language"),
        ("cpp", "tree_sitter_cpp", "language"),
    ]
    for language, module_name, attr in specs:
        try:
            module = importlib.import_module(module_name)
            loaders[language] = getattr(module, attr)
        except (ImportError, AttributeError):
            logger.warning(
                "grammar_not_available",
                language=language,
                module=module_name,
            )
    return loaders


EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "typescript",
    ".jsx": "typescript",
    ".dart": "dart",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "cpp",
    ".h": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
}

_GRAMMAR_LOADERS: dict[str, Callable[[], object]] = _load_grammars()


class LanguageRegistry:
    """Реестр tree-sitter грамматик и parsers.

    Ленивая загрузка: parser создаётся при первом запросе.
    """

    def __init__(self) -> None:
        self._parsers: dict[str, tree_sitter.Parser] = {}

    @staticmethod
    def get_language(path: str) -> str | None:
        """Определить язык по расширению файла."""
        ext = Path(path).suffix.lower()
        return EXTENSION_TO_LANGUAGE.get(ext)

    @staticmethod
    def supported_languages() -> list[str]:
        """Список поддерживаемых языков."""
        return list(_GRAMMAR_LOADERS.keys())

    @staticmethod
    def supported_extensions() -> list[str]:
        """Список поддерживаемых расширений."""
        return list(EXTENSION_TO_LANGUAGE.keys())

    def get_parser(self, language: str) -> tree_sitter.Parser | None:
        """Получить parser для языка.

        Args:
            language: Имя языка (python, typescript, etc.)

        Returns:
            Parser или None если язык не поддерживается.
        """
        if language in self._parsers:
            return self._parsers[language]

        loader = _GRAMMAR_LOADERS.get(language)
        if loader is None:
            logger.warning("language_not_supported", language=language)
            return None

        try:
            lang = tree_sitter.Language(loader())
            parser = tree_sitter.Parser(lang)
            self._parsers[language] = parser
            return parser
        except Exception:
            logger.exception("failed_to_load_grammar", language=language)
            return None

    def can_handle(self, path: str) -> bool:
        """Проверить, поддерживается ли файл."""
        language = self.get_language(path)
        return language is not None and language in _GRAMMAR_LOADERS

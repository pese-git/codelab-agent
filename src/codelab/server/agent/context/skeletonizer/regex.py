"""RegexStrategy — универсальный fallback на regex.

Используется для языков, не поддерживаемых tree-sitter.
Применяет regex-паттерны для поиска функций/классов и замены тел.
"""

from __future__ import annotations

import re
from pathlib import Path

import structlog

from codelab.server.agent.context.skeletonizer.strategy import SkeletonizerStrategy

logger = structlog.get_logger(__name__)

C_LIKE_EXTENSIONS = {
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cc",
    ".cxx",
    ".cs",
    ".php",
    ".swift",
    ".kt",
    ".scala",
}

PYTHON_LIKE_EXTENSIONS = {".py", ".pyx", ".pyi"}

RUBY_LIKE_EXTENSIONS = {".rb", ".rake"}

FUNCTION_PATTERNS = {
    "c_like": re.compile(
        r"(?P<sig>(?:public|private|protected|static|virtual|override|final|inline"
        r"|const|volatile|extern|async|await|\s)*"
        r"(?:[\w<>\[\]:*&,]+)\s+(?:[\w<>\[\]:*&,]+)\s*\([^)]*\)"
        r"(?:\s*const)?(?:\s*noexcept)?(?:\s*->\s*[\w<>\[\]:*&,]+)?)"
        r"\s*\{",
        re.MULTILINE,
    ),
    "python_like": re.compile(
        r"(?P<sig>(?:async\s+)?def\s+[\w]+\s*\([^)]*\)"
        r"(?:\s*->\s*[\w\[\],\s\'\"]+)?)"
        r"\s*:",
        re.MULTILINE,
    ),
    "ruby_like": re.compile(
        r"(?P<sig>def\s+(?:self\.)?[\w]+(?:\([^)]*\))?)"
        r"\s*$",
        re.MULTILINE,
    ),
}


class RegexStrategy(SkeletonizerStrategy):
    """Универсальный regex-based skeletonizer."""

    def can_handle(self, path: str) -> bool:
        """Поддерживает любые текстовые файлы."""
        return True

    def skeletonize(self, code: str, path: str) -> str:
        """Скелетировать код через regex."""
        ext = Path(path).suffix.lower()

        if ext in C_LIKE_EXTENSIONS:
            return self._skeletonize_c_like(code)
        if ext in PYTHON_LIKE_EXTENSIONS:
            return self._skeletonize_python_like(code)
        if ext in RUBY_LIKE_EXTENSIONS:
            return self._skeletonize_ruby_like(code)

        return self._skeletonize_generic(code)

    def _skeletonize_c_like(self, code: str) -> str:
        """Скелетирование C-подобных языков."""
        pattern = FUNCTION_PATTERNS["c_like"]

        def replace_body(match: re.Match) -> str:
            sig = match.group("sig")
            return f"{sig} {{}}"

        result = pattern.sub(replace_body, code)
        if not result.endswith("\n"):
            result += "\n"
        return result

    def _skeletonize_python_like(self, code: str) -> str:
        """Скелетирование Python-подобных языков."""
        pattern = FUNCTION_PATTERNS["python_like"]

        def replace_body(match: re.Match) -> str:
            sig = match.group("sig")
            return f"{sig} ..."

        result = pattern.sub(replace_body, code)
        if not result.endswith("\n"):
            result += "\n"
        return result

    def _skeletonize_ruby_like(self, code: str) -> str:
        """Скелетирование Ruby-подобных языков."""
        pattern = FUNCTION_PATTERNS["ruby_like"]

        def replace_body(match: re.Match) -> str:
            sig = match.group("sig")
            return f"{sig}\n  # ..."

        result = pattern.sub(replace_body, code)
        if not result.endswith("\n"):
            result += "\n"
        return result

    def _skeletonize_generic(self, code: str) -> str:
        """Универсальное скелетирование."""
        lines = code.split("\n")
        result_lines: list[str] = []
        in_function = False
        brace_depth = 0

        for line in lines:
            stripped = line.strip()

            if any(kw in stripped for kw in ("function ", "def ", "func ", "fn ", "sub ")):
                in_function = True
                result_lines.append(line)
                brace_depth += stripped.count("{") - stripped.count("}")
                continue

            if in_function:
                brace_depth += stripped.count("{") - stripped.count("}")
                if brace_depth <= 0:
                    in_function = False
                    result_lines.append(line)
                elif stripped == "{":
                    result_lines.append(line)
                else:
                    continue
            else:
                result_lines.append(line)

        result = "\n".join(result_lines)
        if not result.endswith("\n"):
            result += "\n"
        return result

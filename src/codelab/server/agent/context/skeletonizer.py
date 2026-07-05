"""CodeSkeletonizer — AST-скелетирование кода.

Слой C — Хранение (Phase 2).

Сжимает код до сигнатур, сохраняя структуру:
- imports (отсортированные для детерминизма)
- class/function signatures
- decorators
- type hints

Тела функций/методов заменяются на `...`.

Детерминированный вывод — требование для стабильности кэша.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from codelab.server.agent.context.interfaces import CodeSkeletonizer

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".py"}


class PythonASTSkeletonizer(CodeSkeletonizer):
    """Скелетизатор Python кода на основе AST.

    Заменяет тела функций/методов на `...`, сохраняя сигнатуры.
    Детерминированный вывод: стабильный порядок AST, отсортированные импорты.
    """

    def can_handle(self, path: str) -> bool:
        """Поддерживается ли язык файла."""
        return Path(path).suffix in SUPPORTED_EXTENSIONS

    def skeletonize(self, code: str) -> str:
        """Сжать код до сигнатур. Детерминированно.

        При SyntaxError возвращает оригинальный код.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            logger.warning("skeletonize_syntax_error")
            return code

        transformer = _SkeletonTransformer()
        transformed = transformer.visit(tree)
        ast.fix_missing_locations(transformed)

        try:
            result = ast.unparse(transformed)
        except Exception:
            logger.exception("skeletonize_unparse_error")
            return code

        return _normalize_output(result)


class _SkeletonTransformer(ast.NodeTransformer):
    """AST трансформер: заменяет тела функций на `...`."""

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        """Заменить тело функции на `...`."""
        self.generic_visit(node)
        node.body = [ast.Expr(value=ast.Constant(value=...))]
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        """Заменить тело async функции на `...`."""
        self.generic_visit(node)
        node.body = [ast.Expr(value=ast.Constant(value=...))]
        return node

    def visit_Import(self, node: ast.Import) -> ast.Import:
        """Отсортировать imports для детерминизма."""
        node.names = sorted(node.names, key=lambda n: n.name)
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.ImportFrom:
        """Отсортировать from imports для детерминизма."""
        if node.names:
            node.names = sorted(node.names, key=lambda n: n.name)
        return node


def _normalize_output(code: str) -> str:
    """Нормализовать вывод: убрать лишние пробелы, стабилизировать формат."""
    lines = code.split("\n")
    normalized: list[str] = []
    for line in lines:
        stripped = line.rstrip()
        normalized.append(stripped)

    result = "\n".join(normalized)
    if not result.endswith("\n"):
        result += "\n"
    return result


class NoOpSkeletonizer(CodeSkeletonizer):
    """No-op skeletonizer для неподдерживаемых языков.

    Всегда возвращает оригинальный код.
    """

    def can_handle(self, path: str) -> bool:
        """Не поддерживает никакие языки."""
        return False

    def skeletonize(self, code: str) -> str:
        """Вернуть оригинальный код."""
        return code

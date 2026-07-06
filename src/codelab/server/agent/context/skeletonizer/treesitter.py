"""TreeSitterStrategy — скелетирование через tree-sitter.

Основная стратегия для поддерживаемых языков:
Python, TypeScript, Dart, Go, Rust, Java, C++.

Алгоритм:
1. Определить язык по расширению
2. Распарсить код в AST
3. Найти все функции/методы
4. Заменить их тела на placeholder
5. Сохранить импорты, сигнатуры, декораторы
"""

from __future__ import annotations

import structlog
import tree_sitter

from codelab.server.agent.context.skeletonizer.languages import LANGUAGE_RULES, LanguageRules
from codelab.server.agent.context.skeletonizer.registry import LanguageRegistry
from codelab.server.agent.context.skeletonizer.strategy import SkeletonizerStrategy

logger = structlog.get_logger(__name__)


class TreeSitterStrategy(SkeletonizerStrategy):
    """Скелетирование через tree-sitter."""

    def __init__(self, registry: LanguageRegistry | None = None) -> None:
        self._registry = registry or LanguageRegistry()

    def can_handle(self, path: str) -> bool:
        """Поддерживается ли язык файла."""
        return self._registry.can_handle(path)

    def skeletonize(self, code: str, path: str) -> str:
        """Скелетировать код через tree-sitter."""
        language = self._registry.get_language(path)
        if language is None:
            return code

        rules = LANGUAGE_RULES.get(language)
        if rules is None:
            return code

        parser = self._registry.get_parser(language)
        if parser is None:
            return code

        try:
            tree = parser.parse(code.encode("utf-8"))
            return self._extract_skeleton(code, tree.root_node, rules)
        except Exception:
            logger.exception("tree_sitter_skeletonize_failed", path=path)
            return code

    def _extract_skeleton(
        self,
        source: str,
        root: tree_sitter.Node,
        rules: LanguageRules,
    ) -> str:
        """Извлечь скелет из AST.

        Обходит дерево, заменяет тела функций на placeholder.
        """
        lines = source.split("\n")
        replacements: list[tuple[int, int, int, int, str]] = []

        self._collect_replacements(root, rules, replacements)

        replacements.sort(key=lambda r: (r[0], r[1]), reverse=True)

        for start_row, start_col, end_row, end_col, placeholder in replacements:
            if start_row == end_row:
                line = lines[start_row]
                lines[start_row] = line[:start_col] + placeholder + line[end_col:]
            else:
                first_line = lines[start_row]
                last_line = lines[end_row]
                lines[start_row] = first_line[:start_col] + placeholder + last_line[end_col:]
                for i in range(start_row + 1, end_row + 1):
                    lines[i] = ""

        result_lines = [line for line in lines if line.strip() or line == ""]
        result = "\n".join(result_lines)

        if not result.endswith("\n"):
            result += "\n"

        return result

    def _collect_replacements(
        self,
        node: tree_sitter.Node,
        rules: LanguageRules,
        replacements: list[tuple[int, int, int, int, str]],
    ) -> None:
        """Собрать замены для тел функций."""
        if node.type in rules.function_types:
            body = self._find_body(node, rules.body_field)
            if body is not None:
                replacements.append((
                    body.start_point[0],
                    body.start_point[1],
                    body.end_point[0],
                    body.end_point[1],
                    rules.body_placeholder,
                ))
                return

        for child in node.children:
            self._collect_replacements(child, rules, replacements)

    def _find_body(self, node: tree_sitter.Node, field_name: str) -> tree_sitter.Node | None:
        """Найти тело функции/метода."""
        body = node.child_by_field_name(field_name)
        if body is not None:
            return body

        for child in node.children:
            if child.type in ("block", "statement_block", "body"):
                return child

        return None

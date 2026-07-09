"""Skeletonizer — мультиязыковое AST-скелетирование кода.

Слой C — Хранение (Phase 2).

Архитектура Strategy Pattern:
- TreeSitterStrategy: точное скелетирование через tree-sitter (7 языков)
- RegexStrategy: универсальный fallback на regex
- NoOpStrategy: возврат оригинала для неподдерживаемых языков
- CompositeSkeletonizer: роутер, выбирает стратегию по расширению

Поддерживаемые языки: Python, TypeScript, Dart, Go, Rust, Java, C++.
"""

from codelab.server.agent.context.skeletonizer.composite import CompositeSkeletonizer
from codelab.server.agent.context.skeletonizer.noop import NoOpStrategy
from codelab.server.agent.context.skeletonizer.regex import RegexStrategy
from codelab.server.agent.context.skeletonizer.strategy import SkeletonizerStrategy
from codelab.server.agent.context.skeletonizer.treesitter import TreeSitterStrategy

__all__ = [
    "CompositeSkeletonizer",
    "NoOpStrategy",
    "RegexStrategy",
    "SkeletonizerStrategy",
    "TreeSitterStrategy",
]

"""DependencyGraph — граф зависимостей файлов на основе regex.

Извлекает импорты из Python файлов и строит граф зависимостей.
Используется для расширения контекста: если файл A импортирует файл B,
то при работе с A также загружается B.

Слой A — Сбор контекста (Phase 1).
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from codelab.server.agent.context.interfaces import DependencyGraph

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

IMPORT_PATTERNS = [
    re.compile(r"^import\s+([a-zA-Z_][a-zA-Z0-9_.]*)", re.MULTILINE),
    re.compile(r"^from\s+([a-zA-Z_][a-zA-Z0-9_.]*)\s+import", re.MULTILINE),
]


class RegexDependencyGraph(DependencyGraph):
    """Граф зависимостей на основе regex-парсинга импортов."""

    def __init__(self, project_root: Path | None = None) -> None:
        self._project_root = project_root or Path.cwd()
        self._dependencies: dict[str, set[str]] = defaultdict(set)
        self._dependents: dict[str, set[str]] = defaultdict(set)

    def add_file(self, path: str, imports: list[str]) -> None:
        """Добавить файл в граф с его импортами.

        Args:
            path: Путь к файлу
            imports: Список импортируемых модулей/файлов
        """
        normalized_path = self._normalize_path(path)

        for imp in imports:
            resolved = self._resolve_import(imp)
            if resolved and resolved != normalized_path:
                self._dependencies[normalized_path].add(resolved)
                self._dependents[resolved].add(normalized_path)

    def get_dependencies(self, path: str, *, recursive: bool = False) -> list[str]:
        """Получить зависимости файла.

        Args:
            path: Путь к файлу
            recursive: Рекурсивное разрешение (Phase 5, в Phase 1 игнорируется)

        Returns:
            Список путей к зависимым файлам
        """
        normalized_path = self._normalize_path(path)
        direct_deps = self._dependencies.get(normalized_path, set())

        if not recursive:
            return sorted(direct_deps)

        visited: set[str] = set()
        self._collect_dependencies_recursive(normalized_path, visited)
        visited.discard(normalized_path)
        return sorted(visited)

    def _collect_dependencies_recursive(self, path: str, visited: set[str]) -> None:
        """Рекурсивный сбор зависимостей с защитой от циклов."""
        if path in visited:
            return
        visited.add(path)

        for dep in self._dependencies.get(path, set()):
            self._collect_dependencies_recursive(dep, visited)

    def get_dependents(self, path: str) -> list[str]:
        """Получить файлы, зависящие от данного.

        Args:
            path: Путь к файлу

        Returns:
            Список путей к зависимым файлам
        """
        normalized_path = self._normalize_path(path)
        return sorted(self._dependents.get(normalized_path, set()))

    def parse_imports(self, code: str) -> list[str]:
        """Извлечь импорты из кода.

        Args:
            code: Исходный код Python файла

        Returns:
            Список импортируемых модулей
        """
        imports: set[str] = set()

        for pattern in IMPORT_PATTERNS:
            matches = pattern.findall(code)
            imports.update(matches)

        return list(imports)

    def _normalize_path(self, path: str) -> str:
        """Нормализовать путь к файлу."""
        import contextlib

        try:
            p = Path(path)
            if p.is_absolute():
                with contextlib.suppress(ValueError):
                    p = p.relative_to(self._project_root)
            return str(p).replace("\\", "/")
        except Exception:
            return path

    def _resolve_import(self, import_name: str) -> str | None:
        """Преобразовать имя импорта в путь к файлу.

        Args:
            import_name: Имя модуля (например, "src.module.submodule")

        Returns:
            Путь к файлу или None если не удалось разрешить
        """
        parts = import_name.split(".")

        candidates = [
            "/".join(parts) + ".py",
            "/".join(parts[:-1]) + ".py" if len(parts) > 1 else None,
            parts[0] + ".py" if len(parts) == 1 else None,
        ]

        for candidate in candidates:
            if candidate is None:
                continue
            full_path = self._project_root / candidate
            if full_path.exists():
                return candidate

        if len(parts) >= 2:
            return "/".join(parts[:-1]) + ".py"

        return None

    def clear(self) -> None:
        """Очистить граф."""
        self._dependencies.clear()
        self._dependents.clear()

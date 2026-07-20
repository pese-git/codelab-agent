"""DependencyGraph — граф зависимостей файлов на основе regex.

Извлекает импорты из Python и Dart файлов и строит граф зависимостей.
Используется для расширения контекста: если файл A импортирует файл B,
то при работе с A также загружается B.

Поддерживаемые языки:
- Python: `import module`, `from module import ...`
- Dart: `import 'path.dart'`, `export 'path.dart'`

Слой A — Сбор контекста (Phase 1).
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.agent.context.interfaces import DependencyGraph

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

PYTHON_IMPORT_PATTERNS = [
    re.compile(r"^import\s+([a-zA-Z_][a-zA-Z0-9_.]*)", re.MULTILINE),
    re.compile(r"^from\s+([a-zA-Z_][a-zA-Z0-9_.]*)\s+import", re.MULTILINE),
]

DART_IMPORT_PATTERNS = [
    re.compile(r"""import\s+['"]([^'"]+)['"]"""),
    re.compile(r"""export\s+['"]([^'"]+)['"]"""),
]

IMPORT_PATTERNS = PYTHON_IMPORT_PATTERNS + DART_IMPORT_PATTERNS


class RegexDependencyGraph(DependencyGraph):
    """Граф зависимостей на основе regex-парсинга импортов."""

    def __init__(self, project_root: Path | None = None, max_depth: int | None = None) -> None:
        self._project_root = project_root or Path.cwd()
        self._dependencies: dict[str, set[str]] = defaultdict(set)
        self._dependents: dict[str, set[str]] = defaultdict(set)
        self._project_files: list[str] | None = None
        self._max_depth = max_depth

    def set_max_depth(self, max_depth: int | None) -> None:
        """Задать максимальную глубину рекурсивного обхода.

        Args:
            max_depth: Максимальная глубина (1-3 согласно investigation_depth),
                      None для неограниченной глубины.
        """
        self._max_depth = max_depth

    def set_project_root(self, project_root: Path) -> None:
        """Задать корень проекта (директория пользовательской сессии).

        Важно: по умолчанию граф укоренён в cwd процесса сервера, что неверно —
        разрешение импортов и нормализация путей должны идти относительно
        директории пользовательского проекта (`session.cwd`).
        """
        self._project_root = project_root

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

    def _collect_dependencies_recursive(
        self, path: str, visited: set[str], *, current_depth: int = 0
    ) -> None:
        """Рекурсивный сбор зависимостей с защитой от циклов и ограничением глубины.

        current_depth=0 — начальный файл, current_depth=1 — прямые зависимости, и т.д.
        """
        if path in visited:
            return
        if self._max_depth is not None and current_depth > self._max_depth:
            return
        visited.add(path)

        for dep in self._dependencies.get(path, set()):
            self._collect_dependencies_recursive(dep, visited, current_depth=current_depth + 1)

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
        """Извлечь импорты из кода (Python + Dart).

        Args:
            code: Исходный код файла

        Returns:
            Список импортируемых модулей/путей.
            Встроенные библиотеки (dart:*) отфильтрованы.
        """
        imports: set[str] = set()

        for pattern in IMPORT_PATTERNS:
            matches = pattern.findall(code)
            imports.update(matches)

        imports.discard("")
        return [imp for imp in imports if not imp.startswith("dart:")]

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

        Поддерживает:
        - Python: "module.submodule" → "module/submodule.py"
        - Dart: "package:app/path.dart" → "lib/path.dart"
        - Dart relative: "src/utils.dart" → "src/utils.dart"

        Args:
            import_name: Имя модуля или путь к файлу

        Returns:
            Путь к файлу или None если не удалось разрешить
        """
        # Dart package import: "package:name/path.dart" → "lib/path.dart"
        if import_name.startswith("package:"):
            parts = import_name[len("package:") :].split("/", 1)
            if len(parts) == 2:
                candidate = "lib/" + parts[1]
                if (self._project_root / candidate).exists():
                    return candidate
                return candidate
            return None

        # Path-like import (contains / or ends with .dart) — try as-is
        if "/" in import_name or import_name.endswith(".dart"):
            return import_name

        # Python-style module import
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
        self._project_files = None

    def set_project_files(self, files: list[str]) -> None:
        """Установить кэш структуры проекта.

        Args:
            files: Список относительных путей к файлам проекта
        """
        self._project_files = files
        logger.debug("Project files cached", count=len(files))

    def get_project_files(self) -> list[str] | None:
        """Получить кэш структуры проекта.

        Returns:
            Список путей или None если кэш не загружен
        """
        return self._project_files

    def get_stats(self) -> dict[str, Any]:
        """Экспортировать статистику графа зависимостей.

        Returns:
            Dict с агрегированной статистикой: files_in_graph, total_dependencies,
            total_dependents, project_files_cached.
        """
        return {
            "files_in_graph": len(self._dependencies),
            "total_dependencies": sum(len(deps) for deps in self._dependencies.values()),
            "total_dependents": sum(len(deps) for deps in self._dependents.values()),
            "project_files_cached": len(self._project_files) if self._project_files else 0,
        }

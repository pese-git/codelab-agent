"""ContextGatherer — сбор релевантных файлов для контекста.

Выполняет пайплайн:
1. project_tree() — получить структуру проекта
2. search() — найти файлы по поисковым терминам
3. read_file() — прочитать содержимое кандидатов
4. DependencyGraph — расширить контекст зависимостями
5. Отбор — выбрать наиболее релевантные файлы

Весь I/O выполняется через ACP ToolRegistry (без собственного файлового доступа).

Слой A — Сбор контекста (Phase 1).
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from codelab.server.agent.context.budget import DefaultTokenBudgetManager
from codelab.server.agent.context.interfaces import ContextGatherer
from codelab.server.agent.context.models import (
    BuildOptions,
    ContextItem,
    ContextType,
    TaskProfile,
)

if TYPE_CHECKING:
    from codelab.server.agent.context.dependency_graph import RegexDependencyGraph
    from codelab.server.tools.base import ToolRegistry

logger = logging.getLogger(__name__)

BINARY_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dll", ".exe", ".bin", ".obj", ".o",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",
    ".zip", ".tar", ".gz", ".bz2", ".rar", ".7z",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".woff", ".woff2", ".ttf", ".eot",
    ".db", ".sqlite", ".sqlite3",
}


class ACPContextGatherer(ContextGatherer):
    """Сборщик контекста через ACP ToolRegistry."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        dependency_graph: RegexDependencyGraph,
        session_id: str,
    ) -> None:
        self._tool_registry = tool_registry
        self._dependency_graph = dependency_graph
        self._session_id = session_id

    async def gather(
        self,
        profile: TaskProfile,
        session: Any,
        *,
        options: BuildOptions | None = None,
    ) -> list[ContextItem]:
        """Собрать релевантные файлы для задачи.

        Args:
            profile: Профиль задачи от TaskAnalyzer
            session: Состояние сессии
            options: Опции сборки (max_files и т.д.)

        Returns:
            Список ContextItem с содержимым файлов
        """
        start_time = time.time()
        max_files = options.max_files if options and options.max_files else 20

        logger.debug(
            "Starting context gather",
            task_type=profile.task_type,
            search_terms=profile.search_terms,
            max_files=max_files,
        )

        candidates: list[str] = []

        if profile.target_modules:
            candidates.extend(profile.target_modules)

        for term in profile.search_terms[:5]:
            search_results = await self._search_files(term)
            candidates.extend(search_results)

        unique_candidates = self._deduplicate(candidates)
        logger.debug("Found %d candidate files", len(unique_candidates))

        items: list[ContextItem] = []
        for path in unique_candidates[:max_files]:
            content = await self._read_file(path)
            if content is None:
                continue

            if self._is_binary(path) or self._is_empty(content):
                continue

            imports = self._dependency_graph.parse_imports(content)
            self._dependency_graph.add_file(path, imports)

            token_count = DefaultTokenBudgetManager.estimate_tokens(content)
            items.append(
                ContextItem(
                    id=path,
                    type=ContextType.FILE_CONTENT,
                    content=content,
                    priority=5,
                    owner_scope="gather",
                    token_count=token_count,
                    last_accessed=time.time(),
                )
            )

        dependent_files = self._get_dependents(items)
        for dep_path in dependent_files:
            if len(items) >= max_files:
                break
            if any(item.id == dep_path for item in items):
                continue

            content = await self._read_file(dep_path)
            if content is None or self._is_binary(dep_path) or self._is_empty(content):
                continue

            token_count = DefaultTokenBudgetManager.estimate_tokens(content)
            items.append(
                ContextItem(
                    id=dep_path,
                    type=ContextType.FILE_CONTENT,
                    content=content,
                    priority=3,
                    owner_scope="gather",
                    token_count=token_count,
                    last_accessed=time.time(),
                )
            )

        elapsed_ms = (time.time() - start_time) * 1000
        logger.debug(
            "Context gather completed",
            files_gathered=len(items),
            elapsed_ms=elapsed_ms,
        )

        return items

    async def _search_files(self, term: str) -> list[str]:
        """Поиск файлов по термину через ToolRegistry."""
        try:
            tools = self._tool_registry.get_available_tools(self._session_id)
            search_tool = None
            for tool in tools:
                if tool.name == "fs_search" or tool.name == "search":
                    search_tool = tool
                    break

            if search_tool is None:
                logger.debug("Search tool not found, skipping search for '%s'", term)
                return []

            result = await self._tool_registry.execute_tool(
                self._session_id,
                "fs_search",
                {"pattern": term, "max_results": 10},
            )

            if result.success and isinstance(result.result, list):
                return [str(item.get("path", "")) for item in result.result if item.get("path")]

            return []
        except Exception:
            logger.exception("Search failed for term '%s'", term)
            return []

    async def _read_file(self, path: str) -> str | None:
        """Прочитать файл через ToolRegistry."""
        try:
            result = await self._tool_registry.execute_tool(
                self._session_id,
                "fs_read",
                {"path": path},
            )

            if result.success and isinstance(result.result, dict):
                content = result.result.get("content")
                if isinstance(content, str):
                    return content

            return None
        except Exception:
            logger.exception("Failed to read file '%s'", path)
            return None

    def _get_dependents(self, items: list[ContextItem]) -> list[str]:
        """Получить файлы, зависящие от загруженных."""
        dependents: set[str] = set()
        for item in items:
            deps = self._dependency_graph.get_dependents(item.id)
            dependents.update(deps)
        return list(dependents)

    @staticmethod
    def _deduplicate(paths: list[str]) -> list[str]:
        """Удалить дубликаты путей."""
        seen: set[str] = set()
        result: list[str] = []
        for path in paths:
            if path and path not in seen:
                seen.add(path)
                result.append(path)
        return result

    @staticmethod
    def _is_binary(path: str) -> bool:
        """Проверить, является ли файл бинарным."""
        return any(path.lower().endswith(ext) for ext in BINARY_EXTENSIONS)

    @staticmethod
    def _is_empty(content: str) -> bool:
        """Проверить, пуст ли файл."""
        return len(content.strip()) == 0

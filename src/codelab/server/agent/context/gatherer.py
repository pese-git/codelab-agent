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

import time
from typing import TYPE_CHECKING, Any

import structlog

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

logger = structlog.get_logger(__name__)

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

        logger.info(
            "context.gather.start",
            session_id=self._session_id,
            task_type=profile.task_type,
            search_terms=profile.search_terms,
            target_modules=profile.target_modules,
            max_files=max_files,
        )

        # Этап 1: Сбор кандидатов из target_modules
        candidates: list[str] = []

        if profile.target_modules:
            candidates.extend(profile.target_modules)
            logger.debug(
                "context.gather.target_modules_added",
                session_id=self._session_id,
                count=len(profile.target_modules),
                modules=profile.target_modules,
            )

        # Этап 2: Поиск файлов по поисковым терминам
        search_start = time.time()
        search_results_by_term: dict[str, list[str]] = {}
        
        for term in profile.search_terms[:5]:
            term_start = time.time()
            search_results = await self._search_files(term)
            term_ms = (time.time() - term_start) * 1000
            
            search_results_by_term[term] = search_results
            candidates.extend(search_results)
            
            logger.debug(
                "context.gather.search.term",
                session_id=self._session_id,
                term=term,
                results_count=len(search_results),
                results=search_results[:5],  # Первые 5 результатов
                elapsed_ms=term_ms,
            )

        search_ms = (time.time() - search_start) * 1000
        logger.info(
            "context.gather.search.complete",
            session_id=self._session_id,
            terms_searched=len(profile.search_terms[:5]),
            total_results=len(candidates),
            elapsed_ms=search_ms,
        )

        # Этап 3: Дедупликация кандидатов
        unique_candidates = self._deduplicate(candidates)
        logger.debug(
            "context.gather.candidates.deduplicated",
            session_id=self._session_id,
            before_dedup=len(candidates),
            after_dedup=len(unique_candidates),
            duplicates_removed=len(candidates) - len(unique_candidates),
        )

        # Этап 4: Чтение файлов и построение графа зависимостей
        read_start = time.time()
        items: list[ContextItem] = []
        files_read = 0
        files_skipped_binary = 0
        files_skipped_empty = 0
        files_skipped_error = 0

        for path in unique_candidates[:max_files]:
            content = await self._read_file(path)
            
            if content is None:
                files_skipped_error += 1
                logger.debug(
                    "context.gather.file.read_failed",
                    session_id=self._session_id,
                    path=path,
                )
                continue

            if self._is_binary(path):
                files_skipped_binary += 1
                logger.debug(
                    "context.gather.file.skipped_binary",
                    session_id=self._session_id,
                    path=path,
                )
                continue

            if self._is_empty(content):
                files_skipped_empty += 1
                logger.debug(
                    "context.gather.file.skipped_empty",
                    session_id=self._session_id,
                    path=path,
                )
                continue

            # Парсинг импортов и добавление в граф зависимостей
            imports = self._dependency_graph.parse_imports(content)
            self._dependency_graph.add_file(path, imports)
            
            logger.debug(
                "context.gather.file.processed",
                session_id=self._session_id,
                path=path,
                content_length=len(content),
                imports_count=len(imports),
                imports=imports[:5],  # Первые 5 импортов
            )

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
            files_read += 1

        read_ms = (time.time() - read_start) * 1000
        logger.info(
            "context.gather.files_read.complete",
            session_id=self._session_id,
            files_read=files_read,
            files_skipped_binary=files_skipped_binary,
            files_skipped_empty=files_skipped_empty,
            files_skipped_error=files_skipped_error,
            elapsed_ms=read_ms,
        )

        # Этап 5: Добавление зависимых файлов
        dependents_start = time.time()
        dependent_files = self._get_dependents(items)
        
        logger.debug(
            "context.gather.dependents.found",
            session_id=self._session_id,
            dependents_count=len(dependent_files),
            dependents=dependent_files[:10],  # Первые 10
        )

        dependents_added = 0
        for dep_path in dependent_files:
            if len(items) >= max_files:
                logger.debug(
                    "context.gather.dependents.limit_reached",
                    session_id=self._session_id,
                    max_files=max_files,
                )
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
            dependents_added += 1

        dependents_ms = (time.time() - dependents_start) * 1000
        logger.debug(
            "context.gather.dependents.complete",
            session_id=self._session_id,
            dependents_added=dependents_added,
            elapsed_ms=dependents_ms,
        )

        elapsed_ms = (time.time() - start_time) * 1000
        total_tokens = sum(item.token_count for item in items)
        
        logger.info(
            "context.gather.complete",
            session_id=self._session_id,
            files_gathered=len(items),
            total_tokens=total_tokens,
            file_paths=[item.id for item in items],
            total_elapsed_ms=elapsed_ms,
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

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

import json
import time
from difflib import SequenceMatcher
from pathlib import PurePosixPath
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
    from codelab.server.observability.tracer import Tracer
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

IGNORE_DIRS = {
    ".git", "__pycache__", "venv", ".venv", "node_modules",
    ".idea", ".vscode", "build", "dist", ".dart_tool",
    ".fvm", "android", "ios", "macos", "linux", "windows", "web",
    ".DS_Store", ".gradle", ".codelab",
}


class ACPContextGatherer(ContextGatherer):
    """Сборщик контекста через ACP ToolRegistry."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        dependency_graph: RegexDependencyGraph,
        session_id: str,
        tracer: Tracer | None = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._dependency_graph = dependency_graph
        self._session_id = session_id
        self._tracer = tracer

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

        span = None
        if self._tracer is not None:
            span = self._tracer.start_span(
                name="context.gather",
                session_id=self._session_id,
            )

        logger.info(
            "context.gather.start",
            session_id=self._session_id,
            task_type=profile.task_type,
            search_terms=profile.search_terms,
            target_modules=profile.target_modules,
            max_files=max_files,
        )

        # Этап 0: Получаем структуру проекта из кэша сессии
        project_files_start = time.time()
        project_files = self._list_project_files(session)

        if not project_files:
            project_files = await self._bootstrap_project_files(session)

        project_files_ms = (time.time() - project_files_start) * 1000

        logger.info(
            "context.gather.project_files.ready",
            session_id=self._session_id,
            count=len(project_files),
            elapsed_ms=project_files_ms,
        )

        # Этап 1: Сбор кандидатов из target_modules с адаптивным поиском
        candidates: list[str] = []

        if profile.target_modules:
            for module in profile.target_modules:
                # Проверяем существование файла в реальной структуре
                if module in project_files:
                    candidates.append(module)
                else:
                    # Fallback: ищем похожие файлы
                    similar = self._find_similar_files(module, project_files)
                    candidates.extend(similar)
                    logger.info(
                        "context.gather.target_module.fallback",
                        session_id=self._session_id,
                        original=module,
                        found_count=len(similar),
                        found=similar[:5],
                    )

            logger.debug(
                "context.gather.target_modules_added",
                session_id=self._session_id,
                count=len(candidates),
                modules=candidates[:10],
            )

        # Этап 2: Поиск файлов по поисковым терминам в реальной структуре
        search_start = time.time()
        search_results_by_term: dict[str, list[str]] = {}
        
        for term in profile.search_terms[:5]:
            term_start = time.time()
            search_results = await self._search_in_files(term, project_files, session)
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
        logger.info(
            "context.gather.candidates.deduplicated",
            session_id=self._session_id,
            before_dedup=len(candidates),
            after_dedup=len(unique_candidates),
            duplicates_removed=len(candidates) - len(unique_candidates),
            candidates=unique_candidates[:20],
        )

        # Этап 3.5: Fallback — если кандидатов нет, собрать основные файлы проекта
        if not unique_candidates and project_files:
            fallback_files = self._get_fallback_files(project_files, max_files)
            unique_candidates = fallback_files
            logger.info(
                "context.gather.fallback_files",
                session_id=self._session_id,
                count=len(fallback_files),
                files=fallback_files[:10],
            )

        # Этап 4: Чтение файлов и построение графа зависимостей
        read_start = time.time()
        items: list[ContextItem] = []
        files_read = 0
        files_skipped_binary = 0
        files_skipped_empty = 0
        files_skipped_error = 0

        for path in unique_candidates[:max_files]:
            content = await self._read_file(path, session)
            
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

            content = await self._read_file(dep_path, session)
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

        if span is not None and self._tracer is not None:
            self._tracer.end_span(span, attributes={
                "task_type": profile.task_type,
                "search_terms": profile.search_terms,
                "candidate_files": len(unique_candidates),
                "selected_files": len(items),
            })

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

            if result.success and isinstance(result.raw_output, dict):
                items = result.raw_output.get("results", [])
                if isinstance(items, list):
                    return [str(item.get("path", "")) for item in items if item.get("path")]

            return []
        except Exception:
            logger.exception("Search failed for term '%s'", term)
            return []

    async def _read_file(self, path: str, session: Any) -> str | None:
        """Прочитать файл через ToolRegistry."""
        try:
            result = await self._tool_registry.execute_tool(
                self._session_id,
                "fs/read_text_file",
                {"path": path},
                session=session,
            )

            if result.success and result.output:
                return result.output

            if not result.success:
                logger.debug(
                    "context.gather.file.read_error",
                    session_id=self._session_id,
                    path=path,
                    error=result.error,
                )

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

    def _list_project_files(self, session: Any) -> list[str]:
        """Получить список файлов проекта из кэша сессии.

        Структура проекта предоставляется агентом через terminal/create
        в рамках agent loop (где permission flow активен) и сохраняется
        в session.config_values["project_structure"] как JSON-список путей.

        Args:
            session: Состояние сессии с config_values

        Returns:
            Список относительных путей к файлам проекта (может быть пустым)
        """
        cached = self._dependency_graph.get_project_files()
        if cached is not None:
            logger.debug(
                "context.gather.project_files.from_cache",
                session_id=self._session_id,
                count=len(cached),
            )
            return cached

        config_values = getattr(session, "config_values", {}) or {}
        structure_json = config_values.get("project_structure")

        if structure_json:
            try:
                raw_files = json.loads(structure_json)
                if isinstance(raw_files, list):
                    filtered = self._filter_paths([str(f) for f in raw_files])
                    self._dependency_graph.set_project_files(filtered)
                    logger.info(
                        "context.gather.project_files.from_session",
                        session_id=self._session_id,
                        total_files=len(raw_files),
                        filtered_files=len(filtered),
                    )
                    return filtered
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    "context.gather.project_files.invalid_json",
                    session_id=self._session_id,
                )

        logger.debug(
            "context.gather.project_files.not_available",
            session_id=self._session_id,
            hint="Agent has not yet saved project structure via session/set_config_option",
        )
        return []

    async def _bootstrap_project_files(self, session: Any) -> list[str]:
        """Получить структуру проекта через terminal, если она отсутствует.

        Запускает `find . -type f` через terminal/create, ждёт завершения
        через terminal/wait_for_exit, парсит вывод и сохраняет в сессию.

        Args:
            session: Состояние сессии с config_values

        Returns:
            Список отфильтрованных путей к файлам проекта
        """
        try:
            create_result = await self._tool_registry.execute_tool(
                self._session_id,
                "terminal/create",
                {"command": "find . -type f"},
                session=session,
            )

            if not create_result.success:
                logger.debug(
                    "context.gather.bootstrap.terminal_create_failed",
                    session_id=self._session_id,
                )
                return []

            terminal_id = ""
            if create_result.metadata:
                terminal_id = create_result.metadata.get("terminal_id", "")
            if not terminal_id and create_result.raw_output:
                terminal_id = create_result.raw_output.get("terminal_id", "")

            if not terminal_id:
                logger.debug(
                    "context.gather.bootstrap.no_terminal_id",
                    session_id=self._session_id,
                )
                return []

            wait_result = await self._tool_registry.execute_tool(
                self._session_id,
                "terminal/wait_for_exit",
                {"terminal_id": terminal_id},
                session=session,
            )

            if not wait_result.success or not wait_result.output:
                logger.debug(
                    "context.gather.bootstrap.terminal_wait_failed",
                    session_id=self._session_id,
                )
                return []

            raw_files = self._parse_find_output(wait_result.output)
            filtered = self._filter_paths(raw_files)

            if filtered:
                self._dependency_graph.set_project_files(filtered)
                config_values = getattr(session, "config_values", {}) or {}
                config_values["project_structure"] = json.dumps(filtered)

                logger.info(
                    "context.gather.bootstrap.complete",
                    session_id=self._session_id,
                    total_files=len(raw_files),
                    filtered_files=len(filtered),
                )

            return filtered

        except Exception:
            logger.exception(
                "context.gather.bootstrap.error",
                session_id=self._session_id,
            )
            return []

    @staticmethod
    def _get_fallback_files(project_files: list[str], max_files: int) -> list[str]:
        """Собрать основные файлы проекта, когда нет кандидатов.

        Приоритет:
        1. Конфигурационные файлы проекта (pubspec.yaml, package.json, pyproject.toml)
        2. Главные файлы (main.dart, main.py, index.js, App.tsx)
        3. Остальные файлы исходного кода (lib/, src/, app/)

        Args:
            project_files: Список всех путей в проекте
            max_files: Максимальное количество файлов

        Returns:
            Список основных файлов проекта
        """
        config_files = {
            "pubspec.yaml", "package.json", "pyproject.toml", "setup.py",
            "setup.cfg", "Cargo.toml", "go.mod", "pom.xml", "build.gradle",
            "build.gradle.kts", "CMakeLists.txt", "Makefile", "README.md",
        }
        main_files_patterns = {
            "main.dart", "main.py", "index.js", "index.ts", "index.tsx",
            "App.tsx", "App.jsx", "app.py", "server.py",
        }
        source_dirs = {"lib", "src", "app", "pkg", "cmd"}

        priority_1: list[str] = []
        priority_2: list[str] = []
        priority_3: list[str] = []

        for path in project_files:
            filename = PurePosixPath(path).name
            parts = PurePosixPath(path).parts

            if any(part in IGNORE_DIRS for part in parts):
                continue

            if path in config_files or filename in config_files:
                priority_1.append(path)
            elif filename in main_files_patterns:
                priority_2.append(path)
            elif len(parts) > 1 and parts[0] in source_dirs:
                priority_3.append(path)

        result: list[str] = []
        for group in [priority_1, priority_2, priority_3]:
            for path in group:
                if len(result) >= max_files:
                    return result
                if path not in result:
                    result.append(path)

        return result

    @staticmethod
    def _parse_find_output(output: str) -> list[str]:
        """Парсить вывод find команды в список путей."""
        paths = []
        for line in output.split("\n"):
            line = line.strip()
            if not line or line.startswith("find:"):
                continue
            if line.startswith("./"):
                line = line[2:]
            if line:
                paths.append(line)
        return paths

    @staticmethod
    def _filter_paths(paths: list[str]) -> list[str]:
        """Отфильтровать мусорные папки и файлы.

        Args:
            paths: Список путей

        Returns:
            Отфильтрованный список путей
        """
        filtered = []
        for path in paths:
            normalized = path.replace("\\", "/").strip()

            if not normalized or normalized in (".", "./"):
                continue

            if normalized.startswith("./"):
                normalized = normalized[2:]

            if not normalized:
                continue

            parts = normalized.split("/")

            if any(part in IGNORE_DIRS for part in parts):
                continue

            filtered.append(normalized)

        return filtered

    @staticmethod
    def _detect_project_type(project_files: list[str]) -> str:
        """Определить тип проекта по файлам.

        Args:
            project_files: Список путей в проекте

        Returns:
            Тип проекта: "dart", "python", "javascript", "unknown"
        """
        file_set = set(project_files)

        if "pubspec.yaml" in file_set:
            return "dart"
        if any(f.endswith(".dart") for f in project_files[:50]):
            return "dart"

        if any(f in file_set for f in ("pyproject.toml", "setup.py", "setup.cfg")):
            return "python"
        if any(f.endswith(".py") for f in project_files[:50]):
            return "python"

        if "package.json" in file_set:
            return "javascript"
        if any(f.endswith((".js", ".ts", ".jsx", ".tsx")) for f in project_files[:50]):
            return "javascript"

        return "unknown"

    @staticmethod
    def _map_path_to_project(target: str, project_type: str) -> list[str]:
        """Сгенерировать варианты путей для поиска в проекте.

        Args:
            target: Целевой путь от LLM (например, "src/auth.py")
            project_type: Тип проекта ("dart", "python", "javascript")

        Returns:
            Список вариантов путей для поиска
        """
        target_path = PurePosixPath(target)
        target_stem = target_path.stem
        target_suffix = target_path.suffix

        candidates: list[str] = []

        if project_type == "dart":
            if target_suffix in (".py", ".js", ".ts"):
                candidates.append(f"lib/{target_stem}.dart")
                candidates.append(f"lib/src/{target_stem}.dart")
                candidates.append(f"lib/screens/{target_stem}_screen.dart")
                candidates.append(f"lib/widgets/{target_stem}_widget.dart")
                candidates.append(f"lib/pages/{target_stem}_page.dart")
                candidates.append(f"lib/models/{target_stem}.dart")
                candidates.append(f"lib/services/{target_stem}_service.dart")
                candidates.append(f"lib/providers/{target_stem}_provider.dart")
            else:
                candidates.append(target)

        elif project_type == "python":
            if target_suffix == ".dart":
                candidates.append(f"src/{target_stem}.py")
                candidates.append(f"app/{target_stem}.py")
            else:
                candidates.append(target)

        elif project_type == "javascript":
            if target_suffix in (".py", ".dart"):
                candidates.append(f"src/{target_stem}.js")
                candidates.append(f"src/{target_stem}.ts")
                candidates.append(f"src/{target_stem}.jsx")
                candidates.append(f"src/{target_stem}.tsx")
                candidates.append(f"lib/{target_stem}.js")
                candidates.append(f"lib/{target_stem}.ts")
            else:
                candidates.append(target)

        else:
            candidates.append(target)

        return candidates

    def _find_similar_files(self, target: str, project_files: list[str]) -> list[str]:
        """Найти похожие файлы по имени с fuzzy matching и маппингом путей.

        Args:
            target: Целевой путь от LLM (например, "src/auth.py")
            project_files: Список реальных путей в проекте

        Returns:
            Список похожих путей (максимум 5)
        """
        project_type = self._detect_project_type(project_files)
        mapped_paths = self._map_path_to_project(target, project_type)

        matches: list[tuple[float, str]] = []
        seen_paths: set[str] = set()

        for mapped_path in mapped_paths:
            if mapped_path in project_files and mapped_path not in seen_paths:
                matches.append((1.0, mapped_path))
                seen_paths.add(mapped_path)

        target_stem = PurePosixPath(target).stem.lower()
        target_words = set(target_stem.replace("_", " ").replace("-", " ").split())
        target_words = {w for w in target_words if len(w) > 2}

        for file_path in project_files:
            if file_path in seen_paths:
                continue

            file_stem = PurePosixPath(file_path).stem.lower()

            if target_stem in file_stem or file_stem in target_stem:
                matches.append((0.9, file_path))
                seen_paths.add(file_path)
                continue

            file_words = set(file_stem.replace("_", " ").replace("-", " ").split())
            file_words = {w for w in file_words if len(w) > 2}

            common_words = target_words & file_words
            if common_words:
                score = 0.7 + 0.1 * len(common_words)
                matches.append((min(score, 0.89), file_path))
                seen_paths.add(file_path)
                continue

            ratio = SequenceMatcher(None, target_stem, file_stem).ratio()
            if ratio >= 0.6:
                matches.append((ratio * 0.7, file_path))
                seen_paths.add(file_path)

        path_segments = PurePosixPath(target).parts
        target_segment_words = set()
        for segment in path_segments:
            segment_stem = PurePosixPath(segment).stem.lower()
            target_segment_words.update(
                w for w in segment_stem.replace("_", " ").replace("-", " ").split()
                if len(w) > 2
            )

        for file_path in project_files:
            if file_path in seen_paths:
                continue

            file_lower = file_path.lower()
            segment_match_score = sum(
                1 for word in target_segment_words if word in file_lower
            )

            if segment_match_score >= 2:
                matches.append((0.5 + segment_match_score * 0.05, file_path))
                seen_paths.add(file_path)

        matches.sort(key=lambda x: x[0], reverse=True)
        return [path for _, path in matches[:5]]

    async def _search_in_files(
        self, term: str, project_files: list[str], session: Any
    ) -> list[str]:
        """Найти файлы по термину: сначала по пути, затем по содержимому.

        Args:
            term: Поисковый термин
            project_files: Список путей

        Returns:
            Список подходящих путей (максимум 10)
        """
        term_lower = term.lower()
        matches: list[str] = []

        for file_path in project_files:
            if term_lower in file_path.lower():
                matches.append(file_path)

        if len(matches) >= 3:
            return matches[:10]

        found_paths = set(matches)
        content_search_limit = 30
        files_to_check = [f for f in project_files if f not in found_paths]

        logger.info(
            "context.gather.content_search.start",
            session_id=self._session_id,
            term=term,
            path_matches=len(matches),
            files_to_check=min(len(files_to_check), content_search_limit),
        )

        for file_path in files_to_check[:content_search_limit]:
            if self._is_binary(file_path):
                continue

            content = await self._read_file(file_path, session)
            if content is None or self._is_empty(content):
                continue

            if term_lower in content.lower():
                matches.append(file_path)
                logger.info(
                    "context.gather.content_search.match",
                    session_id=self._session_id,
                    term=term,
                    file_path=file_path,
                )
                if len(matches) >= 10:
                    break

        return matches[:10]

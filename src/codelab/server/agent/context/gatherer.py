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
from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.agent.context.budget import DefaultTokenBudgetManager
from codelab.server.agent.context.file_matching import (
    deduplicate,
    filter_paths,
    find_similar_files,
    get_fallback_files,
    is_binary,
    is_empty,
    normalize_path,
    parse_find_output,
)
from codelab.server.agent.context.interfaces import ContextGatherer
from codelab.server.agent.context.models import (
    BuildOptions,
    ContextConfig,
    ContextItem,
    ContextType,
    TaskProfile,
)
from codelab.server.agent.contracts.ports import writable_session
from codelab.server.domain.value_objects import ToolInvocationSubject

if TYPE_CHECKING:
    from codelab.server.agent.context.dependency_graph import RegexDependencyGraph
    from codelab.server.observability.tracer import Tracer
    from codelab.server.tools.base import ToolRegistry

logger = structlog.get_logger(__name__)


class ACPContextGatherer(ContextGatherer):
    """Сборщик контекста через ACP ToolRegistry."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        dependency_graph: RegexDependencyGraph,
        session_id: str,
        tracer: Tracer | None = None,
        config: ContextConfig | None = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._dependency_graph = dependency_graph
        self._session_id = session_id
        self._tracer = tracer
        self._config = config or ContextConfig()
        self.last_candidate_count = 0

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
        project_files = await self._load_project_files(session)

        # Этапы 1-2: кандидаты из target_modules и поиска по search_terms
        candidates = await self._collect_candidates(profile, project_files, session)

        # Этап 3: Дедупликация кандидатов
        unique_candidates = deduplicate(candidates)
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
            fallback_files = get_fallback_files(project_files, max_files)
            unique_candidates = fallback_files
            logger.info(
                "context.gather.fallback_files",
                session_id=self._session_id,
                count=len(fallback_files),
                files=fallback_files[:10],
            )

        # Число уникальных кандидатов до отбора по бюджету (для /context last).
        self.last_candidate_count = len(unique_candidates)

        # Этап 4: Чтение файлов и построение графа зависимостей
        items = await self._read_candidate_files(unique_candidates, max_files, session)

        # Этап 5: Добавление зависимых файлов
        await self._add_dependent_files(items, max_files, session, profile)

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
            self._tracer.end_span(
                span,
                attributes={
                    "task_type": profile.task_type,
                    "search_terms": profile.search_terms,
                    "candidate_files": len(unique_candidates),
                    "selected_files": len(items),
                },
            )

        return items

    async def _load_project_files(self, session: Any) -> list[str]:
        """Стадия 0: структура проекта из кэша сессии (с bootstrap-fallback)."""
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
        return project_files

    async def _collect_candidates(
        self,
        profile: TaskProfile,
        project_files: list[str],
        session: Any,
    ) -> list[str]:
        """Стадии 1-2: кандидаты из target_modules и поиска по search_terms."""
        candidates: list[str] = []
        project_root = getattr(session, "cwd", None)

        if profile.target_modules:
            for module in profile.target_modules:
                # Нормализуем путь модуля
                normalized_module = normalize_path(module, project_root)

                # Проверяем существование файла в реальной структуре
                if normalized_module in project_files:
                    candidates.append(normalized_module)
                else:
                    # Fallback: ищем похожие файлы
                    similar = find_similar_files(normalized_module, project_files)
                    candidates.extend(similar)
                    logger.info(
                        "context.gather.target_module.fallback",
                        session_id=self._session_id,
                        original=module,
                        normalized=normalized_module,
                        found_count=len(similar),
                        found=similar[:5],
                    )

            logger.debug(
                "context.gather.target_modules_added",
                session_id=self._session_id,
                count=len(candidates),
                modules=candidates[:10],
            )

        # Поиск файлов по поисковым терминам в реальной структуре
        search_start = time.time()
        for term in profile.search_terms[:5]:
            term_start = time.time()
            search_results = await self._search_in_files(term, project_files, session)
            term_ms = (time.time() - term_start) * 1000

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
        return candidates

    async def _read_candidate_files(
        self,
        unique_candidates: list[str],
        max_files: int,
        session: Any,
    ) -> list[ContextItem]:
        """Стадия 4: чтение файлов, построение графа зависимостей, сборка items."""
        read_start = time.time()
        items: list[ContextItem] = []
        files_read = 0
        files_skipped_binary = 0
        files_skipped_empty = 0
        files_skipped_error = 0

        for path in unique_candidates[:max_files]:
            if is_binary(path):
                files_skipped_binary += 1
                logger.debug(
                    "context.gather.file.skipped_binary",
                    session_id=self._session_id,
                    path=path,
                )
                continue

            content = await self._read_file(path, session)

            if content is None:
                files_skipped_error += 1
                logger.debug(
                    "context.gather.file.read_failed",
                    session_id=self._session_id,
                    path=path,
                )
                continue

            if is_empty(content):
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

            if imports:
                logger.info(
                    "context.gather.file.imports_parsed",
                    session_id=self._session_id,
                    path=path,
                    imports_count=len(imports),
                    imports=imports[:10],
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
        return items

    async def _add_dependent_files(
        self,
        items: list[ContextItem],
        max_files: int,
        session: Any,
        profile: TaskProfile,
    ) -> None:
        """Стадия 5: добавить зависимые файлы (по графу) в items (мутирует список).

        При `recursive_dependencies=True` использует рекурсивный обход графа
        с ограничением глубины из `profile.investigation_depth`.
        """
        dependents_start = time.time()

        # Настройка глубины рекурсивного обхода из TaskProfile
        if self._config.recursive_dependencies:
            self._dependency_graph.set_max_depth(profile.investigation_depth)

        dependent_files = self._get_dependents(items, profile)

        logger.info(
            "context.gather.dependents.resolved",
            session_id=self._session_id,
            dependents_count=len(dependent_files),
            recursive_mode=self._config.recursive_dependencies,
            max_depth=profile.investigation_depth if self._config.recursive_dependencies else 0,
            source_files=len(items),
            graph_stats=self._dependency_graph.get_stats(),
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

            if is_binary(dep_path):
                continue

            content = await self._read_file(dep_path, session)
            if content is None or is_empty(content):
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

    async def _read_file(self, path: str, session: Any) -> str | None:
        """Прочитать файл через ToolRegistry."""
        try:
            result = await self._tool_registry.execute_tool(
                self._session_id,
                "fs/read_text_file",
                {"path": path},
                session=session,
                subject=ToolInvocationSubject.CONTEXT,
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

    def _get_dependents(self, items: list[ContextItem], profile: TaskProfile) -> list[str]:
        """Получить файлы, зависящие от загруженных.

        Всегда добавляет прямые зависимости (что файл импортирует).
        При `recursive_dependencies=True` добавляет транзитивные зависимости
        с ограничением глубины из `investigation_depth`.
        """
        dependents: set[str] = set()
        for item in items:
            # Reverse: файлы, которые импортируют данный файл
            reverse_deps = self._dependency_graph.get_dependents(item.id)
            dependents.update(reverse_deps)

            # Forward: прямые зависимости (что данный файл импортирует)
            direct_deps = self._dependency_graph.get_dependencies(item.id, recursive=False)
            dependents.update(direct_deps)

            # Forward recursive: транзитивные зависимости при включённом флаге
            if self._config.recursive_dependencies:
                transitive = self._dependency_graph.get_dependencies(item.id, recursive=True)
                dependents.update(transitive)

        return sorted(dependents)

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
        project_root = getattr(session, "cwd", None)

        if structure_json:
            try:
                raw_files = json.loads(structure_json)
                if isinstance(raw_files, list):
                    # Нормализуем все пути относительно корня проекта
                    normalized_files = [normalize_path(str(f), project_root) for f in raw_files]
                    filtered = filter_paths(normalized_files)
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
        """Получить структуру проекта, если она отсутствует в сессии.

        Перечисление запрашивается узкой возможностью `project/list_files`
        (ADR-009, раздел 6): сборщику контекста нужно перечислить файлы, а не
        исполнять команду, — поэтому команды он больше не формирует и права на
        неё не имеет. Терминал остался деталью реализации возможности.

        Args:
            session: Состояние сессии с config_values

        Returns:
            Список отфильтрованных путей к файлам проекта
        """
        try:
            result = await self._tool_registry.execute_tool(
                self._session_id,
                # Имя возможности литералом, как и остальные инструменты здесь:
                # пакет контекста не зависит от `server.tools` (направление слоёв).
                "project/list_files",
                {},
                session=session,
                subject=ToolInvocationSubject.CONTEXT,
            )

            if not result.success or not result.output:
                logger.debug(
                    "context.gather.bootstrap.list_files_failed",
                    session_id=self._session_id,
                    error=result.error,
                )
                return []

            raw_files = parse_find_output(result.output)
            project_root = getattr(session, "cwd", None)
            # Нормализуем пути относительно корня проекта
            normalized_files = [normalize_path(f, project_root) for f in raw_files]
            filtered = filter_paths(normalized_files)

            if filtered:
                self._dependency_graph.set_project_files(filtered)
                # Пишем в носитель состояния через seam (ADR-006). Порт `SessionView`
                # read-only, а сюда приходит именно он — поэтому носитель достаём
                # `writable_session`: иначе запись падала бы, а Context Manager молча
                # оставался без структуры проекта (найдено в проде после флипа).
                writable_session(session).set_config_value(
                    "project_structure", json.dumps(filtered)
                )

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
            if is_binary(file_path):
                continue

            content = await self._read_file(file_path, session)
            if content is None or is_empty(content):
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

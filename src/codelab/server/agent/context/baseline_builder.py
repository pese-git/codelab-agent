"""BaselineBuilder — анализ задачи и наполнение baseline-реестра.

Выделено из manager.py. Отвечает за этапы 2-4 сборки контекста:
- анализ задачи (TaskAnalyzer) и сохранение TaskProfile для /context;
- выбор/создание session-registry;
- наполнение реестра (system_prompt, сбор файлов, каталог скиллов).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.agent.context.gatherer import ACPContextGatherer
from codelab.server.agent.context.registry import (
    ContextRegistryImpl,
    FileContextSource,
    SkillCatalogSource,
)
from codelab.server.agent.context.task_analyzer import LLMBasedTaskAnalyzer

if TYPE_CHECKING:
    from codelab.server.agent.context.manager import _SessionContext
    from codelab.server.agent.context.models import BuildOptions, ContextConfig, TaskProfile
    from codelab.server.llm.base import LLMProvider
    from codelab.server.observability.metrics_tracker import MetricsTracker
    from codelab.server.observability.tracer import Tracer
    from codelab.server.tools.base import ToolRegistry

logger = structlog.get_logger(__name__)


@dataclass
class GatherStats:
    """Статистика этапа сбора файлов для baseline (метрики/трейсинг)."""

    files_count: int = 0
    file_paths: list[str] = field(default_factory=list)
    file_tokens: list[int] = field(default_factory=list)
    candidate_count: int = 0
    gather_ms: float = 0.0


class BaselineBuilder:
    """Анализирует задачу и наполняет baseline-реестр ContextManager."""

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry,
        config: ContextConfig,
        llm: LLMProvider | None,
        model: str,
        tracer: Tracer | None,
        metrics_tracker: MetricsTracker | None,
    ) -> None:
        self._tool_registry = tool_registry
        self._config = config
        self._llm = llm
        self._model = model
        self._tracer = tracer
        self._metrics_tracker = metrics_tracker

    def resolve_baseline_registry(
        self, ctx: _SessionContext, incremental: bool, session_id: Any
    ) -> ContextRegistryImpl:
        """Вернуть session-registry для переиспользования или создать новый."""
        if incremental and ctx.session_registry is not None:
            registry = ctx.session_registry
            logger.debug(
                "context.build.reusing_session_registry",
                session_id=session_id,
                sources_count=len(registry.list_sources()),
            )
            return registry

        registry = ContextRegistryImpl()
        if incremental:
            ctx.session_registry = registry
        return registry

    async def analyze_task(
        self, prompt_text: str, session: Any, session_id: Any
    ) -> tuple[TaskProfile, float]:
        """Этап 2: анализ задачи (TaskAnalyzer) + сохранение TaskProfile для /context.

        Returns:
            (profile, analyze_ms) — профиль задачи и время анализа в мс.
        """
        analyze_start = time.time()
        logger.debug(
            "context.build.task_analysis.start",
            session_id=session_id,
            llm_available=self._llm is not None,
            model=self._model,
        )

        analyzer = LLMBasedTaskAnalyzer(llm=self._llm, model=self._model)
        profile = await analyzer.analyze(prompt_text, session)
        analyze_ms = (time.time() - analyze_start) * 1000

        logger.info(
            "context.build.task_analysis.complete",
            session_id=session_id,
            task_type=profile.task_type,
            search_terms=profile.search_terms,
            target_modules=profile.target_modules,
            investigation_depth=profile.investigation_depth,
            needs_tests=profile.needs_tests,
            elapsed_ms=analyze_ms,
        )

        # Сохранить TaskProfile для /context profile
        if self._metrics_tracker is not None:
            session_metrics = self._metrics_tracker.get_or_create_metrics(str(session_id))
            session_metrics.last_task_profile = {
                "task_type": str(profile.task_type),
                "search_terms": list(profile.search_terms),
                "target_modules": list(profile.target_modules),
                "investigation_depth": profile.investigation_depth,
                "needs_tests": profile.needs_tests,
            }

        return profile, analyze_ms

    async def populate_baseline_registry(
        self,
        registry: ContextRegistryImpl,
        ctx: _SessionContext,
        profile: TaskProfile,
        session: Any,
        session_id: Any,
        *,
        system_prompt: str | None,
        options: BuildOptions | None,
        is_reusing_registry: bool,
    ) -> GatherStats:
        """Этапы 3-4: наполнить baseline-реестр (system_prompt, gather, skill catalog).

        При переиспользовании session-registry (incremental) регистрация
        пропускается. Возвращает статистику этапа сбора файлов.
        """
        stats = GatherStats()

        if is_reusing_registry:
            logger.debug(
                "context.build.skipping_registration.reusing_registry",
                session_id=session_id,
                sources_count=len(registry.list_sources()),
            )
            return stats

        if system_prompt:
            registry.register(FileContextSource("system_prompt", system_prompt))
            logger.debug(
                "context.build.baseline.system_prompt_added",
                session_id=session_id,
                system_prompt_length=len(system_prompt),
            )

        # Этап 4: Сбор файлов (если включено)
        if self._config.gather_enabled:
            gather_start = time.time()
            logger.info(
                "context.build.gather.start",
                session_id=session_id,
                max_files=options.max_files if options else None,
            )

            gatherer = ACPContextGatherer(
                tool_registry=self._tool_registry,
                dependency_graph=ctx.dependency_graph,
                session_id=session_id,
                tracer=self._tracer,
                config=self._config,
            )
            items = await gatherer.gather(profile, session, options=options)
            stats.files_count = len(items)
            stats.file_paths = [item.id for item in items]
            stats.file_tokens = [item.token_count for item in items]
            stats.candidate_count = gatherer.last_candidate_count
            stats.gather_ms = (time.time() - gather_start) * 1000

            logger.info(
                "context.build.gather.complete",
                session_id=session_id,
                files_gathered=stats.files_count,
                file_paths=[item.id for item in items[:10]],
                total_tokens=sum(item.token_count for item in items),
                elapsed_ms=stats.gather_ms,
            )

            for item in items:
                registry.register(FileContextSource(item.id, item.content))

            logger.debug(
                "context.build.baseline.files_registered",
                session_id=session_id,
                files_count=stats.files_count,
            )
        else:
            logger.debug(
                "context.build.gather.skipped",
                session_id=session_id,
                reason="gather_enabled=false",
            )

        # Регистрация каталога скиллов (пока пустой — SkillRegistry отсутствует)
        registry.register(SkillCatalogSource([]))
        return stats

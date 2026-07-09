"""ContextManager — единая точка входа для управления контекстом.

Оркестрирует компоненты слоя A:
- TaskAnalyzer — классификация задачи
- ContextGatherer — сбор релевантных файлов
- DependencyGraph — граф зависимостей
- TokenBudgetManager — управление бюджетом токенов

Реализует поведение гидрации (Phase 1): baseline пересобирается каждый ход.

Слой A — Сбор контекста (Phase 1).
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.agent.context.budget import DefaultTokenBudgetManager
from codelab.server.agent.context.compactor import ThreePhaseCompactor
from codelab.server.agent.context.dependency_graph import RegexDependencyGraph
from codelab.server.agent.context.epoch import EpochManager
from codelab.server.agent.context.file_cache import InvalidationSignalBus
from codelab.server.agent.context.gatherer import ACPContextGatherer
from codelab.server.agent.context.interfaces import (
    CodeSkeletonizer,
    ContextManager,
    ConversationSummarizer,
    TokenCounter,
)
from codelab.server.agent.context.models import (
    BuildOptions,
    ContextConfig,
    ContextItem,
    ContextType,
    PayloadEnvelope,
    SubagentResult,
)
from codelab.server.agent.context.reconciler import DefaultContextReconciler
from codelab.server.agent.context.registry import (
    ContextRegistryImpl,
    FileContextSource,
    SkillCatalogSource,
)
from codelab.server.agent.context.skeletonizer.composite import CompositeSkeletonizer
from codelab.server.agent.context.summarizer import LLMConversationSummarizer
from codelab.server.agent.context.task_analyzer import LLMBasedTaskAnalyzer
from codelab.server.agent.context.token_counter import create_token_counter
from codelab.server.agent.history_builder import HistoryBuilder
from codelab.server.agent.message_sanitizer import MessageSanitizer
from codelab.server.llm.models import LLMMessage

if TYPE_CHECKING:
    from codelab.server.llm.base import LLMProvider
    from codelab.server.observability.metrics_tracker import MetricsTracker
    from codelab.server.observability.tracer import Tracer
    from codelab.server.tools.base import ToolRegistry

logger = structlog.get_logger(__name__)


class _SessionContext:
    """Изолированное per-session состояние Context Manager.

    Раньше эти поля жили прямо на APP-scope синглтоне DefaultContextManager,
    что приводило к перекрёстному заражению контекста между сессиями
    (эпоха/реестр/граф одной сессии переиспользовались другой). Теперь
    состояние ключуется по session_id.
    """

    __slots__ = (
        "dependency_graph",
        "dirty_paths",
        "epoch_manager",
        "reconciler",
        "session_registry",
    )

    def __init__(self) -> None:
        self.dependency_graph = RegexDependencyGraph(Path.cwd())
        self.epoch_manager = EpochManager()
        self.reconciler = DefaultContextReconciler()
        self.session_registry: ContextRegistryImpl | None = None
        # Пути файлов, помеченных изменёнными сигналом инвалидации; рефрешатся
        # лениво в build_context (где доступны session/session_id).
        self.dirty_paths: set[str] = set()


class DefaultContextManager(ContextManager):
    """Контекст-менеджер с поддержкой гидрации и инкрементального режима.

    Phase 1-3 (гидрация): baseline пересобирается каждый ход.
    Phase 4 (инкрементальный): baseline фиксируется в ContextEpoch,
    отправляются только дельты при стабильном baseline.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        config: ContextConfig | None = None,
        llm: LLMProvider | None = None,
        model: str = "openai/gpt-4o-mini",
        metrics_tracker: MetricsTracker | None = None,
        tracer: Tracer | None = None,
        token_counter: TokenCounter | None = None,
        skeletonizer: CodeSkeletonizer | None = None,
        summarizer: ConversationSummarizer | None = None,
        signal_bus: InvalidationSignalBus | None = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._config = config or ContextConfig()
        self._llm = llm
        self._model = model
        self._budget_manager = DefaultTokenBudgetManager(self._config)
        self._history_builder = HistoryBuilder()
        self._metrics_tracker = metrics_tracker
        self._tracer = tracer
        self._token_counter = token_counter or create_token_counter()
        self._skeletonizer = skeletonizer or CompositeSkeletonizer()
        self._summarizer = summarizer
        self._compactor: ThreePhaseCompactor | None = None
        # Per-session состояние (эпоха/реестр/граф/reconciler) вместо
        # общих полей на APP-scope синглтоне — исключает смешивание сессий.
        self._sessions: dict[str, _SessionContext] = {}
        self._signal_bus = signal_bus or InvalidationSignalBus()
        self._signal_bus.subscribe(self._dispatch_file_invalidated)
        # Тайминги стадий tail/fingerprint последней сборки (для /context last).
        # Заполняются в _build_tail и _timed_fingerprint, сбрасываются в
        # начале build_context. Стадии живут внутри хелперов режима, поэтому
        # экспортируются через поля, а не как локальные переменные.
        self._last_tail_ms = 0.0
        self._last_fingerprint_ms = 0.0

    def _session_ctx(self, session_id: Any) -> _SessionContext:
        """Вернуть (создав при необходимости) изолированное состояние сессии."""
        key = str(session_id)
        ctx = self._sessions.get(key)
        if ctx is None:
            ctx = _SessionContext()
            self._sessions[key] = ctx
        return ctx

    def _dispatch_file_invalidated(self, path: str) -> None:
        """Маршрутизировать сигнал инвалидации во все активные сессии.

        Шина инвалидации — APP-scope, а reconciler/registry — per-session,
        поэтому сигнал доставляется каждому сессионному контексту. Само чтение
        файла НЕ выполняется здесь (нет session/event loop) — путь помечается
        «грязным» и перечитывается лениво в build_context.

        Args:
            path: Путь к изменённому файлу
        """
        for ctx in list(self._sessions.values()):
            ctx.reconciler.on_file_invalidated(path)
            if ctx.session_registry is not None and (
                ctx.session_registry.get_source(path) is not None
            ):
                ctx.dirty_paths.add(path)

    async def _refresh_dirty_sources(
        self, ctx: _SessionContext, session: Any, session_id: Any
    ) -> None:
        """Перечитать помеченные изменёнными файлы и обновить их источники.

        Вызывается в build_context перед reconcile: здесь доступны session и
        session_id, поэтому чтение идёт через реальный инструмент
        `fs/read_text_file` (не фейковый session_id). После обновления контента
        fingerprint источника меняется → reconcile корректно ломает эпоху.
        """
        if not ctx.dirty_paths or ctx.session_registry is None:
            return

        for path in sorted(ctx.dirty_paths):
            source = ctx.session_registry.get_source(path)
            if not isinstance(source, FileContextSource):
                continue
            content = await self._read_file(session, session_id, path)
            if content is not None:
                source.update_content(content)
                logger.debug(
                    "context.build.dirty_source_refreshed",
                    session_id=session_id,
                    path=path,
                    content_length=len(content),
                )
        ctx.dirty_paths.clear()

    async def _read_file(
        self, session: Any, session_id: Any, path: str
    ) -> str | None:
        """Прочитать файл через ToolRegistry (реальный инструмент)."""
        try:
            result = await self._tool_registry.execute_tool(
                session_id,
                "fs/read_text_file",
                {"path": path},
                session=session,
            )
            if result.success and result.output:
                return str(result.output)
        except Exception:
            logger.exception(
                "context.build.dirty_source_refresh_failed",
                session_id=session_id,
                path=path,
            )
        return None

    async def build_context(
        self,
        session: Any,
        prompt: list[dict],
        *,
        agent_scope: str = "single",
        system_prompt: str | None = None,
        options: BuildOptions | None = None,
    ) -> PayloadEnvelope:
        """Собрать payload для LLM-вызова.

        Поддерживает два режима:
        - incremental=false (гидрация): baseline пересобирается каждый ход
        - incremental=true (эпохи): baseline фиксирован, отправляются только дельты

        Args:
            session: Состояние сессии
            prompt: Промпт пользователя (список блоков)
            agent_scope: Область агента
            system_prompt: Системный промпт
            options: Опции сборки

        Returns:
            PayloadEnvelope с baseline и tail
        """
        start_time = time.time()
        session_id = getattr(session, "session_id", "unknown")
        ctx = self._session_ctx(session_id)

        # Укоренить граф зависимостей в директории проекта сессии, а не в cwd
        # процесса сервера (иначе разрешение импортов идёт не в той директории).
        session_cwd = getattr(session, "cwd", None)
        if session_cwd:
            ctx.dependency_graph.set_project_root(Path(session_cwd))

        span = None
        if self._tracer is not None:
            span = self._tracer.start_span(
                name="context.build",
                session_id=str(session_id),
            )

        incremental = self._resolve_incremental(options)

        logger.info(
            "context.build.start",
            session_id=session_id,
            agent_scope=agent_scope,
            has_system_prompt=system_prompt is not None,
            gather_enabled=self._config.gather_enabled,
            incremental=incremental,
        )

        # Этап 1: Извлечение текста из prompt
        extract_start = time.time()
        prompt_text = self._extract_prompt_text(prompt)
        extract_ms = (time.time() - extract_start) * 1000

        logger.debug(
            "context.build.prompt_extracted",
            session_id=session_id,
            prompt_length=len(prompt_text),
            prompt_preview=prompt_text[:100] if prompt_text else "",
            elapsed_ms=extract_ms,
        )

        # Этап 2: Анализ задачи (TaskAnalyzer)
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

        # Этап 3: Формирование baseline через ContextRegistry
        # Сброс таймингов tail/fingerprint — заполнятся внутри хелперов режима.
        self._last_tail_ms = 0.0
        self._last_fingerprint_ms = 0.0
        baseline_start = time.time()

        if incremental and ctx.session_registry is not None:
            registry = ctx.session_registry
            logger.debug(
                "context.build.reusing_session_registry",
                session_id=session_id,
                sources_count=len(registry.list_sources()),
            )
        else:
            registry = ContextRegistryImpl()
            if incremental:
                ctx.session_registry = registry

        gathered_files_count = 0
        gather_ms = 0.0
        gathered_file_paths: list[str] = []
        gathered_file_tokens: list[int] = []
        candidate_count = 0

        is_reusing_registry = (
            incremental
            and ctx.session_registry is not None
            and len(ctx.session_registry.list_sources()) > 0
        )

        if not is_reusing_registry:
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
                )
                items = await gatherer.gather(profile, session, options=options)
                gathered_files_count = len(items)
                gathered_file_paths = [item.id for item in items]
                gathered_file_tokens = [item.token_count for item in items]
                candidate_count = gatherer.last_candidate_count
                gather_ms = (time.time() - gather_start) * 1000

                logger.info(
                    "context.build.gather.complete",
                    session_id=session_id,
                    files_gathered=gathered_files_count,
                    file_paths=[item.id for item in items[:10]],
                    total_tokens=sum(item.token_count for item in items),
                    elapsed_ms=gather_ms,
                )

                for item in items:
                    registry.register(FileContextSource(item.id, item.content))

                logger.debug(
                    "context.build.baseline.files_registered",
                    session_id=session_id,
                    files_count=gathered_files_count,
                )
            else:
                logger.debug(
                    "context.build.gather.skipped",
                    session_id=session_id,
                    reason="gather_enabled=false",
                )

            # Регистрация каталога скиллов (пока пустой — SkillRegistry отсутствует)
            registry.register(SkillCatalogSource([]))
        else:
            logger.debug(
                "context.build.skipping_registration.reusing_registry",
                session_id=session_id,
                sources_count=len(registry.list_sources()),
            )

        # Выбор режима: инкрементальный или гидрация
        if incremental:
            # Ленивый рефреш изменённых файлов до reconcile: обновляет контент
            # источников, чтобы fingerprint отразил изменение и эпоха корректно
            # перестроилась со свежим содержимым (4.D2).
            await self._refresh_dirty_sources(ctx, session, session_id)
            baseline, baseline_fingerprint, tail, reconcile_info = (
                await self._build_incremental(session, ctx, registry, prompt, session_id)
            )
        else:
            baseline, baseline_fingerprint, tail, reconcile_info = (
                await self._build_hydration(session, registry, prompt, session_id)
            )

        baseline_ms = (time.time() - baseline_start) * 1000
        logger.debug(
            "context.build.baseline.complete",
            session_id=session_id,
            baseline_messages=len(baseline),
            mode="incremental" if incremental else "hydration",
            elapsed_ms=baseline_ms,
        )

        # Оценка токенов
        token_count = self._estimate_total_tokens(baseline, tail)

        elapsed_ms = (time.time() - start_time) * 1000
        baseline_tokens = self._estimate_total_tokens(baseline, [])
        tail_tokens = self._estimate_total_tokens([], tail)

        logger.info(
            "context.build.complete",
            session_id=session_id,
            baseline_messages=len(baseline),
            tail_messages=len(tail),
            token_count=token_count,
            baseline_fingerprint=baseline_fingerprint,
            mode="incremental" if incremental else "hydration",
            epoch_broken=reconcile_info.get("epoch_broken", False),
            reconcile_state=reconcile_info.get("state", "n/a"),
            total_elapsed_ms=elapsed_ms,
        )

        if span is not None and self._tracer is not None:
            self._tracer.end_span(span, attributes={
                "agent_scope": agent_scope,
                "task_type": profile.task_type,
                "gathered_files": gathered_files_count,
                "baseline_tokens": baseline_tokens,
                "tail_tokens": tail_tokens,
                "incremental": incremental,
                "epoch_broken": reconcile_info.get("epoch_broken", False),
            })

        if self._metrics_tracker is not None:
            stage_timings = {
                "extract_ms": extract_ms,
                "analyze_ms": analyze_ms,
                "gather_ms": gather_ms,
                "baseline_ms": baseline_ms,
                "tail_ms": self._last_tail_ms,
                "fingerprint_ms": self._last_fingerprint_ms,
            }
            self._metrics_tracker.record_context_build(
                build_duration_ms=elapsed_ms,
                gathered_files=gathered_files_count,
                baseline_tokens=baseline_tokens,
                tail_tokens=tail_tokens,
                session_id=str(session_id),
                task_type=str(profile.task_type),
                file_paths=gathered_file_paths,
                file_tokens=gathered_file_tokens,
                candidate_count=candidate_count,
                stage_timings=stage_timings,
                graph_stats=ctx.dependency_graph.get_stats(),
                fingerprint=baseline_fingerprint,
            )
            if incremental:
                self._metrics_tracker.record_context_reconcile(
                    state=reconcile_info.get("state", "unknown"),
                    epoch_broken=reconcile_info.get("epoch_broken", False),
                    changed_sources=reconcile_info.get("changed_sources", []),
                    session_id=str(session_id),
                )

        return PayloadEnvelope(
            baseline=baseline,
            tail=tail,
            baseline_fingerprint=baseline_fingerprint,
            token_count=token_count,
        )

    async def ensure_context_fits(
        self,
        envelope: PayloadEnvelope,
        *,
        max_context_tokens: int,
        reserved_tokens: int,
    ) -> PayloadEnvelope:
        """Гарантировать, что payload помещается в окно.

        Phase 3: использует ThreePhaseCompactor для 3-фазного сжатия.
        Использует safety margin 0.9 для компенсации недооценки ApproximateTokenCounter.
        """
        safety_margin = 0.9
        available = int((max_context_tokens - reserved_tokens) * safety_margin)

        logger.debug(
            "context.ensure_fits.check",
            current_tokens=envelope.token_count,
            max_context_tokens=max_context_tokens,
            reserved_tokens=reserved_tokens,
            available_tokens=available,
            safety_margin=safety_margin,
            fits=envelope.token_count <= available,
        )

        if envelope.token_count <= available:
            logger.info(
                "context.ensure_fits.ok",
                token_count=envelope.token_count,
                available=available,
                margin=available - envelope.token_count,
            )
            return envelope

        logger.warning(
            "context.ensure_fits.exceeded",
            current=envelope.token_count,
            available=available,
            exceeded_by=envelope.token_count - available,
            action="compaction_needed",
        )

        compactor = self._get_or_create_compactor()
        compacted = await compactor.compact_if_needed(
            envelope.to_messages(),
            max_context_tokens=max_context_tokens,
            reserved_tokens=reserved_tokens,
        )
        new_token_count = self._token_counter.count_messages(compacted)

        # Пост-проверка: компактор сжимает до (max - reserved) без safety
        # margin, а ApproximateTokenCounter может недооценивать. Если результат
        # всё ещё выше строгого порога `available` (0.9), повторяем сжатие с
        # более строгим лимитом — гарантия требования спеки
        # "ensure_context_fits гарантирует бюджет" (context-compaction).
        if new_token_count > available:
            logger.warning(
                "context.ensure_fits.budget_underestimated_retry",
                tokens_after=new_token_count,
                target=available,
                exceeded_by=new_token_count - available,
            )
            compacted = await compactor.compact_if_needed(
                compacted,
                max_context_tokens=available,
                reserved_tokens=0,
            )
            new_token_count = self._token_counter.count_messages(compacted)

        baseline, tail = self._split_baseline_tail(compacted)
        baseline_fingerprint = self._compute_fingerprint(baseline)

        logger.info(
            "context.ensure_fits.compacted",
            tokens_before=envelope.token_count,
            tokens_after=new_token_count,
            baseline_messages=len(baseline),
            tail_messages=len(tail),
        )

        return PayloadEnvelope(
            baseline=baseline,
            tail=tail,
            baseline_fingerprint=baseline_fingerprint,
            token_count=new_token_count,
        )

    @staticmethod
    def _split_baseline_tail(
        messages: list[LLMMessage],
    ) -> tuple[list[LLMMessage], list[LLMMessage]]:
        """Разделить плоский список на baseline (ведущие system) и tail."""
        baseline: list[LLMMessage] = []
        tail: list[LLMMessage] = []
        for msg in messages:
            if msg.role == "system" and not tail:
                baseline.append(msg)
            else:
                tail.append(msg)
        return baseline, tail

    def _get_or_create_compactor(self) -> ThreePhaseCompactor:
        """Получить или создать ThreePhaseCompactor."""
        if self._compactor is None:
            summarizer = self._summarizer
            if summarizer is None and self._llm is not None:
                summarizer = LLMConversationSummarizer(
                    llm=self._llm,
                    model=self._model,
                    token_counter=self._token_counter,
                )

            self._compactor = ThreePhaseCompactor(
                token_counter=self._token_counter,
                skeletonizer=self._skeletonizer,
                summarizer=summarizer,
                sanitizer=MessageSanitizer(),
                config=self._config,
                metrics_tracker=self._metrics_tracker,
                tracer=self._tracer,
            )
        return self._compactor

    async def process_subagent_response(
        self,
        parent_scope: str,
        subagent_scope: str,
        response: Any,
    ) -> SubagentResult:
        """Обработать ответ субагента для родителя.

        Phase 1: заглушка, полная реализация в Phase 6.

        Args:
            parent_scope: Область родителя
            subagent_scope: Область субагента
            response: Ответ субагента

        Returns:
            SubagentResult с summary
        """
        logger.info(
            "context.subagent.process.start",
            parent_scope=parent_scope,
            subagent_scope=subagent_scope,
            response_type=type(response).__name__ if response else None,
        )

        summary = f"[Subagent {subagent_scope} response placeholder]"

        result = SubagentResult(
            summary=summary,
            token_count=0,
            source_scope=subagent_scope,
            shared_items=[],
        )

        logger.info(
            "context.subagent.process.complete",
            parent_scope=parent_scope,
            subagent_scope=subagent_scope,
            summary_length=len(summary),
            token_count=result.token_count,
            shared_items_count=len(result.shared_items),
        )

        return result

    def _resolve_incremental(self, options: BuildOptions | None) -> bool:
        """Определить режим сборки: инкрементальный или гидрация.

        Приоритет: BuildOptions.incremental → ContextConfig.incremental.

        Args:
            options: Per-call опции (может быть None)

        Returns:
            True для инкрементального режима
        """
        if options is not None and options.incremental is not None:
            return options.incremental
        return self._config.incremental

    def _build_tail(self, session: Any, prompt: list[dict]) -> list[LLMMessage]:
        """Собрать tail из истории сессии (источник истины) — 4.D1.

        session.history уже содержит текущий промпт (добавлен обработчиком до
        пайплайна). System-сообщения принадлежат baseline и исключаются.
        Fallback на prompt — только если history не list (не настоящая сессия).
        """
        tail_start = time.time()
        history = getattr(session, "history", None)
        if not isinstance(history, list):
            result = self._tail_from_prompt(prompt)
        else:
            messages = self._history_builder.build(history)
            result = [m for m in messages if m.role != "system"]
        self._last_tail_ms = (time.time() - tail_start) * 1000
        return result

    def _timed_fingerprint(self, messages: list[LLMMessage]) -> str:
        """Вычислить fingerprint baseline с замером длительности (/context last)."""
        fp_start = time.time()
        fingerprint = EpochManager.compute_baseline_fingerprint(messages)
        self._last_fingerprint_ms = (time.time() - fp_start) * 1000
        return fingerprint

    @staticmethod
    def _tail_from_prompt(prompt: list[dict]) -> list[LLMMessage]:
        """Fallback: собрать tail из prompt-блоков (нет истории сессии)."""
        tail: list[LLMMessage] = []
        for block in prompt:
            if block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    tail.append(LLMMessage(role="user", content=text))
        return tail

    async def _build_hydration(
        self,
        session: Any,
        registry: ContextRegistryImpl,
        prompt: list[dict],
        session_id: Any,
    ) -> tuple[list[LLMMessage], str, list[LLMMessage], dict[str, Any]]:
        """Режим гидрации: baseline пересобирается каждый ход.

        Returns:
            (baseline, baseline_fingerprint, tail, reconcile_info)
        """
        baseline_text = await registry.render_baseline()
        baseline: list[LLMMessage] = []
        if baseline_text:
            baseline.append(LLMMessage(role="system", content=baseline_text))

        baseline_fingerprint = self._timed_fingerprint(baseline)

        tail = self._build_tail(session, prompt)

        reconcile_info: dict[str, Any] = {"state": "hydration", "epoch_broken": False}

        logger.debug(
            "context.build.hydration",
            session_id=session_id,
            baseline_messages=len(baseline),
            tail_messages=len(tail),
        )

        return baseline, baseline_fingerprint, tail, reconcile_info

    async def _build_incremental(
        self,
        session: Any,
        ctx: _SessionContext,
        registry: ContextRegistryImpl,
        prompt: list[dict],
        session_id: Any,
    ) -> tuple[list[LLMMessage], str, list[LLMMessage], dict[str, Any]]:
        """Инкрементальный режим: baseline из эпохи, только дельты в tail.

        Returns:
            (baseline, baseline_fingerprint, tail, reconcile_info)
        """
        ctx.epoch_manager.reset_turn_counter()

        tail = self._build_tail(session, prompt)

        if not ctx.epoch_manager.is_active:
            return await self._start_new_epoch(ctx, registry, tail, session_id)

        epoch = ctx.epoch_manager.current_epoch
        assert epoch is not None

        reconcile_result = await ctx.reconciler.reconcile(
            epoch,
            registry,
        )

        reconcile_info: dict[str, Any] = {
            "state": reconcile_result.state.value,
            "epoch_broken": reconcile_result.epoch_broken,
            "changed_sources": reconcile_result.updated_sources,
        }

        if reconcile_result.epoch_broken:
            new_baseline_text = await registry.render_baseline()
            new_baseline: list[LLMMessage] = []
            if new_baseline_text:
                new_baseline.append(LLMMessage(role="system", content=new_baseline_text))

            new_fingerprint = self._timed_fingerprint(new_baseline)
            ctx.epoch_manager.break_epoch(new_baseline, new_fingerprint)

            logger.info(
                "context.build.incremental.epoch_broken",
                session_id=session_id,
                changed_sources=reconcile_result.updated_sources,
            )

            return new_baseline, new_fingerprint, tail, reconcile_info

        if reconcile_result.state.value == "updated" and reconcile_result.new_tail_messages:
            tail = [*reconcile_result.new_tail_messages, *tail]

        epoch = ctx.epoch_manager.current_epoch
        assert epoch is not None
        baseline = list(epoch.baseline)
        baseline_fingerprint = epoch.baseline_fingerprint

        logger.debug(
            "context.build.incremental.stable",
            session_id=session_id,
            epoch_id=epoch.epoch_id,
            baseline_fingerprint=baseline_fingerprint,
            reconcile_state=reconcile_result.state.value,
        )

        return baseline, baseline_fingerprint, tail, reconcile_info

    async def _start_new_epoch(
        self,
        ctx: _SessionContext,
        registry: ContextRegistryImpl,
        tail: list[LLMMessage],
        session_id: Any,
    ) -> tuple[list[LLMMessage], str, list[LLMMessage], dict[str, Any]]:
        """Создать новую эпоху с текущим baseline.

        Returns:
            (baseline, baseline_fingerprint, tail, reconcile_info)
        """
        baseline_text = await registry.render_baseline()
        baseline: list[LLMMessage] = []
        if baseline_text:
            baseline.append(LLMMessage(role="system", content=baseline_text))

        baseline_fingerprint = self._timed_fingerprint(baseline)
        ctx.epoch_manager.start_epoch(baseline, baseline_fingerprint)
        await ctx.reconciler.snapshot(registry)

        reconcile_info: dict[str, Any] = {
            "state": "new_epoch",
            "epoch_broken": False,
            "changed_sources": [],
        }

        logger.info(
            "context.build.incremental.new_epoch",
            session_id=session_id,
            epoch_id=(
                ctx.epoch_manager.current_epoch.epoch_id
                if ctx.epoch_manager.current_epoch
                else None
            ),
            baseline_fingerprint=baseline_fingerprint,
        )

        return baseline, baseline_fingerprint, tail, reconcile_info

    @staticmethod
    def _extract_prompt_text(prompt: list[dict]) -> str:
        """Извлечь текст из prompt блоков."""
        parts: list[str] = []
        for block in prompt:
            if block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    parts.append(text)
        return " ".join(parts)

    @staticmethod
    def _format_context_items(items: list[ContextItem]) -> str:
        """Форматировать ContextItem в текст для system prompt."""
        if not items:
            return ""

        sections: list[str] = ["<context>"]
        for item in items:
            if item.type == ContextType.FILE_CONTENT:
                sections.append(f"<file path=\"{item.id}\">")
                sections.append(item.content)
                sections.append("</file>")

        sections.append("</context>")
        return "\n".join(sections)

    @staticmethod
    def _compute_fingerprint(messages: list[LLMMessage]) -> str:
        """Вычислить fingerprint для baseline."""
        content_parts: list[str] = []
        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            content_parts.append(f"{msg.role}:{content}")

        combined = "|".join(content_parts)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def _estimate_total_tokens(
        self,
        baseline: list[LLMMessage],
        tail: list[LLMMessage],
    ) -> int:
        """Оценить общее количество токенов."""
        total = 0
        for msg in baseline + tail:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            total += DefaultTokenBudgetManager.estimate_tokens(content)
        return total

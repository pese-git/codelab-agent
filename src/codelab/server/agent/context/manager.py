"""ContextManager — единая точка входа для управления контекстом.

Оркестрирует компоненты слоя A через коллабораторов:
- BaselineBuilder — анализ задачи (TaskAnalyzer) и наполнение baseline-реестра
- EnvelopeAssembler — сборка baseline/tail (гидрация и инкрементальный режим)
- manager_helpers — чистые функции (fingerprint, токены, split, извлечение текста)

Реализует поведение гидрации (Phase 1): baseline пересобирается каждый ход.

Слой A — Сбор контекста (Phase 1).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.agent.context.baseline_builder import BaselineBuilder
from codelab.server.agent.context.budget import DefaultTokenBudgetManager
from codelab.server.agent.context.compactor import ThreePhaseCompactor
from codelab.server.agent.context.dependency_graph import RegexDependencyGraph
from codelab.server.agent.context.envelope_assembler import EnvelopeAssembler
from codelab.server.agent.context.epoch import EpochManager
from codelab.server.agent.context.file_cache import InvalidationSignalBus
from codelab.server.agent.context.interfaces import (
    CodeSkeletonizer,
    ContextManager,
    ConversationSummarizer,
    TokenCounter,
)
from codelab.server.agent.context.manager_helpers import (
    compute_fingerprint,
    estimate_total_tokens,
    extract_prompt_text,
    split_baseline_tail,
)
from codelab.server.agent.context.models import (
    BuildOptions,
    ContextConfig,
    PayloadEnvelope,
    SubagentResult,
)
from codelab.server.agent.context.reconciler import DefaultContextReconciler
from codelab.server.agent.context.registry import (
    ContextRegistryImpl,
    FileContextSource,
)
from codelab.server.agent.context.skeletonizer.composite import CompositeSkeletonizer
from codelab.server.agent.context.summarizer import LLMConversationSummarizer
from codelab.server.agent.context.token_counter import create_token_counter
from codelab.server.agent.history_builder import HistoryBuilder
from codelab.server.agent.message_sanitizer import MessageSanitizer

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
        # Коллаборы сборки контекста.
        self._baseline_builder = BaselineBuilder(
            tool_registry=self._tool_registry,
            config=self._config,
            llm=self._llm,
            model=self._model,
            tracer=self._tracer,
            metrics_tracker=self._metrics_tracker,
        )
        self._envelope_assembler = EnvelopeAssembler(self._history_builder)

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

    async def _read_file(self, session: Any, session_id: Any, path: str) -> str | None:
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
        session_id = getattr(session, "session_id", None) or str(getattr(session, "id", "unknown"))
        ctx = self._session_ctx(session_id)

        # Укоренить граф зависимостей в директории проекта сессии, а не в cwd
        # процесса сервера (иначе разрешение импортов идёт не в той директории).
        session_cwd = (
            getattr(session, "cwd", None)
            or getattr(getattr(session, "config", None), "cwd", None)
        )
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
        prompt_text = extract_prompt_text(prompt)
        extract_ms = (time.time() - extract_start) * 1000

        logger.debug(
            "context.build.prompt_extracted",
            session_id=session_id,
            prompt_length=len(prompt_text),
            prompt_preview=prompt_text[:100] if prompt_text else "",
            elapsed_ms=extract_ms,
        )

        # Этап 2: Анализ задачи (TaskAnalyzer)
        profile, analyze_ms = await self._baseline_builder.analyze_task(
            prompt_text, session, session_id
        )

        # Этап 3: Формирование baseline через ContextRegistry
        baseline_start = time.time()

        registry = self._baseline_builder.resolve_baseline_registry(ctx, incremental, session_id)

        is_reusing_registry = (
            incremental
            and ctx.session_registry is not None
            and len(ctx.session_registry.list_sources()) > 0
        )

        gather_stats = await self._baseline_builder.populate_baseline_registry(
            registry,
            ctx,
            profile,
            session,
            session_id,
            system_prompt=system_prompt,
            options=options,
            is_reusing_registry=is_reusing_registry,
        )

        # Выбор режима: инкрементальный или гидрация
        if incremental:
            # Ленивый рефреш изменённых файлов до reconcile: обновляет контент
            # источников, чтобы fingerprint отразил изменение и эпоха корректно
            # перестроилась со свежим содержимым (4.D2).
            await self._refresh_dirty_sources(ctx, session, session_id)
            assembled = await self._envelope_assembler.build_incremental(
                session, ctx, registry, prompt, session_id
            )
        else:
            assembled = await self._envelope_assembler.build_hydration(
                session, registry, prompt, session_id
            )

        baseline = assembled.baseline
        baseline_fingerprint = assembled.baseline_fingerprint
        tail = assembled.tail
        reconcile_info = assembled.reconcile_info

        baseline_ms = (time.time() - baseline_start) * 1000
        logger.debug(
            "context.build.baseline.complete",
            session_id=session_id,
            baseline_messages=len(baseline),
            mode="incremental" if incremental else "hydration",
            elapsed_ms=baseline_ms,
        )

        # Оценка токенов
        token_count = estimate_total_tokens(baseline, tail)

        elapsed_ms = (time.time() - start_time) * 1000
        baseline_tokens = estimate_total_tokens(baseline, [])
        tail_tokens = estimate_total_tokens([], tail)

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
            self._tracer.end_span(
                span,
                attributes={
                    "agent_scope": agent_scope,
                    "task_type": profile.task_type,
                    "gathered_files": gather_stats.files_count,
                    "baseline_tokens": baseline_tokens,
                    "tail_tokens": tail_tokens,
                    "incremental": incremental,
                    "epoch_broken": reconcile_info.get("epoch_broken", False),
                },
            )

        if self._metrics_tracker is not None:
            stage_timings = {
                "extract_ms": extract_ms,
                "analyze_ms": analyze_ms,
                "gather_ms": gather_stats.gather_ms,
                "baseline_ms": baseline_ms,
                "tail_ms": assembled.tail_ms,
                "fingerprint_ms": assembled.fingerprint_ms,
            }
            self._metrics_tracker.record_context_build(
                build_duration_ms=elapsed_ms,
                gathered_files=gather_stats.files_count,
                baseline_tokens=baseline_tokens,
                tail_tokens=tail_tokens,
                session_id=str(session_id),
                task_type=str(profile.task_type),
                file_paths=gather_stats.file_paths,
                file_tokens=gather_stats.file_tokens,
                candidate_count=gather_stats.candidate_count,
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

        baseline, tail = split_baseline_tail(compacted)
        baseline_fingerprint = compute_fingerprint(baseline)

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

        Phase 6: суммаризирует ответ субагента через ConversationSummarizer.
        Родитель получает только summary (изоляция), shared_items пуст (без федерации).

        Args:
            parent_scope: Область родителя
            subagent_scope: Область субагента
            response: Ответ субагента (строка или список сообщений)

        Returns:
            SubagentResult с summary для родителя
        """
        logger.info(
            "context.subagent.process.start",
            parent_scope=parent_scope,
            subagent_scope=subagent_scope,
            response_type=type(response).__name__ if response else None,
        )

        # Если ответ пустой — возвращаем пустой summary
        if not response:
            result = SubagentResult(
                summary="(субагент не выполнил действий)",
                token_count=0,
                source_scope=subagent_scope,
                shared_items=[],
            )
            logger.info(
                "context.subagent.process.complete",
                parent_scope=parent_scope,
                subagent_scope=subagent_scope,
                summary_length=len(result.summary),
                token_count=result.token_count,
            )
            return result

        # Конвертируем ответ в строку для суммаризации
        # Поддерживаем: str, list[LLMMessage], dict с "content"
        if isinstance(response, str):
            response_text = response
        elif isinstance(response, dict):
            response_text = response.get("content", str(response))
        elif isinstance(response, list):
            # list[LLMMessage] — суммаризируем напрямую
            if self._summarizer is not None:
                try:
                    target_tokens = min(len(response) * 100, 2000)
                    summary_message = await self._summarizer.summarize(
                        response, target_tokens=target_tokens
                    )
                    # Извлекаем текст из LLMMessage
                    if hasattr(summary_message, "content"):
                        content = summary_message.content
                        if isinstance(content, str):
                            summary_text = content
                        elif isinstance(content, list):
                            summary_text = " ".join(
                                part.text if hasattr(part, "text") else str(part)
                                for part in content
                            )
                        else:
                            summary_text = str(content)
                    else:
                        summary_text = str(summary_message)
                    summary_tokens = self._token_counter.count_messages([summary_message])

                    result = SubagentResult(
                        summary=summary_text,
                        token_count=summary_tokens,
                        source_scope=subagent_scope,
                        shared_items=[],
                    )

                    logger.info(
                        "context.subagent.process.complete",
                        parent_scope=parent_scope,
                        subagent_scope=subagent_scope,
                        summary_length=len(summary_text),
                        token_count=summary_tokens,
                        history_messages=len(response),
                    )

                    return result
                except Exception:
                    logger.exception(
                        "context.subagent.process.summarize_failed",
                        subagent_scope=subagent_scope,
                    )
            response_text = str(response)
        else:
            response_text = str(response)

        # Fallback: если суммаризатор недоступен или не смог обработать
        summary_text = response_text[:500] if len(response_text) > 500 else response_text
        summary_tokens = self._token_counter.count(summary_text)

        result = SubagentResult(
            summary=summary_text,
            token_count=summary_tokens,
            source_scope=subagent_scope,
            shared_items=[],
        )

        logger.info(
            "context.subagent.process.complete",
            parent_scope=parent_scope,
            subagent_scope=subagent_scope,
            summary_length=len(summary_text),
            token_count=result.token_count,
            fallback=True,
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

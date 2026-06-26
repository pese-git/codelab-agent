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
from codelab.server.agent.context.dependency_graph import RegexDependencyGraph
from codelab.server.agent.context.gatherer import ACPContextGatherer
from codelab.server.agent.context.interfaces import ContextManager
from codelab.server.agent.context.models import (
    BuildOptions,
    ContextConfig,
    ContextItem,
    ContextType,
    PayloadEnvelope,
    SubagentResult,
)
from codelab.server.agent.context.task_analyzer import LLMBasedTaskAnalyzer
from codelab.server.llm.models import LLMMessage

if TYPE_CHECKING:
    from codelab.server.llm.base import LLMProvider
    from codelab.server.observability.metrics_tracker import MetricsTracker
    from codelab.server.observability.tracer import Tracer
    from codelab.server.tools.base import ToolRegistry

logger = structlog.get_logger(__name__)


class DefaultContextManager(ContextManager):
    """Контекст-менеджер с гидратацией (Phase 1)."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        config: ContextConfig | None = None,
        llm: LLMProvider | None = None,
        model: str = "openai/gpt-4o-mini",
        metrics_tracker: MetricsTracker | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._config = config or ContextConfig()
        self._llm = llm
        self._model = model
        self._budget_manager = DefaultTokenBudgetManager(self._config)
        self._dependency_graph = RegexDependencyGraph(Path.cwd())
        self._metrics_tracker = metrics_tracker
        self._tracer = tracer

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

        Phase 1 (гидрация): baseline пересобирается каждый ход.

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

        span = None
        if self._tracer is not None:
            span = self._tracer.start_span(
                name="context.build",
                session_id=str(session_id),
            )

        logger.info(
            "context.build.start",
            session_id=session_id,
            agent_scope=agent_scope,
            has_system_prompt=system_prompt is not None,
            gather_enabled=self._config.gather_enabled,
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

        # Этап 3: Формирование baseline
        baseline_start = time.time()
        baseline: list[LLMMessage] = []

        if system_prompt:
            baseline.append(LLMMessage(role="system", content=system_prompt))
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
                dependency_graph=self._dependency_graph,
                session_id=session_id,
                tracer=self._tracer,
            )
            items = await gatherer.gather(profile, session, options=options)
            gather_ms = (time.time() - gather_start) * 1000

            logger.info(
                "context.build.gather.complete",
                session_id=session_id,
                files_gathered=len(items),
                file_paths=[item.id for item in items[:10]],  # Первые 10 файлов
                total_tokens=sum(item.token_count for item in items),
                elapsed_ms=gather_ms,
            )

            context_content = self._format_context_items(items)
            if context_content:
                baseline.append(
                    LLMMessage(role="system", content=context_content)
                )
                logger.debug(
                    "context.build.baseline.context_added",
                    session_id=session_id,
                    context_length=len(context_content),
                    context_preview=(
                        context_content[:200] + "..."
                        if len(context_content) > 200
                        else context_content
                    ),
                )
        else:
            logger.debug(
                "context.build.gather.skipped",
                session_id=session_id,
                reason="gather_enabled=false",
            )

        baseline_ms = (time.time() - baseline_start) * 1000
        logger.debug(
            "context.build.baseline.complete",
            session_id=session_id,
            baseline_messages=len(baseline),
            elapsed_ms=baseline_ms,
        )

        # Этап 5: Формирование tail
        tail_start = time.time()
        tail: list[LLMMessage] = []
        for block in prompt:
            if block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    tail.append(LLMMessage(role="user", content=text))

        tail_ms = (time.time() - tail_start) * 1000
        logger.debug(
            "context.build.tail.complete",
            session_id=session_id,
            tail_messages=len(tail),
            elapsed_ms=tail_ms,
        )

        # Этап 6: Вычисление fingerprint
        fingerprint_start = time.time()
        baseline_fingerprint = self._compute_fingerprint(baseline)
        fingerprint_ms = (time.time() - fingerprint_start) * 1000
        
        logger.debug(
            "context.build.fingerprint.computed",
            session_id=session_id,
            fingerprint=baseline_fingerprint,
            elapsed_ms=fingerprint_ms,
        )

        # Этап 7: Оценка токенов
        token_count = self._estimate_total_tokens(baseline, tail)
        
        logger.debug(
            "context.build.tokens.estimated",
            session_id=session_id,
            baseline_tokens=self._estimate_total_tokens(baseline, []),
            tail_tokens=self._estimate_total_tokens([], tail),
            total_tokens=token_count,
        )

        elapsed_ms = (time.time() - start_time) * 1000
        baseline_tokens = self._estimate_total_tokens(baseline, [])
        tail_tokens = self._estimate_total_tokens([], tail)
        gathered_files_count = sum(
            1 for msg in baseline
            if msg.role == "system" and "<context>" in (msg.content or "")
        )

        logger.info(
            "context.build.complete",
            session_id=session_id,
            baseline_messages=len(baseline),
            tail_messages=len(tail),
            token_count=token_count,
            baseline_fingerprint=baseline_fingerprint,
            total_elapsed_ms=elapsed_ms,
        )

        if span is not None and self._tracer is not None:
            self._tracer.end_span(span, attributes={
                "agent_scope": agent_scope,
                "task_type": profile.task_type,
                "gathered_files": gathered_files_count,
                "baseline_tokens": baseline_tokens,
                "tail_tokens": tail_tokens,
            })

        if self._metrics_tracker is not None:
            self._metrics_tracker.record_context_build(
                build_duration_ms=elapsed_ms,
                gathered_files=gathered_files_count,
                baseline_tokens=baseline_tokens,
                tail_tokens=tail_tokens,
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

        Phase 1: простое усечение низкоприоритетных элементов.

        Args:
            envelope: Исходный envelope
            max_context_tokens: Максимальный размер контекста
            reserved_tokens: Зарезервированные токены

        Returns:
            Усечённый PayloadEnvelope
        """
        available = max_context_tokens - reserved_tokens

        logger.debug(
            "context.ensure_fits.check",
            current_tokens=envelope.token_count,
            max_context_tokens=max_context_tokens,
            reserved_tokens=reserved_tokens,
            available_tokens=available,
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
            action="truncation_needed",
        )

        # TODO: Phase 3 - реализовать усечение низкоприоритетных элементов
        # Сейчас просто возвращаем envelope как есть
        return envelope

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

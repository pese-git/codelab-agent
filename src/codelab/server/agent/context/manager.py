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
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
    from codelab.server.tools.base import ToolRegistry

logger = logging.getLogger(__name__)


class DefaultContextManager(ContextManager):
    """Контекст-менеджер с гидратацией (Phase 1)."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        config: ContextConfig | None = None,
        llm: LLMProvider | None = None,
        model: str = "openai/gpt-4o-mini",
    ) -> None:
        self._tool_registry = tool_registry
        self._config = config or ContextConfig()
        self._llm = llm
        self._model = model
        self._budget_manager = DefaultTokenBudgetManager(self._config)
        self._dependency_graph = RegexDependencyGraph(Path.cwd())

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

        prompt_text = self._extract_prompt_text(prompt)

        analyzer = LLMBasedTaskAnalyzer(llm=self._llm, model=self._model)
        profile = await analyzer.analyze(prompt_text, session)

        logger.debug(
            "Task analyzed",
            task_type=profile.task_type,
            search_terms=profile.search_terms,
        )

        baseline: list[LLMMessage] = []

        if system_prompt:
            baseline.append(LLMMessage(role="system", content=system_prompt))

        if self._config.gather_enabled:
            session_id = getattr(session, "session_id", "unknown")
            gatherer = ACPContextGatherer(
                tool_registry=self._tool_registry,
                dependency_graph=self._dependency_graph,
                session_id=session_id,
            )
            items = await gatherer.gather(profile, session, options=options)

            context_content = self._format_context_items(items)
            if context_content:
                baseline.append(
                    LLMMessage(role="system", content=context_content)
                )

        tail: list[LLMMessage] = []
        for block in prompt:
            if block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    tail.append(LLMMessage(role="user", content=text))

        baseline_fingerprint = self._compute_fingerprint(baseline)
        token_count = self._estimate_total_tokens(baseline, tail)

        elapsed_ms = (time.time() - start_time) * 1000
        logger.debug(
            "Context built",
            baseline_messages=len(baseline),
            tail_messages=len(tail),
            token_count=token_count,
            elapsed_ms=elapsed_ms,
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

        if envelope.token_count <= available:
            return envelope

        logger.debug(
            "Context exceeds limit, truncating",
            current=envelope.token_count,
            available=available,
        )

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
        summary = f"[Subagent {subagent_scope} response placeholder]"
        return SubagentResult(
            summary=summary,
            token_count=0,
            source_scope=subagent_scope,
            shared_items=[],
        )

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

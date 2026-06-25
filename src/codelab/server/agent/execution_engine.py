"""ExecutionEngine — композиционный движок выполнения.

Композиция переиспользуемых компонентов:
- HistoryBuilder — session.history → LLMMessage
- ToolFilter — filter by capabilities + MCP
- MessageSanitizer — fix orphaned tool calls
- PlanExtractor — extract plan from response (существующий)
- ContextCompactor — prune + summarize

Phase 0: внутренне использует PayloadEnvelope (baseline/tail),
to_messages() — адаптер на границе с LLMAdapter.

Phase 1: при enabled=true использует DefaultContextManager для сбора контекста.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from codelab.server.agent.base import AgentContext, ContinuationContext
from codelab.server.agent.context.models import ContextConfig, PayloadEnvelope
from codelab.server.agent.history_builder import HistoryBuilder
from codelab.server.agent.message_sanitizer import MessageSanitizer
from codelab.server.agent.plan_extractor import PlanExtractor
from codelab.server.agent.tool_filter import ToolFilter
from codelab.server.llm.models import LLMMessage

if TYPE_CHECKING:
    from codelab.server.agent.context.interfaces import ContextManager
    from codelab.server.agent.context_compactor import ContextCompactor
    from codelab.server.protocol.state import SessionState
    from codelab.server.tools.base import ToolRegistry

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Композиционный движок выполнения.

    Attributes:
        history_builder: Конвертер истории
        tool_filter: Фильтр инструментов
        sanitizer: Санитайзер сообщений
        compactor: Компактор контекста
        plan_extractor: Извлекатель планов
        tool_registry: Реестр инструментов
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        compactor: ContextCompactor | None = None,
        history_builder: HistoryBuilder | None = None,
        tool_filter: ToolFilter | None = None,
        sanitizer: MessageSanitizer | None = None,
        plan_extractor: PlanExtractor | None = None,
        context_config: ContextConfig | None = None,
        context_manager: ContextManager | None = None,
    ) -> None:
        self.tool_registry = tool_registry
        self.compactor = compactor
        self.history_builder = history_builder or HistoryBuilder()
        self.tool_filter = tool_filter or ToolFilter()
        self.sanitizer = sanitizer or MessageSanitizer()
        self.plan_extractor = plan_extractor or PlanExtractor()
        self.context_config = context_config or ContextConfig()
        self.context_manager = context_manager

    async def build_context(
        self,
        session: SessionState,
        prompt: str,
        system_prompt: str | None = None,
        mcp_manager: Any | None = None,
        content_parts: list[Any] | None = None,
    ) -> AgentContext:
        """Собрать AgentContext из сессии и промпта.

        Автоматически применяет ContextCompactor если история превышает лимит.
        Это гарантирует что все стратегии (Single, Orchestrated, Hierarchical,
        Choreography) получают компактный контекст без дублирования логики.

        Phase 0: внутренне использует PayloadEnvelope (baseline/tail).
        to_messages() — адаптер на границе с LLMAdapter.

        Phase 1: при enabled=true использует ContextManager для сбора контекста.

        Args:
            session: Состояние сессии.
            prompt: Текст промпта пользователя.
            system_prompt: Системный промпт.
            mcp_manager: MCP manager для получения MCP инструментов.
            content_parts: Мультимодальные части содержимого (опционально).

        Returns:
            AgentContext для вызова LLM.
        """
        mcp_tools = None
        if mcp_manager is not None:
            mcp_tools = mcp_manager.get_all_tools()

        available_tools = self.tool_filter.filter(
            self.tool_registry.get_available_tools(session.session_id),
            session.runtime_capabilities,
            mcp_tools,
        )

        if self.context_config.enabled and self.context_manager is not None:
            prompt_blocks = [{"type": "text", "text": prompt}]
            if content_parts:
                prompt_blocks = [
                    self._content_part_to_dict(part) for part in content_parts
                ]

            envelope = await self.context_manager.build_context(
                session=session,
                prompt=prompt_blocks,
                agent_scope="single",
                system_prompt=system_prompt,
            )
            history = envelope.to_messages()
        else:
            history = self.history_builder.build(
                session.history,
                system_prompt=system_prompt,
            )

            history = self.sanitizer.sanitize(history)

            envelope = self._build_envelope(history)
            envelope = await self._ensure_envelope_fits(envelope)
            history = envelope.to_messages()

        if content_parts and not (self.context_config.enabled and self.context_manager):
            prompt_blocks = [
                self._content_part_to_dict(part) for part in content_parts
            ]
        elif not (self.context_config.enabled and self.context_manager):
            prompt_blocks = [{"type": "text", "text": prompt}]

        return AgentContext(
            session_id=session.session_id,
            session=session,
            prompt=prompt_blocks,
            conversation_history=history,
            available_tools=available_tools,
            config=session.config_values,
            model=session.config_values.get("model", ""),
        )

    @staticmethod
    def _content_part_to_dict(part: Any) -> dict[str, Any]:
        """Конвертировать ContentPart в dict для AgentContext.prompt."""
        if part.type == "text":
            return {"type": "text", "text": part.text or ""}
        if part.type == "image":
            return {
                "type": "image",
                "data": part.data or "",
                "mime_type": part.mime_type or "",
            }
        return {"type": "text", "text": ""}

    async def build_continuation_context(
        self,
        session: SessionState,
        mcp_manager: Any | None = None,
    ) -> ContinuationContext:
        """Собрать ContinuationContext для продолжения после tool_results.

        Автоматически применяет ContextCompactor если история превышает лимит.

        Phase 0: внутренне использует PayloadEnvelope (baseline/tail).

        Args:
            session: Состояние сессии (история уже содержит tool_results).
            mcp_manager: MCP manager.

        Returns:
            ContinuationContext для вызова LLM.
        """
        mcp_tools = None
        if mcp_manager is not None:
            mcp_tools = mcp_manager.get_all_tools()

        available_tools = self.tool_filter.filter(
            self.tool_registry.get_available_tools(session.session_id),
            session.runtime_capabilities,
            mcp_tools,
        )

        history = self.history_builder.build(session.history)
        history = self.sanitizer.sanitize(history)

        envelope = self._build_envelope(history)
        envelope = await self._ensure_envelope_fits(envelope)
        history = envelope.to_messages()

        return ContinuationContext(
            session_id=session.session_id,
            session=session,
            history=history,
            available_tools=available_tools,
            config=session.config_values,
            model=session.config_values.get("model", ""),
        )

    async def ensure_context_fits(
        self,
        history: list[LLMMessage],
    ) -> tuple[list[LLMMessage], bool, str]:
        """Убедиться что контекст помещается в лимит.

        Args:
            history: Текущая история сообщений.

        Returns:
            Кортеж (новая история, была ли compaction, причина).
        """
        if self.compactor is None:
            return history, False, "no_compactor"

        return await self.compactor.compact_if_needed(history)

    @staticmethod
    def _build_envelope(history: list[LLMMessage]) -> PayloadEnvelope:
        """Разделить историю на baseline (стабильный префикс) и tail (дельты).

        MVP: system prompt → baseline, остальное → tail.
        """
        baseline: list[LLMMessage] = []
        tail: list[LLMMessage] = []

        for msg in history:
            if msg.role == "system" and not tail:
                baseline.append(msg)
            else:
                tail.append(msg)

        return PayloadEnvelope(baseline=baseline, tail=tail)

    async def _ensure_envelope_fits(
        self,
        envelope: PayloadEnvelope,
    ) -> PayloadEnvelope:
        """Обеспечить что envelope помещается в лимит.

        Делегирует legacy compactor при enabled=false.
        """
        if self.compactor is None:
            return envelope

        messages = envelope.to_messages()
        compacted, changed, _reason = await self.compactor.compact_if_needed(
            messages,
        )

        if not changed:
            return envelope

        return self._build_envelope(compacted)

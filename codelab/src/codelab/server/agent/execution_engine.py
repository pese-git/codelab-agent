"""ExecutionEngine — композиционный движок выполнения.

Композиция переиспользуемых компонентов:
- HistoryBuilder — session.history → LLMMessage
- ToolFilter — filter by capabilities + MCP
- MessageSanitizer — fix orphaned tool calls
- PlanExtractor — extract plan from response (существующий)
- ContextCompactor — prune + summarize
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from codelab.server.agent.base import AgentContext, ContinuationContext
from codelab.server.agent.history_builder import HistoryBuilder
from codelab.server.agent.message_sanitizer import MessageSanitizer
from codelab.server.agent.plan_extractor import PlanExtractor
from codelab.server.agent.tool_filter import ToolFilter
from codelab.server.llm.models import LLMMessage

if TYPE_CHECKING:
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
    ) -> None:
        self.tool_registry = tool_registry
        self.compactor = compactor
        self.history_builder = history_builder or HistoryBuilder()
        self.tool_filter = tool_filter or ToolFilter()
        self.sanitizer = sanitizer or MessageSanitizer()
        self.plan_extractor = plan_extractor or PlanExtractor()

    async def build_context(
        self,
        session: SessionState,
        prompt: str,
        system_prompt: str | None = None,
        mcp_manager: Any | None = None,
    ) -> AgentContext:
        """Собрать AgentContext из сессии и промпта.

        Автоматически применяет ContextCompactor если история превышает лимит.
        Это гарантирует что все стратегии (Single, Orchestrated, Hierarchical,
        Choreography) получают компактный контекст без дублирования логики.

        Args:
            session: Состояние сессии.
            prompt: Текст промпта пользователя.
            system_prompt: Системный промпт.
            mcp_manager: MCP manager для получения MCP инструментов.

        Returns:
            AgentContext для вызова LLM.
        """
        # Фильтруем инструменты
        mcp_tools = None
        if mcp_manager is not None:
            mcp_tools = mcp_manager.get_all_tools()

        available_tools = self.tool_filter.filter(
            self.tool_registry.get_available_tools(session.session_id),
            session.runtime_capabilities,
            mcp_tools,
        )

        # Строим историю
        history = self.history_builder.build(
            session.history,
            system_prompt=system_prompt,
        )

        # Санитайзим
        history = self.sanitizer.sanitize(history)

        # Compaction: автоматически если история превышает лимит
        # Это обеспечивает единый путь для всех стратегий (SRP, Open/Closed)
        history, _, _ = await self.ensure_context_fits(history)

        return AgentContext(
            session_id=session.session_id,
            session=session,
            prompt=[{"type": "text", "text": prompt}],
            conversation_history=history,
            available_tools=available_tools,
            config=session.config_values,
            model=session.config_values.get("model", ""),
        )

    async def build_continuation_context(
        self,
        session: SessionState,
        mcp_manager: Any | None = None,
    ) -> ContinuationContext:
        """Собрать ContinuationContext для продолжения после tool_results.

        Автоматически применяет ContextCompactor если история превышает лимит.

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

        # Compaction: автоматически если история превышает лимит
        history, _, _ = await self.ensure_context_fits(history)

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

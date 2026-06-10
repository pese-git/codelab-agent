"""LegacyCallStrategy — адаптер AgentOrchestrator под LLMCallStrategy.

Реализует LLMCallStrategy Protocol для legacy пути выполнения
через AgentOrchestrator + NaiveAgent.

Архитектурное решение:
- Adapter pattern — адаптирует существующий AgentOrchestrator
- Сохраняет обратную совместимость с legacy кодом
- Не требует изменения AgentOrchestrator

Важно: AgentLoop добавляет tool_results в session.history перед вызовом
continue_execution(). LegacyCallStrategy передаёт пустой список в
orchestrator.continue_with_tool_results(), который использует history.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from codelab.server.agent.base import AgentResponse
    from codelab.server.agent.orchestrator import AgentOrchestrator
    from codelab.server.protocol.state import SessionState

logger = structlog.get_logger()


class LegacyCallStrategy:
    """Адаптер AgentOrchestrator под LLMCallStrategy Protocol.

    Адаптирует legacy AgentOrchestrator (с методами process_prompt и
    continue_with_tool_results) под унифицированный интерфейс LLMCallStrategy.

    Attributes:
        _orchestrator: Legacy оркестратор агентов.

    Example:
        strategy = LegacyCallStrategy(agent_orchestrator)
        response = await strategy.execute(session, "Hello")
        if response.tool_calls:
            # ... обработать tool_calls, добавить в session.history ...
            response = await strategy.continue_execution(session)
    """

    def __init__(self, orchestrator: AgentOrchestrator) -> None:
        """Инициализация адаптера.

        Args:
            orchestrator: Legacy оркестратор агентов.
        """
        self._orchestrator = orchestrator
        logger.debug("LegacyCallStrategy initialized")

    async def execute(
        self,
        session: SessionState,
        prompt: str | None,
        mcp_manager: Any | None = None,
    ) -> AgentResponse:
        """Выполнить вызов LLM с начальным prompt.

        Делегирует AgentOrchestrator.process_prompt().

        Args:
            session: Состояние сессии.
            prompt: Текст промпта пользователя.
            mcp_manager: MCP manager для tool execution.

        Returns:
            AgentResponse с текстом, tool_calls, usage, stop_reason.
        """
        if prompt is None:
            # Продолжение без prompt — используем continue_with_tool_results
            return await self._orchestrator.continue_with_tool_results(
                session, [], mcp_manager
            )

        return await self._orchestrator.process_prompt(
            session, prompt, mcp_manager
        )

    async def continue_execution(
        self,
        session: SessionState,
        mcp_manager: Any | None = None,
    ) -> AgentResponse:
        """Продолжить выполнение после tool_results.

        Делегирует AgentOrchestrator.continue_with_tool_results()
        с пустым списком tool_results, потому что tool_results
        уже добавлены в session.history вызывающим кодом (AgentLoop).

        Args:
            session: Состояние сессии (с tool_results в history).
            mcp_manager: MCP manager для tool execution.

        Returns:
            AgentResponse с текстом, tool_calls, usage, stop_reason.
        """
        return await self._orchestrator.continue_with_tool_results(
            session, [], mcp_manager
        )

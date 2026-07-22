"""Базовые интерфейсы для стратегий вызова LLM.

Определяет LLMCallStrategy Protocol — контракт для стратегий вызова LLM.
Реализуется StrategyDispatcher (EventBus путь).

Архитектурное решение:
- AgentLoop зависит от LLMCallStrategy Protocol (DIP)
- Конкретные стратегии реализуют Protocol
- Добавление новой стратегии не требует изменения AgentLoop (OCP)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from codelab.server.agent.contracts.ports import SessionView
    from codelab.server.agent.core.agent_base import AgentResponse

    OnDelta = Callable[[str], Awaitable[None]]


@runtime_checkable
class LLMCallStrategy(Protocol):
    """Интерфейс для стратегии вызова LLM.

    Следующий принцип Dependency Inversion:
    AgentLoop зависит от абстракции, не от конкретной реализации.

    Реализации:
    - StrategyDispatcher — EventBus путь (SingleStrategy → LLMAdapter)

    Пример использования:
        async def run(strategy: LLMCallStrategy, session: SessionState):
            response = await strategy.execute(session, "Hello")
            if response.tool_calls:
                # ... обработать tool_calls ...
                response = await strategy.continue_execution(session)
    """

    async def execute(
        self,
        session: SessionView,
        prompt: str | None,
        mcp_manager: Any | None = None,
        *,
        on_delta: OnDelta | None = None,
    ) -> AgentResponse:
        """Выполнить вызов LLM с начальным prompt.

        Первый вызов в рамках prompt turn. Стратегия формирует контекст
        из истории сессии и текста промпта, вызывает LLM.

        Args:
            session: Read-only представление сессии (SessionView).
            prompt: Текст промпта пользователя (None для продолжения).
            mcp_manager: MCP manager для tool execution (опционально).

        Returns:
            AgentResponse с текстом, tool_calls, usage, stop_reason.
        """
        ...

    async def continue_execution(
        self,
        session: SessionView,
        mcp_manager: Any | None = None,
        *,
        on_delta: OnDelta | None = None,
    ) -> AgentResponse:
        """Продолжить выполнение после tool_results.

        Вызывается после обработки tool_calls. Tool results уже находятся
        в session.history — стратегия передаёт их LLM для продолжения диалога.

        Args:
            session: Состояние сессии (с tool_results в history).
            mcp_manager: MCP manager для tool execution (опционально).

        Returns:
            AgentResponse с текстом, tool_calls, usage, stop_reason.
        """
        ...

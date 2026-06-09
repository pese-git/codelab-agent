"""SingleStrategy — базовая стратегия выполнения через EventBus.

Вызывает единственного агента через EventBus.send_request().
Принцип uniformity — тот же паттерн вызова, что и все остальные стратегии.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from codelab.server.agent.base import AgentResponse as BaseAgentResponse
from codelab.server.agent.contracts.base import (
    AgentRequest,
)

if TYPE_CHECKING:
    from codelab.server.agent.event_bus.bus import AgentEventBus
    from codelab.server.agent.execution_engine import ExecutionEngine
    from codelab.server.observability.tracer import SpanContext, Tracer
    from codelab.server.protocol.state import SessionState

logger = logging.getLogger(__name__)


class SingleStrategy:
    """Базовая стратегия — вызов единственного агента через EventBus.

    Attributes:
        event_bus: Шина событий для вызова агента
        execution_engine: Движок выполнения для сборки контекста
        tracer: Tracer для observability
        agent_name: Имя агента для вызова
    """

    def __init__(
        self,
        event_bus: AgentEventBus,
        execution_engine: ExecutionEngine,
        tracer: Tracer | None = None,
        agent_name: str = "primary",
    ) -> None:
        self.event_bus = event_bus
        self.execution_engine = execution_engine
        self.tracer = tracer
        self.agent_name = agent_name

    async def execute(
        self,
        session: SessionState,
        prompt: str,
        system_prompt: str | None = None,
        mcp_manager: Any | None = None,
        parent_span: SpanContext | None = None,
    ) -> BaseAgentResponse:
        """Выполнить стратегию — вызвать агента через EventBus.

        Args:
            session: Состояние сессии.
            prompt: Текст промпта пользователя.
            system_prompt: Системный промпт.
            mcp_manager: MCP manager.
            parent_span: Родительский span для tracing.

        Returns:
            AgentResponse с результатом вызова агента.
        """
        start_time = time.time()

        # Tracing: создаём span
        span = None
        if self.tracer:
            span = self.tracer.start_span(
                "single_strategy",
                parent=parent_span,
            )

        # Собираем контекст
        context = self.execution_engine.build_context(
            session=session,
            prompt=prompt,
            system_prompt=system_prompt,
            mcp_manager=mcp_manager,
        )

        # Формируем запрос
        request = AgentRequest(
            target_agent=self.agent_name,
            messages=context.conversation_history,
            tools=context.available_tools,
            correlation_id=f"single_{session.session_id}_{int(start_time)}",
            session_id=session.session_id,
        )

        # Вызываем агента через EventBus
        response = await self.event_bus.send_request(
            request=request,
            parent_span=span,
        )

        # Tracing: завершаем span
        if span and self.tracer:
            total_time_ms = (time.time() - start_time) * 1000
            self.tracer.end_span(
                span,
                attributes={
                    "agent_name": self.agent_name,
                    "total_time_ms": total_time_ms,
                    "stop_reason": response.stop_reason,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            )

        # Конвертируем AgentResponse (DomainEvent) → BaseAgentResponse
        return BaseAgentResponse(
            text=response.text,
            tool_calls=[],  # ToolCall → LLMToolCall конвертация если нужна
            stop_reason=response.stop_reason,
        )

    async def continue_execution(
        self,
        session: SessionState,
        mcp_manager: Any | None = None,
        parent_span: SpanContext | None = None,
    ) -> BaseAgentResponse:
        """Продолжить выполнение после tool_results.

        Args:
            session: Состояние сессии (история уже содержит tool_results).
            mcp_manager: MCP manager.
            parent_span: Родительский span.

        Returns:
            AgentResponse с результатом.
        """
        start_time = time.time()

        span = None
        if self.tracer:
            span = self.tracer.start_span(
                "single_strategy_continue",
                parent=parent_span,
            )

        context = self.execution_engine.build_continuation_context(
            session=session,
            mcp_manager=mcp_manager,
        )

        request = AgentRequest(
            target_agent=self.agent_name,
            messages=context.history,
            tools=context.available_tools,
            correlation_id=f"single_cont_{session.session_id}",
            session_id=session.session_id,
        )

        response = await self.event_bus.send_request(
            request=request,
            parent_span=span,
        )

        if span and self.tracer:
            total_time_ms = (time.time() - start_time) * 1000
            self.tracer.end_span(
                span,
                attributes={
                    "agent_name": self.agent_name,
                    "total_time_ms": total_time_ms,
                    "stop_reason": response.stop_reason,
                },
            )

        return BaseAgentResponse(
            text=response.text,
            tool_calls=[],
            stop_reason=response.stop_reason,
        )

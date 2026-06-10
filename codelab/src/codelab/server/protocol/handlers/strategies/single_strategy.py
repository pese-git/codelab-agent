"""SingleStrategy — базовая стратегия выполнения через EventBus.

Вызывает единственного агента через EventBus.send_request().
Принцип uniformity — тот же паттерн вызова, что и все остальные стратегии.

Агент для вызова определяется через параметр agent_name в execute(),
который передаётся из StrategyDispatcher на основе session.config_values["_agent"].
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from codelab.server.agent.base import AgentResponse as BaseAgentResponse
from codelab.server.agent.contracts.base import (
    AgentRequest,
)
from codelab.server.llm.models import LLMToolCall

if TYPE_CHECKING:
    from codelab.server.agent.event_bus.bus import AgentEventBus
    from codelab.server.agent.execution_engine import ExecutionEngine
    from codelab.server.observability.tracer import SpanContext, Tracer
    from codelab.server.protocol.state import SessionState

logger = logging.getLogger(__name__)


def _convert_tool_calls(
    contract_tool_calls: list,
) -> list[LLMToolCall]:
    """Конвертировать ToolCall из контрактов шины → LLMToolCall.

    EventBus возвращает ToolCall (contracts.base), а LLMLoopStage
    ожидает LLMToolCall (llm.models). Структура идентична:
    id, name, arguments.

    Args:
        contract_tool_calls: Список ToolCall из AgentResponse шины.

    Returns:
        Список LLMToolCall для LLMLoopStage.
    """
    return [
        LLMToolCall(
            id=tc.id,
            name=tc.name,
            arguments=tc.arguments,
        )
        for tc in contract_tool_calls
    ]


def _convert_usage_to_dict(usage) -> dict[str, int] | None:
    """Конвертировать TokenUsage в dict для AgentResponse.usage.

    Args:
        usage: TokenUsage из AgentResponse шины.

    Returns:
        Dict с input_tokens, output_tokens, total_tokens или None.
    """
    if usage is None:
        return None
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
    }


class SingleStrategy:
    """Базовая стратегия — вызов единственного агента через EventBus.

    Attributes:
        event_bus: Шина событий для вызова агента
        execution_engine: Движок выполнения для сборки контекста
        tracer: Tracer для observability
        default_agent_name: Имя агента по умолчанию (fallback)
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
        self.default_agent_name = agent_name

    async def execute(
        self,
        session: SessionState,
        prompt: str | None,
        mcp_manager: Any | None = None,
        *,
        system_prompt: str | None = None,
        parent_span: SpanContext | None = None,
        agent_name: str | None = None,
    ) -> BaseAgentResponse:
        """Выполнить стратегию — вызвать агента через EventBus.

        Args:
            session: Состояние сессии.
            prompt: Текст промпта пользователя (None для продолжения).
            mcp_manager: MCP manager.
            system_prompt: Системный промпт (keyword-only, опционально).
            parent_span: Родительский span для tracing (keyword-only, опционально).
            agent_name: Имя агента для вызова (из session.config_values["_agent"]).
                Если None, используется default_agent_name.

        Returns:
            AgentResponse с результатом вызова агента.
        """
        target_agent = agent_name or self.default_agent_name
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
            target_agent=target_agent,
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
                    "agent_name": target_agent,
                    "total_time_ms": total_time_ms,
                    "stop_reason": response.stop_reason,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                },
            )

        # Конвертируем AgentResponse (DomainEvent) → BaseAgentResponse
        # КРИТИЧНО: tool_calls НЕ должны быть пустыми — LLMLoopStage
        # проверяет их для продолжения цикла tool-calling.
        return BaseAgentResponse(
            text=response.text,
            tool_calls=_convert_tool_calls(response.tool_calls),
            stop_reason=response.stop_reason,
            usage=_convert_usage_to_dict(response.usage),
        )

    async def continue_execution(
        self,
        session: SessionState,
        mcp_manager: Any | None = None,
        *,
        parent_span: SpanContext | None = None,
        agent_name: str | None = None,
    ) -> BaseAgentResponse:
        """Продолжить выполнение после tool_results.

        Args:
            session: Состояние сессии (история уже содержит tool_results).
            mcp_manager: MCP manager.
            parent_span: Родительский span (keyword-only, опционально).
            agent_name: Имя агента для вызова (keyword-only, опционально).
                Если None, используется default_agent_name.

        Returns:
            AgentResponse с результатом.
        """
        target_agent = agent_name or self.default_agent_name
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
            target_agent=target_agent,
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
                    "agent_name": target_agent,
                    "total_time_ms": total_time_ms,
                    "stop_reason": response.stop_reason,
                },
            )

        return BaseAgentResponse(
            text=response.text,
            tool_calls=_convert_tool_calls(response.tool_calls),
            stop_reason=response.stop_reason,
            usage=_convert_usage_to_dict(response.usage),
        )

"""LLMAdapter — единый LLM-агент для мультиагентной архитектуры.

Заменяет NaiveAgent. Реализует:
- call() → AgentResult с сохранением usage (токены)
- Регистрацию в AgentEventBus как RequestHandler
- Tracer span для каждого LLM вызова
- ОДИН вызов LLM (single call pattern) — цикл tool-calling в LLMLoopStage
- Отмену через asyncio.Task tracking
- Tool name mapping (acp_name_to_llm_name)
- Plan extraction из ответа LLM

Архитектурное решение:
LLMAdapter делает ровно один вызов LLM провайдера и возвращает результат.
Цикл tool-calling (permissions, MCP, notifications) выполняется в LLMLoopStage.
Это соответствует спецификации §3.4: "Single LLM call pattern".
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING, Any

from codelab.server.agent.contracts.base import (
    AgentRequest,
    AgentResponse,
    AgentResult,
    TokenUsage,
    ToolCall,
)
from codelab.server.agent.plan_extractor import PlanExtractor
from codelab.server.llm.base import LLMProvider
from codelab.server.llm.models import (
    CompletionRequest,
    CompletionResponse,
    LLMMessage,
    StopReason,
)
from codelab.server.tools.base import ToolDefinition, ToolRegistry
from codelab.server.tools.mapping import acp_name_to_llm_name

if TYPE_CHECKING:
    from codelab.server.agent.event_bus.bus import AgentEventBus
    from codelab.server.observability.tracer import SpanContext, Tracer

logger = logging.getLogger(__name__)


class LLMAdapter:
    """Адаптер LLM для мультиагентной шины событий.

    Реализует RequestHandler Protocol — регистрируется в AgentEventBus
    и обрабатывает AgentRequest → AgentResult.

    Делает ровно ОДИН вызов LLM провайдера. Цикл tool-calling,
    permissions, MCP и notifications — ответственность LLMLoopStage.

    Attributes:
        _llm_provider: LLM провайдер для вызовов
        _tool_registry: Реестр инструментов
        _tracer: Tracer для observability
        _event_bus: Шина событий (опционально)
        _active_tasks: Активные asyncio.Task для отмены
        _name: Имя агента
        _plan_extractor: Извлекатель планов из ответа LLM
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        tool_registry: ToolRegistry,
        tracer: Tracer | None = None,
        event_bus: AgentEventBus | None = None,
        name: str = "llm_adapter",
    ) -> None:
        self._llm_provider = llm_provider
        self._tool_registry = tool_registry
        self._tracer = tracer
        self._event_bus = event_bus
        self._active_tasks: dict[int, asyncio.Task] = {}
        self._name = name
        self._plan_extractor = PlanExtractor()

    async def call(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
        config: dict[str, Any] | None = None,
        parent_span: SpanContext | None = None,
    ) -> AgentResult:
        """Выполнить ОДИН вызов LLM провайдера.

        Не выполняет tool-calling — это ответственность LLMLoopStage.
        Возвращает AgentResult с текстом, tool_calls, usage, stop_reason.

        Args:
            messages: История сообщений для LLM
            tools: Доступные инструменты
            config: Конфигурация (model, temperature, max_tokens, etc.)
            parent_span: Родительский span для tracing

        Returns:
            AgentResult с текстом, tool_calls, usage, stop_reason
        """
        config = config or {}
        model = config.get("model", self._llm_provider.name)

        # Tracing: создаём span
        span = None
        if self._tracer:
            span = self._tracer.start_span(
                "llm_call",
                parent=parent_span,
            )

        start_time = time.time()

        # Создаём задачу для отслеживания отмены
        task = asyncio.create_task(
            self._single_call(messages, tools, config, model)
        )
        task_id = id(task)
        self._active_tasks[task_id] = task

        try:
            result = await task
        except asyncio.CancelledError:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            return AgentResult(
                text="",
                tool_calls=[],
                usage=TokenUsage(0, 0, 0),
                stop_reason="cancelled",
                agent_name=self._name,
            )
        finally:
            self._active_tasks.pop(task_id, None)

        # Tracing: завершаем span с атрибутами
        if span and self._tracer:
            latency_ms = (time.time() - start_time) * 1000
            self._tracer.end_span(
                span,
                attributes={
                    "model": model,
                    "provider": self._llm_provider.name,
                    "input_tokens": result.usage.input_tokens,
                    "output_tokens": result.usage.output_tokens,
                    "latency_ms": latency_ms,
                },
            )

        return result

    async def _single_call(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
        config: dict[str, Any],
        model: str,
    ) -> AgentResult:
        """Один вызов LLM провайдера.

        Делает ровно один create_completion(), извлекает usage,
        plan, конвертирует tool_calls в контракт шины.

        Args:
            messages: История сообщений
            tools: Доступные инструменты
            config: Конфигурация
            model: Идентификатор модели

        Returns:
            AgentResult с результатом одного LLM вызова
        """
        temperature = config.get("temperature", 0.7)
        max_tokens = config.get("max_tokens", 8192)

        # Конвертируем имена инструментов для LLM
        llm_tools = self._tool_registry.to_llm_tools(tools)
        for tool in llm_tools:
            if "function" in tool and "name" in tool["function"]:
                tool["function"]["name"] = acp_name_to_llm_name(
                    tool["function"]["name"]
                )

        request = CompletionRequest(
            model=model,
            messages=list(messages),
            tools=llm_tools if tools else None,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        response = await self._llm_provider.create_completion(request)

        # Собираем usage
        usage = self._extract_usage(response)

        # Извлекаем план если есть (для будущих стратегий)
        if response.text:
            self._plan_extractor.extract_from_text(response.text)
        if response.tool_calls:
            self._plan_extractor.extract_from_tool_call(response.tool_calls)

        # Конвертируем tool_calls в контракт шины
        tool_calls = [
            ToolCall(
                id=tc.id,
                name=tc.name,
                arguments=tc.arguments,
            )
            for tc in response.tool_calls
        ] if response.tool_calls else []

        return AgentResult(
            text=response.text or "",
            tool_calls=tool_calls,
            usage=usage,
            stop_reason=self._map_stop_reason(response.stop_reason),
            agent_name=self._name,
        )

    def _extract_usage(self, response: CompletionResponse) -> TokenUsage:
        """Извлечь TokenUsage из CompletionResponse."""
        usage_data = response.usage
        input_tokens = usage_data.get("input_tokens", 0)
        output_tokens = usage_data.get("output_tokens", 0)
        total_tokens = usage_data.get("total_tokens", input_tokens + output_tokens)
        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )

    def _map_stop_reason(self, stop_reason: StopReason) -> str:
        """Маппинг StopReason → строковый stop_reason."""
        mapping = {
            StopReason.END_TURN: "end_turn",
            StopReason.TOOL_USE: "tool_use",
            StopReason.MAX_TOKENS: "max_tokens",
            StopReason.STOP_SEQUENCE: "stop_sequence",
            StopReason.ERROR: "error",
            StopReason.CANCELLED: "cancelled",
            StopReason.STREAMING: "streaming",
            StopReason.REFUSAL: "refusal",
        }
        return mapping.get(stop_reason, "end_turn")

    async def cancel(self) -> None:
        """Отменить все активные задачи."""
        for _task_id, task in list(self._active_tasks.items()):
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._active_tasks.clear()

    async def _handle_request(
        self,
        request: AgentRequest,
        parent_span: SpanContext | None = None,
    ) -> AgentResponse:
        """Обработать AgentRequest → AgentResponse.

        Реализует RequestHandler Protocol для регистрации в EventBus.
        """
        result = await self.call(
            messages=request.messages,
            tools=request.tools,
            config={},
            parent_span=parent_span,
        )

        return AgentResponse(
            request_id=request.correlation_id,
            text=result.text,
            tool_calls=result.tool_calls,
            usage=result.usage,
            stop_reason=result.stop_reason,
            agent_name=result.agent_name,
            session_id=request.session_id,
        )

    async def register_with_bus(
        self,
        event_bus: AgentEventBus,
        agent_name: str,
    ) -> None:
        """Зарегистрировать адаптер в EventBus как RequestHandler.

        Args:
            event_bus: Шина событий
            agent_name: Имя агента для регистрации
        """
        self._event_bus = event_bus
        self._name = agent_name
        await event_bus.register_agent(agent_name, self._handle_request)

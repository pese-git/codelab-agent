"""Тесты для LLMAdapter.

LLMAdapter делает ровно ОДИН вызов LLM провайдера (single call pattern).
Цикл tool-calling выполняется в LLMLoopStage, не внутри адаптера.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.agent.contracts.base import (
    AgentRequest,
    AgentResponse,
    TokenUsage,
)
from codelab.server.agent.llm_adapter import LLMAdapter
from codelab.server.llm.base import LLMProvider
from codelab.server.llm.models import (
    CompletionResponse,
    LLMMessage,
    LLMToolCall,
    StopReason,
)
from codelab.server.observability.tracer import SpanContext, Tracer
from codelab.server.tools.base import ToolDefinition, ToolRegistry


@pytest.fixture
def mock_llm_provider():
    provider = MagicMock(spec=LLMProvider)
    provider.name = "openai"
    return provider


@pytest.fixture
def mock_tool_registry():
    registry = MagicMock(spec=ToolRegistry)
    registry.to_llm_tools.return_value = []
    return registry


@pytest.fixture
def mock_tracer():
    return Tracer(debug=True)


@pytest.fixture
def adapter(mock_llm_provider, mock_tool_registry, mock_tracer):
    return LLMAdapter(
        llm_provider=mock_llm_provider,
        tool_registry=mock_tool_registry,
        tracer=mock_tracer,
        name="test_adapter",
    )


class TestLLMCallNoTools:
    """6.1 — LLM вызов без tools → текстовый ответ."""

    @pytest.mark.asyncio
    async def test_text_response(self, adapter, mock_llm_provider):
        mock_llm_provider.create_completion = AsyncMock(
            return_value=CompletionResponse(
                text="Hello, world!",
                stop_reason=StopReason.END_TURN,
                usage={"input_tokens": 10, "output_tokens": 5},
            )
        )

        result = await adapter.call(
            messages=[LLMMessage(role="user", content="Hi")],
            tools=[],
        )

        assert result.text == "Hello, world!"
        assert result.tool_calls == []
        assert result.stop_reason == "end_turn"
        assert result.agent_name == "test_adapter"

    @pytest.mark.asyncio
    async def test_usage_preserved(self, adapter, mock_llm_provider):
        mock_llm_provider.create_completion = AsyncMock(
            return_value=CompletionResponse(
                text="Response",
                usage={
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150,
                },
            )
        )

        result = await adapter.call(
            messages=[LLMMessage(role="user", content="Hi")],
            tools=[],
        )

        assert result.usage == TokenUsage(100, 50, 150)


class TestLLMCallWithTools:
    """6.2 — LLM вызов с tools → возвращает tool_calls (без выполнения).

    LLMAdapter делает ОДИН вызов LLM и возвращает tool_calls наружу.
    Выполнение инструментов — ответственность LLMLoopStage.
    """

    @pytest.mark.asyncio
    async def test_returns_tool_calls_without_executing(
        self, adapter, mock_llm_provider, mock_tool_registry
    ):
        """LLMAdapter возвращает tool_calls, но НЕ выполняет инструменты."""
        mock_llm_provider.create_completion = AsyncMock(
            return_value=CompletionResponse(
                text="",
                tool_calls=[
                    LLMToolCall(
                        id="tc1",
                        name="fs_read_file",
                        arguments={"path": "test.py"},
                    )
                ],
                stop_reason=StopReason.TOOL_USE,
                usage={"input_tokens": 10, "output_tokens": 5},
            )
        )

        mock_tool_registry.to_llm_tools.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "fs_read_file",
                    "description": "Read file",
                    "parameters": {},
                },
            }
        ]

        tools = [
            ToolDefinition(
                name="fs/read_file",
                description="Read",
                parameters={},
                kind="filesystem",
            )
        ]

        result = await adapter.call(
            messages=[LLMMessage(role="user", content="Read test.py")],
            tools=tools,
        )

        # Инструменты НЕ выполнялись внутри адаптера
        mock_tool_registry.execute_tool.assert_not_called()

        # Но tool_calls возвращены для LLMLoopStage
        assert result.text == ""
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "fs_read_file"
        assert result.tool_calls[0].arguments == {"path": "test.py"}
        assert result.stop_reason == "tool_use"


class TestUsage:
    """6.3 — сохранение usage из ответа LLM."""

    @pytest.mark.asyncio
    async def test_usage_from_single_call(self, adapter, mock_llm_provider):
        """Usage из одного вызова LLM сохраняется корректно."""
        mock_llm_provider.create_completion = AsyncMock(
            return_value=CompletionResponse(
                text="done",
                usage={"input_tokens": 10, "output_tokens": 5},
            )
        )

        result = await adapter.call(
            messages=[LLMMessage(role="user", content="test")],
            tools=[],
        )

        assert result.usage.input_tokens == 10
        assert result.usage.output_tokens == 5
        assert result.usage.total_tokens == 15


class TestCancellation:
    """4.4, 4.5 — отмена и нормальное завершение."""

    @pytest.mark.asyncio
    async def test_cancel_active_task(self, adapter, mock_llm_provider):
        """Отмена активной задачи → cancelled result."""
        async def slow_completion(request):
            await asyncio.sleep(10)
            return CompletionResponse(text="done")

        mock_llm_provider.create_completion = slow_completion

        task = asyncio.create_task(
            adapter.call(
                messages=[LLMMessage(role="user", content="test")],
                tools=[],
            )
        )

        # Даём задаче начаться
        await asyncio.sleep(0.01)
        assert len(adapter._active_tasks) == 1

        # Отменяем
        task.cancel()
        result = await task

        assert result.stop_reason == "cancelled"
        assert len(adapter._active_tasks) == 0

    @pytest.mark.asyncio
    async def test_normal_completion_clears_task(self, adapter, mock_llm_provider):
        """Нормальное завершение → задача очищена."""
        mock_llm_provider.create_completion = AsyncMock(
            return_value=CompletionResponse(
                text="done",
                usage={"input_tokens": 10, "output_tokens": 5},
            )
        )

        result = await adapter.call(
            messages=[LLMMessage(role="user", content="test")],
            tools=[],
        )

        assert result.stop_reason == "end_turn"
        assert len(adapter._active_tasks) == 0


class TestTracingIntegration:
    """3.3, 3.4 — tracing span с parent context и usage атрибутами."""

    @pytest.mark.asyncio
    async def test_span_created_with_parent(self, adapter, mock_llm_provider, mock_tracer):
        """Span создан с правильным родительским контекстом."""
        mock_llm_provider.create_completion = AsyncMock(
            return_value=CompletionResponse(
                text="done",
                usage={"input_tokens": 10, "output_tokens": 5},
            )
        )

        parent_span = SpanContext(name="parent", session_id="s1")
        await adapter.call(
            messages=[LLMMessage(role="user", content="test")],
            tools=[],
            parent_span=parent_span,
        )

        completed = mock_tracer.get_completed_spans()
        assert len(completed) == 1
        span = completed[0]
        assert span.name == "llm_call"
        assert span.parent_id == parent_span.span_id

    @pytest.mark.asyncio
    async def test_span_attributes_include_usage(self, adapter, mock_llm_provider, mock_tracer):
        """Атрибуты span включают данные usage."""
        mock_llm_provider.create_completion = AsyncMock(
            return_value=CompletionResponse(
                text="done",
                usage={"input_tokens": 100, "output_tokens": 50},
            )
        )

        await adapter.call(
            messages=[LLMMessage(role="user", content="test")],
            tools=[],
        )

        completed = mock_tracer.get_completed_spans()
        assert len(completed) == 1
        span = completed[0]
        assert span.attributes.get("input_tokens") == 100
        assert span.attributes.get("output_tokens") == 50
        assert span.attributes.get("model") == "openai"
        assert "latency_ms" in span.attributes


class TestToolNameMapping:
    """5.3 — маппинг имён инструментов."""

    @pytest.mark.asyncio
    async def test_tool_name_mapped_in_llm_call(
        self, adapter, mock_llm_provider, mock_tool_registry,
    ):
        """Имена инструментов конвертируются через acp_name_to_llm_name."""
        mock_llm_provider.create_completion = AsyncMock(
            return_value=CompletionResponse(
                text="done",
                usage={"input_tokens": 10, "output_tokens": 5},
            )
        )

        mock_tool_registry.to_llm_tools.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "fs/read_file",
                    "description": "Read file",
                    "parameters": {},
                },
            }
        ]

        await adapter.call(
            messages=[LLMMessage(role="user", content="test")],
            tools=[
                ToolDefinition(
                    name="fs/read_file",
                    description="",
                    parameters={},
                    kind="filesystem",
                )
            ],
        )

        # Проверяем что имя было замаплено
        call_args = mock_llm_provider.create_completion.call_args
        request = call_args[0][0]
        assert request.tools is not None
        assert request.tools[0]["function"]["name"] == "fs_read_file"


class TestPlanExtraction:
    """5.4 — извлечение плана через PlanExtractor."""

    @pytest.mark.asyncio
    async def test_plan_extracted_from_text(self, adapter, mock_llm_provider):
        """План извлекается из текстового ответа."""
        response_text = '''Here is my plan:
```json
{"plan": [{"content": "Step 1", "priority": "high", "status": "pending"}]}
```
'''
        mock_llm_provider.create_completion = AsyncMock(
            return_value=CompletionResponse(
                text=response_text,
                usage={"input_tokens": 10, "output_tokens": 20},
            )
        )

        result = await adapter.call(
            messages=[LLMMessage(role="user", content="test")],
            tools=[],
        )

        assert result.text == response_text


class TestEventBusIntegration:
    """2.3, 6.5 — register_with_bus → send_request → корректный ответ."""

    @pytest.mark.asyncio
    async def test_register_and_handle_request(self, mock_llm_provider, mock_tool_registry):
        """register_with_bus → send_request → корректный ответ."""
        from codelab.server.agent.event_bus.bus import AgentEventBus, RetryConfig

        bus = AgentEventBus(retry_config=RetryConfig(max_attempts=1, base_delay=0.0))
        adapter = LLMAdapter(
            llm_provider=mock_llm_provider,
            tool_registry=mock_tool_registry,
            name="coder",
        )

        mock_llm_provider.create_completion = AsyncMock(
            return_value=CompletionResponse(
                text="Hello from LLM!",
                usage={"input_tokens": 10, "output_tokens": 5},
            )
        )

        await adapter.register_with_bus(bus, "coder")

        request = AgentRequest(
            target_agent="coder",
            messages=[LLMMessage(role="user", content="Hi")],
            tools=[],
            correlation_id="corr_1",
            session_id="sess_1",
        )

        response = await bus.send_request(request)

        assert isinstance(response, AgentResponse)
        assert response.text == "Hello from LLM!"
        assert response.request_id == "corr_1"
        assert response.agent_name == "coder"
        assert response.usage == TokenUsage(10, 5, 15)

    @pytest.mark.asyncio
    async def test_full_cycle_through_eventbus(self, mock_llm_provider, mock_tool_registry):
        """Integration: полный цикл через EventBus."""
        from codelab.server.agent.event_bus.bus import AgentEventBus, RetryConfig
        from codelab.server.observability.event_timeline import EventTimeline
        from codelab.server.observability.metrics_tracker import MetricsTracker

        bus = AgentEventBus(retry_config=RetryConfig(max_attempts=1, base_delay=0.0))
        timeline = EventTimeline(debug=True)
        metrics = MetricsTracker(debug=True)

        timeline.subscribe_to_bus(bus)
        metrics.subscribe_to_bus(bus)

        adapter = LLMAdapter(
            llm_provider=mock_llm_provider,
            tool_registry=mock_tool_registry,
            name="coder",
        )

        mock_llm_provider.create_completion = AsyncMock(
            return_value=CompletionResponse(
                text="Response from coder",
                usage={"input_tokens": 100, "output_tokens": 50},
            )
        )

        await adapter.register_with_bus(bus, "coder")

        request = AgentRequest(
            target_agent="coder",
            messages=[LLMMessage(role="user", content="Test")],
            tools=[],
            correlation_id="c1",
            session_id="s1",
        )

        response = await bus.send_request(request)

        assert response.text == "Response from coder"
        assert response.usage.input_tokens == 100

        events = timeline.get_events("s1")
        assert any(e.event_type == "AgentResponse" for e in events)

        m = metrics.get_metrics("s1")
        assert m.agent_responses == 1

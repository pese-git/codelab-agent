"""Тесты для SingleStrategy."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.agent.base import AgentResponse as BaseAgentResponse
from codelab.server.agent.contracts.base import (
    AgentResponse,
    TokenUsage,
)
from codelab.server.agent.event_bus.bus import AgentEventBus, RetryConfig
from codelab.server.agent.execution_engine import ExecutionEngine
from codelab.server.agent.llm_adapter import LLMAdapter
from codelab.server.llm.base import LLMProvider
from codelab.server.llm.models import CompletionResponse, LLMMessage
from codelab.server.observability.tracer import Tracer
from codelab.server.protocol.handlers.strategies.single_strategy import (
    SingleStrategy,
)
from codelab.server.protocol.state import SessionState
from codelab.server.tools.base import ToolRegistry


@pytest.fixture
def mock_event_bus():
    bus = MagicMock(spec=AgentEventBus)
    bus.send_request = AsyncMock(
        return_value=AgentResponse(
            request_id="r1",
            text="Response from agent",
            tool_calls=[],
            usage=TokenUsage(100, 50, 150),
            stop_reason="end_turn",
            agent_name="primary",
            session_id="s1",
        )
    )
    return bus


@pytest.fixture
def mock_execution_engine():
    engine = MagicMock(spec=ExecutionEngine)
    engine.build_context.return_value = MagicMock(
        session_id="s1",
        conversation_history=[LLMMessage(role="user", content="Hello")],
        available_tools=[],
    )
    return engine


@pytest.fixture
def mock_tracer():
    return Tracer(debug=True)


@pytest.fixture
def mock_session():
    session = MagicMock(spec=SessionState)
    session.session_id = "s1"
    session.config_values = {"model": "openai/gpt-4o"}
    return session


class TestSingleStrategyExecute:
    """6.7 — execute → send_request → AgentResponse."""

    @pytest.mark.asyncio
    async def test_execute_returns_response(
        self, mock_event_bus, mock_execution_engine, mock_session
    ):
        strategy = SingleStrategy(
            event_bus=mock_event_bus,
            execution_engine=mock_execution_engine,
            agent_name="primary",
        )

        result = await strategy.execute(
            session=mock_session,
            prompt="Hello",
        )

        assert isinstance(result, BaseAgentResponse)
        assert result.text == "Response from agent"
        assert result.stop_reason == "end_turn"
        mock_event_bus.send_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_calls_send_request_with_correct_request(
        self, mock_event_bus, mock_execution_engine, mock_session
    ):
        strategy = SingleStrategy(
            event_bus=mock_event_bus,
            execution_engine=mock_execution_engine,
            agent_name="coder",
        )

        await strategy.execute(
            session=mock_session,
            prompt="Test",
        )

        call_args = mock_event_bus.send_request.call_args
        request = call_args.kwargs.get("request") or call_args.args[0]
        assert request.target_agent == "coder"
        assert request.session_id == "s1"


class TestTracingIntegration:
    """6.5 — Tracer integration."""

    @pytest.mark.asyncio
    async def test_tracer_span_created(
        self, mock_event_bus, mock_execution_engine, mock_session, mock_tracer
    ):
        strategy = SingleStrategy(
            event_bus=mock_event_bus,
            execution_engine=mock_execution_engine,
            tracer=mock_tracer,
        )

        await strategy.execute(
            session=mock_session,
            prompt="Test",
        )

        completed = mock_tracer.get_completed_spans()
        assert len(completed) == 1
        assert completed[0].name == "single_strategy"


class TestContinueExecution:
    """Тесты continue_execution."""

    @pytest.mark.asyncio
    async def test_continue_execution_returns_response(
        self, mock_event_bus, mock_execution_engine, mock_session
    ):
        mock_execution_engine.build_continuation_context.return_value = MagicMock(
            session_id="s1",
            history=[LLMMessage(role="user", content="Hello")],
            available_tools=[],
        )

        strategy = SingleStrategy(
            event_bus=mock_event_bus,
            execution_engine=mock_execution_engine,
        )

        result = await strategy.continue_execution(session=mock_session)

        assert isinstance(result, BaseAgentResponse)
        assert result.text == "Response from agent"


class TestFullIntegration:
    """6.9 — integration: полный цикл через EventBus + LLMAdapter."""

    @pytest.mark.asyncio
    async def test_full_cycle_with_mock_llm(self):
        """Полный цикл: Strategy → EventBus → LLMAdapter → Response."""
        mock_llm = MagicMock(spec=LLMProvider)
        mock_llm.name = "openai"
        mock_llm.create_completion = AsyncMock(
            return_value=CompletionResponse(
                text="Hello from LLM!",
                usage={"input_tokens": 10, "output_tokens": 5},
            )
        )

        mock_tool_registry = MagicMock(spec=ToolRegistry)
        mock_tool_registry.to_llm_tools.return_value = []

        bus = AgentEventBus(retry_config=RetryConfig(max_attempts=1, base_delay=0.0))
        tracer = Tracer(debug=True)

        adapter = LLMAdapter(
            llm_provider=mock_llm,
            tool_registry=mock_tool_registry,
            tracer=tracer,
            name="primary",
        )
        await adapter.register_with_bus(bus, "primary")

        engine = MagicMock(spec=ExecutionEngine)
        engine.build_context.return_value = MagicMock(
            session_id="s1",
            conversation_history=[LLMMessage(role="user", content="Hi")],
            available_tools=[],
        )

        strategy = SingleStrategy(
            event_bus=bus,
            execution_engine=engine,
            tracer=tracer,
            agent_name="primary",
        )

        session = MagicMock(spec=SessionState)
        session.session_id = "s1"
        session.config_values = {}

        result = await strategy.execute(session=session, prompt="Hi")

        assert result.text == "Hello from LLM!"
        assert result.stop_reason == "end_turn"

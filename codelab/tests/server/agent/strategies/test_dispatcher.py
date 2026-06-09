"""Тесты для StrategyDispatcher."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.agent.event_bus.bus import AgentEventBus, RetryConfig
from codelab.server.agent.execution_engine import ExecutionEngine
from codelab.server.agent.strategies.dispatcher import StrategyDispatcher
from codelab.server.llm.models import LLMMessage
from codelab.server.observability.tracer import Tracer
from codelab.server.protocol.state import SessionState


@pytest.fixture
def mock_event_bus():
    bus = MagicMock(spec=AgentEventBus)
    bus.send_request = AsyncMock()
    return bus


@pytest.fixture
def mock_execution_engine():
    engine = MagicMock(spec=ExecutionEngine)
    engine.build_context.return_value = MagicMock(
        session_id="s1",
        conversation_history=[LLMMessage(role="user", content="Hello")],
        available_tools=[],
    )
    engine.build_continuation_context.return_value = MagicMock(
        session_id="s1",
        history=[LLMMessage(role="user", content="Hello")],
        available_tools=[],
    )
    return engine


@pytest.fixture
def mock_tracer():
    return Tracer(debug=True)


@pytest.fixture
def dispatcher(mock_event_bus, mock_execution_engine, mock_tracer):
    return StrategyDispatcher(
        event_bus=mock_event_bus,
        execution_engine=mock_execution_engine,
        tracer=mock_tracer,
        default_mode="single",
    )


@pytest.fixture
def mock_session():
    session = MagicMock(spec=SessionState)
    session.session_id = "s1"
    session.config_values = {"mode": "single"}
    return session


class TestExecute:
    """Тесты execute — маршрутизация по mode."""

    @pytest.mark.asyncio
    async def test_execute_dispatches_to_single_strategy(
        self, dispatcher, mock_session
    ):
        """mode='single' → SingleStrategy."""
        # SingleStrategy.execute будет вызван через event_bus
        from codelab.server.agent.contracts.base import (
            AgentResponse,
            TokenUsage,
        )

        dispatcher._event_bus.send_request = AsyncMock(
            return_value=AgentResponse(
                request_id="r1",
                text="Response",
                usage=TokenUsage(10, 5, 15),
                stop_reason="end_turn",
                agent_name="primary",
                session_id="s1",
            )
        )

        result = await dispatcher.execute(
            session=mock_session,
            prompt="Hello",
        )

        assert result.text == "Response"
        assert result.stop_reason == "end_turn"

    @pytest.mark.asyncio
    async def test_execute_resolves_mode_from_session_config(
        self, dispatcher, mock_session
    ):
        """Режим берётся из session.config_values['mode']."""
        mock_session.config_values = {"mode": "single"}

        from codelab.server.agent.contracts.base import (
            AgentResponse,
            TokenUsage,
        )

        dispatcher._event_bus.send_request = AsyncMock(
            return_value=AgentResponse(
                request_id="r1",
                text="OK",
                usage=TokenUsage(0, 0, 0),
                stop_reason="end_turn",
            )
        )

        await dispatcher.execute(session=mock_session, prompt="test")

        # SingleStrategy была вызвана (event_bus.send_request был вызван)
        dispatcher._event_bus.send_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_uses_default_mode_if_not_in_config(
        self, dispatcher, mock_session
    ):
        """Если mode нет в config — используется default_mode."""
        mock_session.config_values = {}  # нет mode

        from codelab.server.agent.contracts.base import (
            AgentResponse,
            TokenUsage,
        )

        dispatcher._event_bus.send_request = AsyncMock(
            return_value=AgentResponse(
                request_id="r1",
                text="OK",
                usage=TokenUsage(0, 0, 0),
                stop_reason="end_turn",
            )
        )

        await dispatcher.execute(session=mock_session, prompt="test")

        dispatcher._event_bus.send_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_raises_for_unimplemented_mode(
        self, dispatcher, mock_session
    ):
        """Не реализованные режимы → NotImplementedError."""
        mock_session.config_values = {"mode": "multi_orchestrated"}

        with pytest.raises(NotImplementedError, match="not yet implemented"):
            await dispatcher.execute(session=mock_session, prompt="test")

    @pytest.mark.asyncio
    async def test_execute_raises_for_unknown_mode(
        self, dispatcher, mock_session
    ):
        """Неизвестный режим → ValueError."""
        mock_session.config_values = {"mode": "unknown_mode"}

        with pytest.raises(ValueError, match="Unknown execution mode"):
            await dispatcher.execute(session=mock_session, prompt="test")


class TestContinueExecution:
    """Тесты continue_execution."""

    @pytest.mark.asyncio
    async def test_continue_dispatches_to_strategy(
        self, dispatcher, mock_session
    ):
        """continue_execution делегирует стратегии."""
        from codelab.server.agent.contracts.base import (
            AgentResponse,
            TokenUsage,
        )

        dispatcher._event_bus.send_request = AsyncMock(
            return_value=AgentResponse(
                request_id="r1",
                text="Continued",
                usage=TokenUsage(5, 3, 8),
                stop_reason="end_turn",
            )
        )

        result = await dispatcher.continue_execution(session=mock_session)

        assert result.text == "Continued"


class TestModeSupport:
    """Тесты проверки поддержки режимов."""

    def test_get_registered_modes(self, dispatcher):
        """Возвращает список зарегистрированных режимов."""
        modes = dispatcher.get_registered_modes()
        assert "single" in modes

    def test_is_mode_supported_single(self, dispatcher):
        """mode='single' поддерживается."""
        assert dispatcher.is_mode_supported("single") is True

    def test_is_mode_supported_unimplemented(self, dispatcher):
        """Не реализованные режимы не поддерживаются."""
        assert dispatcher.is_mode_supported("multi_orchestrated") is False
        assert dispatcher.is_mode_supported("multi_choreographed") is False
        assert dispatcher.is_mode_supported("hierarchical") is False


class TestInitialization:
    """Тесты инициализации."""

    def test_default_mode_is_single(self, mock_event_bus, mock_execution_engine):
        """По умолчанию режим — single."""
        dispatcher = StrategyDispatcher(
            event_bus=mock_event_bus,
            execution_engine=mock_execution_engine,
        )
        assert dispatcher._default_mode == "single"

    def test_custom_default_mode(self, mock_event_bus, mock_execution_engine):
        """Можно задать кастомный default_mode."""
        dispatcher = StrategyDispatcher(
            event_bus=mock_event_bus,
            execution_engine=mock_execution_engine,
            default_mode="single",
        )
        assert dispatcher._default_mode == "single"

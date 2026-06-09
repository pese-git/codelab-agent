"""Тесты для StrategyDispatcher."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.agent.event_bus.bus import AgentEventBus
from codelab.server.agent.execution_engine import ExecutionEngine
from codelab.server.agent.registry import AgentRegistry
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
def mock_agent_registry():
    registry = MagicMock(spec=AgentRegistry)
    registry.get_all.return_value = {}
    registry.get_primary_agents.return_value = {}
    registry.get.return_value = None
    return registry


@pytest.fixture
def dispatcher(mock_event_bus, mock_execution_engine, mock_tracer, mock_agent_registry):
    return StrategyDispatcher(
        event_bus=mock_event_bus,
        execution_engine=mock_execution_engine,
        agent_registry=mock_agent_registry,
        tracer=mock_tracer,
        strategy="single",
    )


@pytest.fixture
def mock_session():
    session = MagicMock(spec=SessionState)
    session.session_id = "s1"
    session.config_values = {"_agent": "primary"}
    return session


class TestExecute:
    """Тесты execute — маршрутизация по strategy."""

    @pytest.mark.asyncio
    async def test_execute_dispatches_to_single_strategy(
        self, dispatcher, mock_session, mock_agent_registry
    ):
        """strategy='single' → SingleStrategy."""
        # SingleStrategy.execute будет вызван через event_bus
        from codelab.server.agent.contracts.base import (
            AgentResponse,
            TokenUsage,
        )
        from codelab.server.agent.config.models import AgentMode, ResolvedAgent

        # Настроим registry чтобы возвращал агента
        mock_agent_registry.get.return_value = ResolvedAgent(
            name="primary",
            mode=AgentMode.PRIMARY,
            model="openai/gpt-4o",
        )

        dispatcher._event_bus.send_request = AsyncMock(
            return_value=AgentResponse(
                request_id="r1",
                text="Response",
                usage=TokenUsage(10, 5, 15),
                stop_reason="end_turn",
            )
        )

        result = await dispatcher.execute(mock_session, "Hello")

        assert result.text == "Response"
        assert dispatcher._event_bus.send_request.called

    @pytest.mark.asyncio
    async def test_execute_resolves_agent_from_session_config(
        self, dispatcher, mock_session, mock_agent_registry
    ):
        """agent_name из session.config_values['_agent']."""
        from codelab.server.agent.contracts.base import (
            AgentResponse,
            TokenUsage,
        )
        from codelab.server.agent.config.models import AgentMode, ResolvedAgent

        mock_session.config_values = {"_agent": "coder"}
        mock_agent_registry.get.return_value = ResolvedAgent(
            name="coder",
            mode=AgentMode.PRIMARY,
            model="openai/gpt-4o",
        )

        dispatcher._event_bus.send_request = AsyncMock(
            return_value=AgentResponse(
                request_id="r1",
                text="Response",
                usage=TokenUsage(10, 5, 15),
                stop_reason="end_turn",
            )
        )

        await dispatcher.execute(mock_session, "Hello")

        # Проверяем что запрос был отправлен к правильному агенту
        call_args = dispatcher._event_bus.send_request.call_args
        request = call_args.kwargs["request"]
        assert request.target_agent == "coder"

    @pytest.mark.asyncio
    async def test_execute_uses_default_agent_if_not_in_config(
        self, dispatcher, mock_session, mock_agent_registry
    ):
        """Если _agent не указан, используется default agent из registry."""
        from codelab.server.agent.contracts.base import (
            AgentResponse,
            TokenUsage,
        )
        from codelab.server.agent.config.models import AgentMode, ResolvedAgent

        mock_session.config_values = {}  # нет _agent
        mock_agent_registry.get_primary_agents.return_value = {
            "coder": ResolvedAgent(
                name="coder",
                mode=AgentMode.PRIMARY,
                model="openai/gpt-4o",
                priority=1,
            )
        }
        mock_agent_registry.get.return_value = ResolvedAgent(
            name="coder",
            mode=AgentMode.PRIMARY,
            model="openai/gpt-4o",
        )

        dispatcher._event_bus.send_request = AsyncMock(
            return_value=AgentResponse(
                request_id="r1",
                text="Response",
                usage=TokenUsage(10, 5, 15),
                stop_reason="end_turn",
            )
        )

        await dispatcher.execute(mock_session, "Hello")

        call_args = dispatcher._event_bus.send_request.call_args
        request = call_args.kwargs["request"]
        assert request.target_agent == "coder"

    @pytest.mark.asyncio
    async def test_execute_raises_for_unimplemented_strategy(self, dispatcher, mock_session):
        """strategy='multi_orchestrated' → NotImplementedError."""
        dispatcher._strategy_name = "multi_orchestrated"

        with pytest.raises(NotImplementedError, match="not yet implemented"):
            await dispatcher.execute(mock_session, "Hello")

    @pytest.mark.asyncio
    async def test_execute_raises_for_unknown_strategy(self, dispatcher, mock_session):
        """strategy='unknown' → ValueError."""
        dispatcher._strategy_name = "unknown"

        with pytest.raises(ValueError, match="Unknown strategy"):
            await dispatcher.execute(mock_session, "Hello")

    @pytest.mark.asyncio
    async def test_execute_raises_for_agent_not_found(
        self, dispatcher, mock_session, mock_agent_registry
    ):
        """Агент не найден в registry → ValueError."""
        mock_agent_registry.get.return_value = None  # агент не найден

        with pytest.raises(ValueError, match="not found in registry"):
            await dispatcher.execute(mock_session, "Hello")


class TestContinueExecution:
    """Тесты continue_execution."""

    @pytest.mark.asyncio
    async def test_continue_dispatches_to_strategy(
        self, dispatcher, mock_session, mock_agent_registry
    ):
        """continue_execution вызывает strategy.continue_execution."""
        from codelab.server.agent.contracts.base import (
            AgentResponse,
            TokenUsage,
        )
        from codelab.server.agent.config.models import AgentMode, ResolvedAgent

        mock_agent_registry.get.return_value = ResolvedAgent(
            name="primary",
            mode=AgentMode.PRIMARY,
            model="openai/gpt-4o",
        )

        dispatcher._event_bus.send_request = AsyncMock(
            return_value=AgentResponse(
                request_id="r1",
                text="Continued",
                usage=TokenUsage(5, 3, 8),
                stop_reason="end_turn",
            )
        )

        result = await dispatcher.continue_execution(mock_session)

        assert result.text == "Continued"


class TestStrategySupport:
    """Тесты поддержки стратегий."""

    def test_get_registered_strategies(self, dispatcher):
        """get_registered_strategies() возвращает список стратегий."""
        strategies = dispatcher.get_registered_strategies()
        assert "single" in strategies

    def test_is_strategy_supported_single(self, dispatcher):
        """is_strategy_supported('single') → True."""
        assert dispatcher.is_strategy_supported("single") is True

    def test_is_strategy_supported_unimplemented(self, dispatcher):
        """is_strategy_supported('multi_orchestrated') → False."""
        assert dispatcher.is_strategy_supported("multi_orchestrated") is False


class TestSetStrategy:
    """Тесты set_strategy — runtime override."""

    def test_set_strategy_single(self, dispatcher):
        """set_strategy('single') меняет текущую стратегию."""
        dispatcher.set_strategy("single")
        assert dispatcher.get_strategy() == "single"

    def test_set_strategy_unknown_raises(self, dispatcher):
        """set_strategy('unknown') → ValueError."""
        with pytest.raises(ValueError, match="Unknown strategy"):
            dispatcher.set_strategy("unknown")

    def test_set_strategy_unimplemented_raises(self, dispatcher):
        """set_strategy('multi_orchestrated') → ValueError (не зарегистрирована)."""
        with pytest.raises(ValueError, match="Unknown strategy"):
            dispatcher.set_strategy("multi_orchestrated")


class TestInitialization:
    """Тесты инициализации."""

    def test_default_strategy_is_single(
        self, mock_event_bus, mock_execution_engine, mock_tracer, mock_agent_registry
    ):
        """По умолчанию strategy='single'."""
        dispatcher = StrategyDispatcher(
            event_bus=mock_event_bus,
            execution_engine=mock_execution_engine,
            agent_registry=mock_agent_registry,
            tracer=mock_tracer,
        )
        assert dispatcher.get_strategy() == "single"

    def test_custom_strategy(
        self, mock_event_bus, mock_execution_engine, mock_tracer, mock_agent_registry
    ):
        """Можно установить custom strategy."""
        dispatcher = StrategyDispatcher(
            event_bus=mock_event_bus,
            execution_engine=mock_execution_engine,
            agent_registry=mock_agent_registry,
            tracer=mock_tracer,
            strategy="single",
        )
        assert dispatcher.get_strategy() == "single"

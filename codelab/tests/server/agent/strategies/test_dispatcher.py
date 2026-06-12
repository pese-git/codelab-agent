"""Тесты для StrategyDispatcher с StrategyRegistry."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from codelab.server.agent.strategies.descriptor import (
    StrategyDependencies,
    StrategyDescriptor,
)
from codelab.server.agent.strategies.dispatcher import StrategyDispatcher
from codelab.server.agent.strategies.registry import StrategyRegistry


class TestStrategyDispatcherSelectStrategy:
    """Тесты для select_strategy."""

    def _create_dispatcher(
        self,
        available_strategies: list[str] | None = None,
    ) -> StrategyDispatcher:
        """Создать dispatcher с mocked registry."""
        # Создаём mock registry
        strategy_registry = MagicMock(spec=StrategyRegistry)
        agent_registry = MagicMock()

        # Создаём descriptors для доступных стратегий
        if available_strategies is None:
            available_strategies = ["single"]

        descriptors = []
        for name in available_strategies:
            descriptor = MagicMock(spec=StrategyDescriptor)
            descriptor.name = name
            descriptors.append(descriptor)

        strategy_registry.get_available.return_value = descriptors

        # Создаём dependencies
        deps = MagicMock(spec=StrategyDependencies)

        return StrategyDispatcher(
            strategy_registry=strategy_registry,
            agent_registry=agent_registry,
            strategy_dependencies=deps,
            default_strategy="single",
            fallback_strategy="single",
        )

    def test_select_strategy_priority_slash_command(self) -> None:
        """Slash command имеет высший приоритет."""
        dispatcher = self._create_dispatcher(["single", "hierarchical"])

        session = MagicMock()
        session.session_id = "test-session"
        session.config_values = {"_active_strategy": "hierarchical"}

        context_meta = {"active_strategy": "single"}

        strategy_name, fallback_from = dispatcher.select_strategy(session, context_meta)

        assert strategy_name == "single"
        assert fallback_from is None

    def test_select_strategy_priority_config_values(self) -> None:
        """config_values имеет второй приоритет."""
        dispatcher = self._create_dispatcher(["single", "hierarchical"])

        session = MagicMock()
        session.session_id = "test-session"
        session.config_values = {"_active_strategy": "hierarchical"}

        strategy_name, fallback_from = dispatcher.select_strategy(session, context_meta=None)

        assert strategy_name == "hierarchical"
        assert fallback_from is None

    def test_select_strategy_priority_default(self) -> None:
        """Default strategy используется когда нет override."""
        dispatcher = self._create_dispatcher(["single"])

        session = MagicMock()
        session.session_id = "test-session"
        session.config_values = {}

        strategy_name, fallback_from = dispatcher.select_strategy(session, context_meta=None)

        assert strategy_name == "single"
        assert fallback_from is None

    def test_select_strategy_fallback_when_unavailable(self) -> None:
        """Fallback когда запрошенная стратегия недоступна."""
        dispatcher = self._create_dispatcher(["single"])

        session = MagicMock()
        session.session_id = "test-session"
        session.config_values = {"_active_strategy": "hierarchical"}

        strategy_name, fallback_from = dispatcher.select_strategy(session, context_meta=None)

        assert strategy_name == "single"
        assert fallback_from == "hierarchical"

    def test_select_strategy_fallback_chain(self) -> None:
        """Fallback chain когда fallback тоже недоступен."""
        # Только "single" доступна
        strategy_registry = MagicMock(spec=StrategyRegistry)
        agent_registry = MagicMock()

        single_descriptor = MagicMock(spec=StrategyDescriptor)
        single_descriptor.name = "single"
        strategy_registry.get_available.return_value = [single_descriptor]

        deps = MagicMock(spec=StrategyDependencies)

        dispatcher = StrategyDispatcher(
            strategy_registry=strategy_registry,
            agent_registry=agent_registry,
            strategy_dependencies=deps,
            default_strategy="hierarchical",  # недоступна
            fallback_strategy="multi_orchestrated",  # тоже недоступна
        )

        session = MagicMock()
        session.session_id = "test-session"
        session.config_values = {}

        strategy_name, fallback_from = dispatcher.select_strategy(session, context_meta=None)

        # Должна выбрать первую доступную
        assert strategy_name == "single"
        assert fallback_from == "hierarchical"

    def test_select_strategy_empty_available_uses_hardcoded_fallback(self) -> None:
        """Когда нет доступных стратегий, используется hardcoded fallback."""
        strategy_registry = MagicMock(spec=StrategyRegistry)
        agent_registry = MagicMock()
        strategy_registry.get_available.return_value = []

        deps = MagicMock(spec=StrategyDependencies)

        dispatcher = StrategyDispatcher(
            strategy_registry=strategy_registry,
            agent_registry=agent_registry,
            strategy_dependencies=deps,
            default_strategy="single",
            fallback_strategy="single",
        )

        session = MagicMock()
        session.session_id = "test-session"
        session.config_values = {}

        strategy_name, fallback_from = dispatcher.select_strategy(session, context_meta=None)

        # Когда нет доступных стратегий, requested == fallback, поэтому fallback_from == requested
        assert strategy_name == "single"
        assert fallback_from == "single"  # requested was "single", but it wasn't available


class TestStrategyDispatcherCurrentStrategy:
    """Тесты для get/set current strategy."""

    def test_get_current_strategy(self) -> None:
        """get_current_strategy создаёт экземпляр через registry."""
        strategy_registry = MagicMock(spec=StrategyRegistry)
        agent_registry = MagicMock()
        strategy_registry.get_available.return_value = []

        mock_strategy = MagicMock()
        strategy_registry.create_instance.return_value = mock_strategy

        deps = MagicMock(spec=StrategyDependencies)

        dispatcher = StrategyDispatcher(
            strategy_registry=strategy_registry,
            agent_registry=agent_registry,
            strategy_dependencies=deps,
            default_strategy="single",
            fallback_strategy="single",
        )

        strategy = dispatcher.get_current_strategy()

        assert strategy is mock_strategy
        strategy_registry.create_instance.assert_called_once_with("single", deps)

    def test_set_current_strategy_success(self) -> None:
        """set_current_strategy устанавливает стратегию."""
        strategy_registry = MagicMock(spec=StrategyRegistry)
        agent_registry = MagicMock()

        descriptor = MagicMock(spec=StrategyDescriptor)
        descriptor.name = "hierarchical"
        strategy_registry.get.return_value = descriptor

        deps = MagicMock(spec=StrategyDependencies)

        dispatcher = StrategyDispatcher(
            strategy_registry=strategy_registry,
            agent_registry=agent_registry,
            strategy_dependencies=deps,
            default_strategy="single",
            fallback_strategy="single",
        )

        result = dispatcher.set_current_strategy("hierarchical")

        assert result is True
        assert dispatcher.get_strategy() == "hierarchical"

    def test_set_current_strategy_not_found(self) -> None:
        """set_current_strategy возвращает False если стратегия не найдена."""
        strategy_registry = MagicMock(spec=StrategyRegistry)
        agent_registry = MagicMock()
        strategy_registry.get.return_value = None

        deps = MagicMock(spec=StrategyDependencies)

        dispatcher = StrategyDispatcher(
            strategy_registry=strategy_registry,
            agent_registry=agent_registry,
            strategy_dependencies=deps,
            default_strategy="single",
            fallback_strategy="single",
        )

        result = dispatcher.set_current_strategy("nonexistent")

        assert result is False
        assert dispatcher.get_strategy() == "single"


class TestStrategyDispatcherAvailableStrategies:
    """Тесты для get_available_strategies."""

    def test_get_available_strategies(self) -> None:
        """get_available_strategies возвращает список доступных."""
        strategy_registry = MagicMock(spec=StrategyRegistry)
        agent_registry = MagicMock()

        descriptor1 = MagicMock(spec=StrategyDescriptor)
        descriptor1.name = "single"
        descriptor2 = MagicMock(spec=StrategyDescriptor)
        descriptor2.name = "hierarchical"

        strategy_registry.get_available.return_value = [descriptor1, descriptor2]

        deps = MagicMock(spec=StrategyDependencies)

        dispatcher = StrategyDispatcher(
            strategy_registry=strategy_registry,
            agent_registry=agent_registry,
            strategy_dependencies=deps,
            default_strategy="single",
            fallback_strategy="single",
        )

        available = dispatcher.get_available_strategies()

        assert available == ["single", "hierarchical"]

    def test_is_strategy_available(self) -> None:
        """is_strategy_available проверяет доступность."""
        strategy_registry = MagicMock(spec=StrategyRegistry)
        agent_registry = MagicMock()

        descriptor = MagicMock(spec=StrategyDescriptor)
        descriptor.name = "single"
        strategy_registry.get_available.return_value = [descriptor]

        deps = MagicMock(spec=StrategyDependencies)

        dispatcher = StrategyDispatcher(
            strategy_registry=strategy_registry,
            agent_registry=agent_registry,
            strategy_dependencies=deps,
            default_strategy="single",
            fallback_strategy="single",
        )

        assert dispatcher.is_strategy_available("single") is True
        assert dispatcher.is_strategy_available("hierarchical") is False


class TestStrategyDispatcherFallbackNotification:
    """Тесты для build_fallback_notification."""

    def test_build_fallback_notification_format(self) -> None:
        """build_fallback_notification создаёт правильное сообщение."""
        notification = StrategyDispatcher.build_fallback_notification(
            session_id="test-session",
            requested="multi_orchestrated",
            actual="single",
            reason="no orchestrator",
        )

        assert notification.method == "session/update"
        assert notification.params is not None
        assert notification.params["sessionId"] == "test-session"
        assert notification.params["update"]["sessionUpdate"] == "agent_message_chunk"

        content = notification.params["update"]["content"]
        assert content["type"] == "text"
        assert "multi_orchestrated" in content["text"]
        assert "single" in content["text"]
        assert "no orchestrator" in content["text"]


class TestStrategyDispatcherLLMCallStrategy:
    """Тесты для LLMCallStrategy Protocol."""

    @pytest.mark.asyncio
    async def test_execute_delegates_to_strategy(self) -> None:
        """execute делегирует выполнение стратегии."""
        from unittest.mock import AsyncMock
        
        strategy_registry = MagicMock(spec=StrategyRegistry)
        agent_registry = MagicMock()

        # Настраиваем доступные стратегии
        descriptor = MagicMock(spec=StrategyDescriptor)
        descriptor.name = "single"
        strategy_registry.get_available.return_value = [descriptor]

        # Настраиваем mock стратегию с AsyncMock для async методов
        mock_strategy = MagicMock()
        mock_response = MagicMock()
        mock_strategy.execute = AsyncMock(return_value=mock_response)
        strategy_registry.create_instance.return_value = mock_strategy

        # Настраиваем agent_registry
        primary_agent = MagicMock()
        primary_agent.name = "primary"
        agent_registry.get_primary_agents.return_value = {"primary": primary_agent}

        # Используем обычный MagicMock без spec чтобы можно было обращаться к атрибутам
        deps = MagicMock()
        deps.event_bus = MagicMock()
        deps.execution_engine = MagicMock()
        deps.tracer = None
        deps.agent_name = "primary"

        dispatcher = StrategyDispatcher(
            strategy_registry=strategy_registry,
            agent_registry=agent_registry,
            strategy_dependencies=deps,
            default_strategy="single",
            fallback_strategy="single",
        )

        session = MagicMock()
        session.session_id = "test-session"
        session.config_values = {}

        result = await dispatcher.execute(session, "test prompt")

        assert result is mock_response
        mock_strategy.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_continue_execution_delegates_to_strategy(self) -> None:
        """continue_execution делегирует выполнение стратегии."""
        from unittest.mock import AsyncMock
        
        strategy_registry = MagicMock(spec=StrategyRegistry)
        agent_registry = MagicMock()

        # Настраиваем mock стратегию с AsyncMock для async методов
        mock_strategy = MagicMock()
        mock_response = MagicMock()
        mock_strategy.continue_execution = AsyncMock(return_value=mock_response)
        strategy_registry.create_instance.return_value = mock_strategy

        # Настраиваем agent_registry
        primary_agent = MagicMock()
        primary_agent.name = "primary"
        agent_registry.get_primary_agents.return_value = {"primary": primary_agent}

        # Используем обычный MagicMock без spec чтобы можно было обращаться к атрибутам
        deps = MagicMock()
        deps.event_bus = MagicMock()
        deps.execution_engine = MagicMock()
        deps.tracer = None
        deps.agent_name = "primary"

        dispatcher = StrategyDispatcher(
            strategy_registry=strategy_registry,
            agent_registry=agent_registry,
            strategy_dependencies=deps,
            default_strategy="single",
            fallback_strategy="single",
        )

        session = MagicMock()
        session.session_id = "test-session"
        session.config_values = {}

        result = await dispatcher.continue_execution(session)

        assert result is mock_response
        mock_strategy.continue_execution.assert_called_once()

    @pytest.mark.asyncio
    async def test_continue_execution_selects_default_when_strategy_not_set(self) -> None:
        """continue_execution выбирает дефолтную стратегию если _current_strategy_name = None."""
        from unittest.mock import AsyncMock

        strategy_registry = MagicMock(spec=StrategyRegistry)
        agent_registry = MagicMock()

        # Настраиваем descriptor
        mock_descriptor = MagicMock(spec=StrategyDescriptor)
        mock_descriptor.name = "single"
        strategy_registry.get_available.return_value = [mock_descriptor]
        strategy_registry.get.return_value = mock_descriptor

        # Настраиваем mock стратегию
        mock_strategy = MagicMock()
        mock_response = MagicMock()
        mock_strategy.continue_execution = AsyncMock(return_value=mock_response)
        strategy_registry.create_instance.return_value = mock_strategy

        # Настраиваем agent_registry
        primary_agent = MagicMock()
        primary_agent.name = "primary"
        agent_registry.get_primary_agents.return_value = {"primary": primary_agent}

        deps = MagicMock()
        deps.event_bus = MagicMock()
        deps.execution_engine = MagicMock()
        deps.tracer = None
        deps.agent_name = "primary"

        dispatcher = StrategyDispatcher(
            strategy_registry=strategy_registry,
            agent_registry=agent_registry,
            strategy_dependencies=deps,
            default_strategy="single",
            fallback_strategy="single",
        )

        # Сбрасываем _current_strategy_name в None
        dispatcher._current_strategy_name = None

        session = MagicMock()
        session.session_id = "test-session"
        session.config_values = {}

        result = await dispatcher.continue_execution(session)

        assert result is mock_response
        # Стратегия должна быть выбрана автоматически
        assert dispatcher._current_strategy_name == "single"
        mock_strategy.continue_execution.assert_called_once()

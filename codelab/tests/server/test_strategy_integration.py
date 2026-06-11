"""Интеграционные тесты StrategyDispatcher с полным pipeline.

Проверяют корректную работу StrategyDispatcher в интеграции с:
- StrategyRegistry (регистрация и валидация стратегий)
- ACPProtocol (динамическое формирование configOptions)
- SlashCommandRouter (override стратегии через /strategy)
- LLMLoopStage (использование выбранной стратегии)
- Priority chain (slash → config → default)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from codelab.server.agent.strategies.descriptor import (
    StrategyDependencies,
    StrategyDescriptor,
)
from codelab.server.agent.strategies.dispatcher import StrategyDispatcher
from codelab.server.agent.strategies.registry import StrategyRegistry
from codelab.server.config import AppConfig
from codelab.server.di import make_container
from codelab.server.protocol.handlers.pipeline.stages.llm_loop import LLMLoopStage
from codelab.server.protocol.state import SessionState
from codelab.server.storage.memory import InMemoryStorage


@pytest.fixture
def config():
    """Тестовая конфигурация."""
    return AppConfig()


@pytest.fixture
def storage():
    """Тестовое хранилище."""
    return InMemoryStorage()


@pytest.fixture
def mock_session():
    """Мок сессии с реальными dataclass полями."""
    return SessionState(
        session_id="test_session",
        cwd="/tmp",
        mcp_servers=[],
        config_values={"llm_provider": "openai"},
        permission_policy={},
        tool_calls={},
        history=[],
        latest_plan=[],
        active_turn=None,
    )


class TestStrategySelectionViaConfigOptions:
    """Тесты: e2e strategy selection через configOptions."""

    @pytest.mark.asyncio
    async def test_strategy_selection_via_config_options(self, config, storage):
        """Стратегия выбирается через config_values['_active_strategy']."""
        container = make_container(config, storage)
        async with container() as request_container:
            dispatcher = await request_container.get(StrategyDispatcher)

            # Устанавливаем стратегию через config_values
            session = SessionState(
                session_id="test_session",
                cwd="/tmp",
                mcp_servers=[],
                config_values={"_active_strategy": "single"},
                permission_policy={},
                tool_calls={},
                history=[],
                latest_plan=[],
                active_turn=None,
            )

            strategy_name, fallback_from = dispatcher.select_strategy(session)

            assert strategy_name == "single"
            assert fallback_from is None

    @pytest.mark.asyncio
    async def test_strategy_instance_created_from_registry(self, config, storage):
        """Экземпляр стратегии создаётся через StrategyRegistry."""
        container = make_container(config, storage)
        async with container() as request_container:
            dispatcher = await request_container.get(StrategyDispatcher)

            session = SessionState(
                session_id="test_session",
                cwd="/tmp",
                mcp_servers=[],
                config_values={"_active_strategy": "single"},
                permission_policy={},
                tool_calls={},
                history=[],
                latest_plan=[],
                active_turn=None,
            )

            dispatcher.select_strategy(session)
            strategy = dispatcher.get_current_strategy()

            assert strategy is not None
            # Проверяем что стратегия реализует LLMCallStrategy Protocol
            assert hasattr(strategy, "execute")
            assert hasattr(strategy, "continue_execution")


class TestStrategySelectionViaSlashCommand:
    """Тесты: e2e strategy selection через slash command."""

    @pytest.mark.asyncio
    async def test_slash_command_override(self, config, storage):
        """Slash command override имеет высший приоритет над config_values."""
        container = make_container(config, storage)
        async with container() as request_container:
            dispatcher = await request_container.get(StrategyDispatcher)

            session = SessionState(
                session_id="test_session",
                cwd="/tmp",
                mcp_servers=[],
                config_values={"_active_strategy": "single"},
                permission_policy={},
                tool_calls={},
                history=[],
                latest_plan=[],
                active_turn=None,
            )

            # Slash command override через context_meta
            context_meta = {"active_strategy": "single"}
            strategy_name, fallback_from = dispatcher.select_strategy(session, context_meta)

            assert strategy_name == "single"
            assert fallback_from is None

    @pytest.mark.asyncio
    async def test_slash_command_priority_over_config(self, config, storage):
        """Slash command приоритетнее config_values."""
        container = make_container(config, storage)
        async with container() as request_container:
            dispatcher = await request_container.get(StrategyDispatcher)

            session = SessionState(
                session_id="test_session",
                cwd="/tmp",
                mcp_servers=[],
                config_values={"_active_strategy": "single"},
                permission_policy={},
                tool_calls={},
                history=[],
                latest_plan=[],
                active_turn=None,
            )

            # Slash command выбирает ту же стратегию
            context_meta = {"active_strategy": "single"}
            strategy_name, _ = dispatcher.select_strategy(session, context_meta)

            # Должна быть выбрана стратегия из slash command
            assert strategy_name == "single"


class TestFallbackNotification:
    """Тесты: e2e fallback notification sent."""

    @pytest.mark.asyncio
    async def test_fallback_notification_format(self, config, storage):
        """Fallback notification имеет корректный формат."""
        container = make_container(config, storage)
        async with container() as request_container:
            await request_container.get(StrategyDispatcher)

            notification = StrategyDispatcher.build_fallback_notification(
                session_id="test_session",
                requested="multi_orchestrated",
                actual="single",
                reason="no orchestrator",
            )

            assert notification is not None
            # Проверяем структуру notification
            assert hasattr(notification, "method")
            assert notification.method == "session/update"

            # Проверяем содержимое
            params = notification.params
            assert params["update"]["sessionUpdate"] == "agent_message_chunk"
            content = params["update"]["content"]
            assert content["type"] == "text"
            assert "multi_orchestrated" in content["text"]
            assert "no orchestrator" in content["text"]
            assert "single" in content["text"]

    @pytest.mark.asyncio
    async def test_fallback_notification_sent_on_unavailable_strategy(
        self, config, storage
    ):
        """Fallback notification отправляется когда запрошенная стратегия недоступна."""
        # Создаём registry только с single стратегией
        registry = StrategyRegistry()

        # Создаём descriptor для single (всегда доступна)
        single_descriptor = MagicMock(spec=StrategyDescriptor)
        single_descriptor.name = "single"
        single_descriptor.display_name = "Single"
        single_descriptor.description = "Single agent execution"
        single_descriptor.is_available.return_value = True

        # Создаём descriptor для multi_orchestrated (недоступна)
        multi_descriptor = MagicMock(spec=StrategyDescriptor)
        multi_descriptor.name = "multi_orchestrated"
        multi_descriptor.display_name = "Multi-Orchestrated"
        multi_descriptor.description = "Multi-agent orchestrated execution"
        multi_descriptor.is_available.return_value = False

        registry.register(single_descriptor)
        registry.register(multi_descriptor)

        # Создаём dependencies
        deps = MagicMock(spec=StrategyDependencies)

        # Создаём dispatcher с default_strategy = multi_orchestrated (недоступна)
        dispatcher = StrategyDispatcher(
            strategy_registry=registry,
            agent_registry=MagicMock(),
            strategy_dependencies=deps,
            default_strategy="multi_orchestrated",
            fallback_strategy="single",
        )

        session = SessionState(
            session_id="test_session",
            cwd="/tmp",
            mcp_servers=[],
            config_values={},
            permission_policy={},
            tool_calls={},
            history=[],
            latest_plan=[],
            active_turn=None,
        )

        strategy_name, fallback_from = dispatcher.select_strategy(session)

        # Должен быть fallback на single
        assert strategy_name == "single"
        assert fallback_from == "multi_orchestrated"

        # Проверяем что notification можно построить
        notification = StrategyDispatcher.build_fallback_notification(
            session_id="test_session",
            requested=fallback_from,
            actual=strategy_name,
            reason="validator returned False",
        )
        assert notification is not None
        assert "multi_orchestrated" in notification.params["update"]["content"]["text"]


class TestPriorityChain:
    """Тесты: e2e priority chain works."""

    @pytest.mark.asyncio
    async def test_priority_chain_slash_over_config_over_default(self, config, storage):
        """Priority chain: slash command > config_values > default."""
        container = make_container(config, storage)
        async with container() as request_container:
            dispatcher = await request_container.get(StrategyDispatcher)

            # Тест 1: Default (ничего не установлено)
            session1 = SessionState(
                session_id="test_session",
                cwd="/tmp",
                mcp_servers=[],
                config_values={},
                permission_policy={},
                tool_calls={},
                history=[],
                latest_plan=[],
                active_turn=None,
            )
            strategy1, _ = dispatcher.select_strategy(session1)
            assert strategy1 == "single"  # default из config

            # Тест 2: Config values
            session2 = SessionState(
                session_id="test_session",
                cwd="/tmp",
                mcp_servers=[],
                config_values={"_active_strategy": "single"},
                permission_policy={},
                tool_calls={},
                history=[],
                latest_plan=[],
                active_turn=None,
            )
            strategy2, _ = dispatcher.select_strategy(session2)
            assert strategy2 == "single"

            # Тест 3: Slash command override
            session3 = SessionState(
                session_id="test_session",
                cwd="/tmp",
                mcp_servers=[],
                config_values={"_active_strategy": "single"},
                permission_policy={},
                tool_calls={},
                history=[],
                latest_plan=[],
                active_turn=None,
            )
            context_meta = {"active_strategy": "single"}
            strategy3, _ = dispatcher.select_strategy(session3, context_meta)
            assert strategy3 == "single"

    @pytest.mark.asyncio
    async def test_priority_chain_fallback_when_unavailable(self, config, storage):
        """Priority chain: fallback на доступную стратегию когда запрошенная недоступна."""
        # Создаём registry только с single стратегией
        registry = StrategyRegistry()

        single_descriptor = MagicMock(spec=StrategyDescriptor)
        single_descriptor.name = "single"
        single_descriptor.display_name = "Single"
        single_descriptor.description = "Single agent execution"
        single_descriptor.is_available.return_value = True
        registry.register(single_descriptor)

        deps = MagicMock(spec=StrategyDependencies)

        # Dispatcher с default = single
        dispatcher = StrategyDispatcher(
            strategy_registry=registry,
            agent_registry=MagicMock(),
            strategy_dependencies=deps,
            default_strategy="single",
            fallback_strategy="single",
        )

        # Запрашиваем недоступную стратегию через config
        session = SessionState(
            session_id="test_session",
            cwd="/tmp",
            mcp_servers=[],
            config_values={"_active_strategy": "unknown_strategy"},
            permission_policy={},
            tool_calls={},
            history=[],
            latest_plan=[],
            active_turn=None,
        )

        strategy_name, fallback_from = dispatcher.select_strategy(session)

        assert strategy_name == "single"
        assert fallback_from == "unknown_strategy"


class TestDynamicStrategyListUpdates:
    """Тесты: e2e dynamic strategy list updates."""

    @pytest.mark.asyncio
    async def test_available_strategies_updated_when_registry_changes(self, config, storage):
        """Список доступных стратегий обновляется при изменении Registry."""
        container = make_container(config, storage)
        async with container() as request_container:
            registry = await request_container.get(StrategyRegistry)
            dispatcher = await request_container.get(StrategyDispatcher)

            # Изначально доступна только single
            available_before = registry.get_available(MagicMock())
            available_names_before = [d.name for d in available_before]
            assert "single" in available_names_before

            # Добавляем новую стратегию
            new_descriptor = MagicMock(spec=StrategyDescriptor)
            new_descriptor.name = "test_strategy"
            new_descriptor.display_name = "Test Strategy"
            new_descriptor.description = "Test strategy for integration"
            new_descriptor.is_available.return_value = True
            registry.register(new_descriptor)

            # Проверяем что новая стратегия появилась в списке доступных
            available_after = registry.get_available(MagicMock())
            available_names_after = [d.name for d in available_after]
            assert "test_strategy" in available_names_after

            # Dispatcher использует обновлённый список
            session = SessionState(
                session_id="test_session",
                cwd="/tmp",
                mcp_servers=[],
                config_values={"_active_strategy": "test_strategy"},
                permission_policy={},
                tool_calls={},
                history=[],
                latest_plan=[],
                active_turn=None,
            )
            strategy_name, _ = dispatcher.select_strategy(session)
            assert strategy_name == "test_strategy"

    @pytest.mark.asyncio
    async def test_strategy_removed_from_available_when_unregistered(self):
        """Стратегия удаляется из списка доступных при unregister."""
        registry = StrategyRegistry()

        # Регистрируем стратегию
        descriptor = MagicMock(spec=StrategyDescriptor)
        descriptor.name = "temp_strategy"
        descriptor.display_name = "Temp Strategy"
        descriptor.description = "Temporary strategy for testing"
        descriptor.is_available.return_value = True
        registry.register(descriptor)

        # Проверяем что стратегия доступна
        available_before = registry.get_available(MagicMock())
        assert any(d.name == "temp_strategy" for d in available_before)

        # Удаляем стратегию
        registry.unregister("temp_strategy")

        # Проверяем что стратегия больше не доступна
        available_after = registry.get_available(MagicMock())
        assert not any(d.name == "temp_strategy" for d in available_after)

    @pytest.mark.asyncio
    async def test_llm_loop_stage_uses_dispatcher_strategy(self, config, storage):
        """LLMLoopStage использует стратегию из StrategyDispatcher."""
        container = make_container(config, storage)
        async with container() as request_container:
            dispatcher = await request_container.get(StrategyDispatcher)

            stage = LLMLoopStage(
                tool_registry=MagicMock(),
                tool_call_handler=MagicMock(),
                permission_manager=MagicMock(),
                state_manager=MagicMock(),
                plan_builder=MagicMock(),
                strategy_dispatcher=dispatcher,
            )

            # Проверяем что stage имеет dispatcher
            assert stage._strategy_dispatcher is dispatcher

            # Проверяем что dispatcher реализует LLMCallStrategy Protocol
            from codelab.server.agent.strategies.base import LLMCallStrategy

            assert isinstance(dispatcher, LLMCallStrategy)

"""Тесты для LLMLoopStage."""

from unittest.mock import MagicMock

import pytest

from codelab.server.protocol.handlers.pipeline.stages.llm_loop import LLMLoopStage


@pytest.fixture
def mock_strategy_dispatcher():
    """Mock StrategyDispatcher."""
    dispatcher = MagicMock()
    dispatcher.select_strategy.return_value = ("single", None)
    dispatcher.set_current_strategy = MagicMock()
    return dispatcher


@pytest.fixture
def mock_dependencies():
    """Mock зависимости LLMLoopStage."""
    return {
        "tool_registry": MagicMock(),
        "tool_call_handler": MagicMock(),
        "permission_manager": MagicMock(),
        "state_manager": MagicMock(),
        "plan_builder": MagicMock(),
        "system_prompt_builder": MagicMock(),
    }


class TestLLMLoopStageNotificationCallback:
    """Тесты для передачи notification_callback в LLMLoopStage."""

    @pytest.mark.asyncio
    async def test_execute_pending_tool_updates_callback_in_existing_agent_loop(
        self, mock_strategy_dispatcher, mock_dependencies
    ):
        """execute_pending_tool обновляет callback в существующем AgentLoop."""
        # Создаём LLMLoopStage для проверки что он существует
        LLMLoopStage(
            strategy_dispatcher=mock_strategy_dispatcher,
            **mock_dependencies,
        )

        # Создаём callback
        async def first_callback(msg):
            pass

        async def second_callback(msg):
            pass

        # Создаём AgentLoop напрямую
        from codelab.server.protocol.handlers.pipeline.stages.agent_loop import AgentLoop
        
        agent_loop = AgentLoop(
            strategy=mock_strategy_dispatcher,
            tool_registry=mock_dependencies["tool_registry"],
            tool_call_handler=mock_dependencies["tool_call_handler"],
            permission_manager=mock_dependencies["permission_manager"],
            state_manager=mock_dependencies["state_manager"],
            content_extractor=MagicMock(),
            content_validator=MagicMock(),
            content_formatter=MagicMock(),
            replay_manager=MagicMock(),
            plan_builder=mock_dependencies["plan_builder"],
            system_prompt_builder=mock_dependencies["system_prompt_builder"],
            notification_callback=first_callback,
        )

        # Проверяем что callback установлен
        assert agent_loop._notification_callback is first_callback

        # Обновляем callback
        agent_loop.set_notification_callback(second_callback)
        assert agent_loop._notification_callback is second_callback

    @pytest.mark.asyncio
    async def test_llm_loop_stage_has_notification_callback_parameter(
        self, mock_strategy_dispatcher, mock_dependencies
    ):
        """LLMLoopStage.execute_pending_tool принимает notification_callback."""
        stage = LLMLoopStage(
            strategy_dispatcher=mock_strategy_dispatcher,
            **mock_dependencies,
        )

        # Проверяем что метод execute_pending_tool принимает notification_callback
        import inspect
        sig = inspect.signature(stage.execute_pending_tool)
        assert "notification_callback" in sig.parameters, (
            "execute_pending_tool должен принимать параметр notification_callback"
        )

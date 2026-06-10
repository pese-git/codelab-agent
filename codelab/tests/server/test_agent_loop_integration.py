"""Интеграционные тесты AgentLoop с полным pipeline.

Проверяют корректную работу AgentLoop в интеграции с:
- LLMLoopStage (pipeline adapter)
- StrategyDispatcher (EventBus путь)
- LegacyCallStrategy (AgentOrchestrator путь)
- ToolRegistry и ToolCallHandler
- PermissionManager и permission flow
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.agent.base import AgentResponse
from codelab.server.agent.strategies.base import LLMCallStrategy
from codelab.server.agent.strategies.dispatcher import StrategyDispatcher
from codelab.server.agent.strategies.legacy_adapter import LegacyCallStrategy
from codelab.server.config import AppConfig
from codelab.server.di import make_container
from codelab.server.protocol.handlers.pipeline.stages.agent_loop import AgentLoop
from codelab.server.protocol.handlers.pipeline.stages.llm_loop import LLMLoopStage
from codelab.server.protocol.state import (
    ActiveTurnState,
    SessionState,
    ToolCallState,
)
from codelab.server.protocol.stop_reasons import StopReason
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


class TestAgentLoopWithDIContainer:
    """Тесты AgentLoop с DI контейнером."""

    @pytest.mark.asyncio
    async def test_agent_loop_created_from_container(self, config, storage):
        """AgentLoop можно создать через DI контейнер."""
        container = make_container(config, storage)
        async with container() as request_container:
            llm_loop_stage = await request_container.get(LLMLoopStage)
            assert llm_loop_stage is not None
            assert isinstance(llm_loop_stage, LLMLoopStage)

    @pytest.mark.asyncio
    async def test_strategy_dispatcher_implements_protocol(self, config, storage):
        """StrategyDispatcher реализует LLMCallStrategy Protocol."""
        container = make_container(config, storage)
        async with container() as request_container:
            dispatcher = await request_container.get(StrategyDispatcher)
            assert isinstance(dispatcher, LLMCallStrategy)


class TestAgentLoopEventBusPath:
    """Тесты AgentLoop через EventBus путь (StrategyDispatcher)."""

    @pytest.mark.asyncio
    async def test_full_cycle_with_tool_calls(self, mock_session):
        """Полный цикл: LLM → tool_calls → continue → завершение."""
        # Arrange
        mock_strategy = AsyncMock(spec=LLMCallStrategy)

        # Первый вызов: LLM запрашивает tool
        tool_call = MagicMock()
        tool_call.id = "call_1"
        tool_call.name = "test_tool"
        tool_call.arguments = {"input": "data"}

        first_response = MagicMock(spec=AgentResponse)
        first_response.text = "Вызываю инструмент..."
        first_response.tool_calls = [tool_call]
        first_response.plan = None

        # Второй вызов: LLM завершает
        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "Готово!"
        second_response.tool_calls = []
        second_response.plan = None

        mock_strategy.execute.return_value = first_response
        mock_strategy.continue_execution.return_value = second_response

        # Mock dependencies
        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = False
        mock_tool_def.kind = "other"

        mock_tool_registry = MagicMock()
        mock_tool_registry.get.return_value = mock_tool_def
        mock_tool_result = MagicMock()
        mock_tool_result.success = True
        mock_tool_result.output = "Tool result"
        mock_tool_result.error = None
        mock_tool_registry.execute_tool = AsyncMock(return_value=mock_tool_result)

        mock_tool_call_handler = MagicMock()
        mock_tool_call_handler.create_tool_call.return_value = "tc_1"
        mock_tool_call_handler.build_tool_call_notification.return_value = MagicMock()
        mock_tool_call_handler.build_tool_update_notification.return_value = MagicMock()

        mock_content_extractor = AsyncMock()
        mock_extracted = MagicMock()
        mock_extracted.content_items = []
        mock_content_extractor.extract_from_result.return_value = mock_extracted

        mock_session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="test_session",
            cancel_requested=False,
            phase="running",
            permission_tool_call_id=None,
        )

        loop = AgentLoop(
            strategy=mock_strategy,
            tool_registry=mock_tool_registry,
            tool_call_handler=mock_tool_call_handler,
            permission_manager=MagicMock(),
            state_manager=MagicMock(),
            content_extractor=mock_content_extractor,
            content_validator=MagicMock(),
            content_formatter=MagicMock(),
            replay_manager=MagicMock(),
            plan_builder=MagicMock(),
        )

        # Act
        result = await loop.run(mock_session, "test_session", "Сделай что-нибудь")

        # Assert
        assert result.stop_reason == StopReason.END_TURN
        assert result.text == "Готово!"
        mock_strategy.execute.assert_called_once()
        mock_strategy.continue_execution.assert_called_once()
        mock_tool_registry.execute_tool.assert_called_once()

        # Проверяем что tool result добавлен в историю
        assert len(mock_session.history) >= 2  # assistant tool_call + tool result


class TestAgentLoopLegacyPath:
    """Тесты AgentLoop через Legacy путь (LegacyCallStrategy)."""

    @pytest.mark.asyncio
    async def test_full_cycle_with_tool_calls(self, mock_session):
        """Полный цикл через LegacyCallStrategy."""
        # Arrange
        mock_orchestrator = AsyncMock()

        tool_call = MagicMock()
        tool_call.id = "call_1"
        tool_call.name = "legacy_tool"
        tool_call.arguments = {}

        first_response = MagicMock(spec=AgentResponse)
        first_response.text = ""
        first_response.tool_calls = [tool_call]
        first_response.plan = None

        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "Legacy done"
        second_response.tool_calls = []
        second_response.plan = None

        mock_orchestrator.process_prompt.return_value = first_response
        mock_orchestrator.continue_with_tool_results.return_value = second_response

        strategy = LegacyCallStrategy(mock_orchestrator)

        # Mock dependencies
        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = False
        mock_tool_def.kind = "other"

        mock_tool_registry = MagicMock()
        mock_tool_registry.get.return_value = mock_tool_def
        mock_tool_result = MagicMock()
        mock_tool_result.success = True
        mock_tool_result.output = "Legacy tool output"
        mock_tool_result.error = None
        mock_tool_registry.execute_tool = AsyncMock(return_value=mock_tool_result)

        mock_tool_call_handler = MagicMock()
        mock_tool_call_handler.create_tool_call.return_value = "tc_1"
        mock_tool_call_handler.build_tool_call_notification.return_value = MagicMock()
        mock_tool_call_handler.build_tool_update_notification.return_value = MagicMock()

        mock_content_extractor = AsyncMock()
        mock_extracted = MagicMock()
        mock_extracted.content_items = []
        mock_content_extractor.extract_from_result.return_value = mock_extracted

        loop = AgentLoop(
            strategy=strategy,
            tool_registry=mock_tool_registry,
            tool_call_handler=mock_tool_call_handler,
            permission_manager=MagicMock(),
            state_manager=MagicMock(),
            content_extractor=mock_content_extractor,
            content_validator=MagicMock(),
            content_formatter=MagicMock(),
            replay_manager=MagicMock(),
            plan_builder=MagicMock(),
        )

        # Act
        result = await loop.run(mock_session, "test_session", "Legacy test")

        # Assert
        assert result.stop_reason == StopReason.END_TURN
        assert result.text == "Legacy done"
        mock_orchestrator.process_prompt.assert_called_once()
        mock_orchestrator.continue_with_tool_results.assert_called_once()


class TestAgentLoopPermissionFlow:
    """Тесты permission flow через AgentLoop."""

    @pytest.mark.asyncio
    async def test_permission_pause_and_resume(self, mock_session):
        """Полный permission flow: pause → approve → resume → continue."""
        # Arrange
        mock_strategy = AsyncMock(spec=LLMCallStrategy)

        tool_call = MagicMock()
        tool_call.id = "call_1"
        tool_call.name = "dangerous_tool"
        tool_call.arguments = {}

        first_response = MagicMock(spec=AgentResponse)
        first_response.text = "Нужно разрешение"
        first_response.tool_calls = [tool_call]
        first_response.plan = None

        # После resume — LLM завершает
        final_response = MagicMock(spec=AgentResponse)
        final_response.text = "После разрешения"
        final_response.tool_calls = []
        final_response.plan = None

        mock_strategy.execute.return_value = first_response
        mock_strategy.continue_execution.return_value = final_response

        # Tool требует permission
        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = True
        mock_tool_def.kind = "terminal"

        mock_tool_registry = MagicMock()
        mock_tool_registry.get.return_value = mock_tool_def

        # Tool execution после permission
        mock_tool_result = MagicMock()
        mock_tool_result.success = True
        mock_tool_result.output = "Executed after permission"
        mock_tool_result.error = None
        mock_tool_registry.execute_tool = AsyncMock(return_value=mock_tool_result)

        mock_tool_call_handler = MagicMock()
        mock_tool_call_handler.create_tool_call.return_value = "tc_1"
        mock_tool_call_handler.build_tool_call_notification.return_value = MagicMock()
        mock_tool_call_handler.build_tool_update_notification.return_value = MagicMock()

        mock_permission_manager = MagicMock()
        mock_permission_manager.build_permission_request.return_value = MagicMock()

        mock_content_extractor = AsyncMock()
        mock_extracted = MagicMock()
        mock_extracted.content_items = []
        mock_content_extractor.extract_from_result.return_value = mock_extracted

        # Setup session with active turn
        mock_session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="test_session",
            cancel_requested=False,
            phase="running",
            permission_tool_call_id=None,
        )

        # Setup tool_call_state для resume
        mock_tool_call_state = ToolCallState(
            tool_call_id="tc_1",
            title="dangerous_tool",
            kind="terminal",
            tool_name="dangerous_tool",
            tool_arguments={},
            tool_call_id_from_llm="call_1",
            status="pending",
            result_content=[],
        )
        mock_session.tool_calls["tc_1"] = mock_tool_call_state

        loop = AgentLoop(
            strategy=mock_strategy,
            tool_registry=mock_tool_registry,
            tool_call_handler=mock_tool_call_handler,
            permission_manager=mock_permission_manager,
            state_manager=MagicMock(),
            content_extractor=mock_content_extractor,
            content_validator=MagicMock(),
            content_formatter=MagicMock(),
            replay_manager=MagicMock(),
            plan_builder=MagicMock(),
        )

        # Act 1: Запуск — должен приостановиться на permission
        result1 = await loop.run(mock_session, "test_session", "Выполни опасное")

        # Assert 1: Приостановка
        assert result1.pending_permission is True
        assert "tc_1" in result1.pending_tool_calls

        # Act 2: Resume после permission approval
        result2 = await loop.resume_after_permission(mock_session, "test_session", "tc_1")

        # Assert 2: Завершение
        assert result2.stop_reason == StopReason.END_TURN
        assert result2.text == "После разрешения"
        mock_tool_registry.execute_tool.assert_called_once()
        mock_strategy.continue_execution.assert_called_once()


class TestAgentLoopCancellation:
    """Тесты cancellation в AgentLoop."""

    @pytest.mark.asyncio
    async def test_cancellation_during_tool_execution(self, mock_session):
        """Отмена во время выполнения tool calls."""
        # Arrange
        mock_strategy = AsyncMock(spec=LLMCallStrategy)

        tool_call = MagicMock()
        tool_call.id = "call_1"
        tool_call.name = "slow_tool"
        tool_call.arguments = {}

        response = MagicMock(spec=AgentResponse)
        response.text = ""
        response.tool_calls = [tool_call]
        response.plan = None

        mock_strategy.execute.return_value = response

        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = False
        mock_tool_def.kind = "other"

        mock_tool_registry = MagicMock()
        mock_tool_registry.get.return_value = mock_tool_def
        mock_tool_call_handler = MagicMock()
        mock_tool_call_handler.create_tool_call.return_value = "tc_1"
        mock_tool_call_handler.build_tool_call_notification.return_value = MagicMock()

        # Setup session — отмена запрашивается после первого вызова
        mock_session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="test_session",
            cancel_requested=False,
            phase="running",
            permission_tool_call_id=None,
        )

        loop = AgentLoop(
            strategy=mock_strategy,
            tool_registry=mock_tool_registry,
            tool_call_handler=mock_tool_call_handler,
            permission_manager=MagicMock(),
            state_manager=MagicMock(),
            content_extractor=AsyncMock(),
            content_validator=MagicMock(),
            content_formatter=MagicMock(),
            replay_manager=MagicMock(),
            plan_builder=MagicMock(),
        )

        # Устанавливаем cancel_requested после обработки tool_calls
        call_count = 0

        def cancel_after_tool_processing(session):
            nonlocal call_count
            call_count += 1
            return call_count > 2

        loop._is_cancel_requested = cancel_after_tool_processing

        # Act
        result = await loop.run(mock_session, "test_session", "Начни")

        # Assert
        assert result.stop_reason == StopReason.CANCELLED


class TestAgentLoopMaxTurnRequests:
    """Тесты ограничения max_turn_requests."""

    @pytest.mark.asyncio
    async def test_max_turn_requests_stops_loop(self, mock_session):
        """Цикл останавливается при достижении max_turn_requests."""
        # Arrange
        mock_strategy = AsyncMock(spec=LLMCallStrategy)

        tool_call = MagicMock()
        tool_call.id = "call_1"
        tool_call.name = "loop_tool"
        tool_call.arguments = {}

        # LLM всегда возвращает tool_calls — бесконечный цикл
        response = MagicMock(spec=AgentResponse)
        response.text = ""
        response.tool_calls = [tool_call]
        response.plan = None

        mock_strategy.execute.return_value = response
        mock_strategy.continue_execution.return_value = response

        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = False
        mock_tool_def.kind = "other"

        mock_tool_registry = MagicMock()
        mock_tool_registry.get.return_value = mock_tool_def
        mock_tool_result = MagicMock()
        mock_tool_result.success = True
        mock_tool_result.output = "OK"
        mock_tool_result.error = None
        mock_tool_registry.execute_tool = AsyncMock(return_value=mock_tool_result)

        mock_tool_call_handler = MagicMock()
        mock_tool_call_handler.create_tool_call.return_value = "tc_1"
        mock_tool_call_handler.build_tool_call_notification.return_value = MagicMock()
        mock_tool_call_handler.build_tool_update_notification.return_value = MagicMock()

        mock_content_extractor = AsyncMock()
        mock_extracted = MagicMock()
        mock_extracted.content_items = []
        mock_content_extractor.extract_from_result.return_value = mock_extracted

        loop = AgentLoop(
            strategy=mock_strategy,
            tool_registry=mock_tool_registry,
            tool_call_handler=mock_tool_call_handler,
            permission_manager=MagicMock(),
            state_manager=MagicMock(),
            content_extractor=mock_content_extractor,
            content_validator=MagicMock(),
            content_formatter=MagicMock(),
            replay_manager=MagicMock(),
            plan_builder=MagicMock(),
            max_turn_requests=3,  # Ограничиваем до 3
        )

        # Act
        result = await loop.run(mock_session, "test_session", "Бесконечный цикл")

        # Assert
        assert result.stop_reason == StopReason.MAX_TURN_REQUESTS
        assert mock_strategy.execute.call_count == 1
        assert mock_strategy.continue_execution.call_count == 2


class TestAgentLoopErrorHandling:
    """Тесты обработки ошибок в AgentLoop."""

    @pytest.mark.asyncio
    async def test_llm_error_stops_gracefully(self, mock_session):
        """Ошибка LLM приводит к graceful остановке."""
        # Arrange
        mock_strategy = AsyncMock(spec=LLMCallStrategy)
        mock_strategy.execute.side_effect = RuntimeError("LLM service unavailable")

        loop = AgentLoop(
            strategy=mock_strategy,
            tool_registry=MagicMock(),
            tool_call_handler=MagicMock(),
            permission_manager=MagicMock(),
            state_manager=MagicMock(),
            content_extractor=AsyncMock(),
            content_validator=MagicMock(),
            content_formatter=MagicMock(),
            replay_manager=MagicMock(),
            plan_builder=MagicMock(),
        )

        # Act
        result = await loop.run(mock_session, "test_session", "Test")

        # Assert
        assert result.stop_reason == StopReason.END_TURN
        assert len(result.notifications) == 1  # Error notification

    @pytest.mark.asyncio
    async def test_tool_error_continues_loop(self, mock_session):
        """Ошибка tool не останавливает цикл — LLM получает ошибку и продолжает."""
        # Arrange
        mock_strategy = AsyncMock(spec=LLMCallStrategy)

        tool_call = MagicMock()
        tool_call.id = "call_1"
        tool_call.name = "failing_tool"
        tool_call.arguments = {}

        first_response = MagicMock(spec=AgentResponse)
        first_response.text = ""
        first_response.tool_calls = [tool_call]
        first_response.plan = None

        second_response = MagicMock(spec=AgentResponse)
        second_response.text = "Recovered from error"
        second_response.tool_calls = []
        second_response.plan = None

        mock_strategy.execute.return_value = first_response
        mock_strategy.continue_execution.return_value = second_response

        mock_tool_def = MagicMock()
        mock_tool_def.requires_permission = False
        mock_tool_def.kind = "other"

        mock_tool_registry = MagicMock()
        mock_tool_registry.get.return_value = mock_tool_def
        mock_tool_registry.execute_tool = AsyncMock(side_effect=RuntimeError("Tool crashed"))

        mock_tool_call_handler = MagicMock()
        mock_tool_call_handler.create_tool_call.return_value = "tc_1"
        mock_tool_call_handler.build_tool_call_notification.return_value = MagicMock()
        mock_tool_call_handler.build_tool_update_notification.return_value = MagicMock()

        loop = AgentLoop(
            strategy=mock_strategy,
            tool_registry=mock_tool_registry,
            tool_call_handler=mock_tool_call_handler,
            permission_manager=MagicMock(),
            state_manager=MagicMock(),
            content_extractor=AsyncMock(),
            content_validator=MagicMock(),
            content_formatter=MagicMock(),
            replay_manager=MagicMock(),
            plan_builder=MagicMock(),
        )

        # Act
        result = await loop.run(mock_session, "test_session", "Try failing tool")

        # Assert
        assert result.stop_reason == StopReason.END_TURN
        assert result.text == "Recovered from error"
        # Tool result с ошибой добавлен в историю
        assert any(
            h.get("role") == "tool" and "Tool crashed" in str(h.get("content", ""))
            for h in mock_session.history
        )

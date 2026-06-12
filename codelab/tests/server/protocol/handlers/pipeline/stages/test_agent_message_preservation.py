"""Тесты для сохранения agent_message_chunk в events_history."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.agent.base import AgentResponse
from codelab.server.protocol.handlers.pipeline.stages.agent_loop import AgentLoop
from codelab.server.protocol.handlers.replay_manager import ReplayManager
from codelab.server.protocol.state import SessionState


class TestAgentMessageChunkPreservation:
    """Тесты сохранения agent_message_chunk в events_history."""

    @pytest.mark.asyncio
    async def test_agent_response_saved_to_events_history(self) -> None:
        """Agent response сохраняется в events_history для replay."""
        # Arrange
        session = SessionState(
            session_id="test_session",
            cwd="/tmp",
            mcp_servers=[],
        )
        
        mock_strategy = AsyncMock()
        mock_response = AgentResponse(
            text="Hello from agent!",
            tool_calls=[],
            stop_reason="end_turn",
        )
        mock_strategy.execute.return_value = mock_response
        mock_strategy.continue_execution.return_value = mock_response
        
        replay_manager = ReplayManager()
        
        loop = AgentLoop(
            strategy=mock_strategy,
            tool_registry=MagicMock(),
            tool_call_handler=MagicMock(),
            permission_manager=MagicMock(),
            state_manager=MagicMock(),
            content_extractor=MagicMock(),
            content_validator=MagicMock(),
            content_formatter=MagicMock(),
            replay_manager=replay_manager,
            plan_builder=MagicMock(),
            system_prompt_builder=MagicMock(),
        )
        
        # Act
        result = await loop.run(
            session=session,
            session_id="test_session",
            initial_prompt="Hello",
        )
        
        # Assert
        assert result.stop_reason.value == "end_turn"
        assert len(session.events_history) > 0
        
        # Проверяем, что agent_message_chunk сохранён
        agent_chunks = [
            event for event in session.events_history
            if event.get("update", {}).get("sessionUpdate") == "agent_message_chunk"
        ]
        assert len(agent_chunks) > 0
        
        # Проверяем содержимое
        chunk_content = agent_chunks[0]["update"]["content"]
        assert chunk_content["type"] == "text"
        assert chunk_content["text"] == "Hello from agent!"

    @pytest.mark.asyncio
    async def test_multiple_agent_responses_all_saved(self) -> None:
        """Несколько agent responses сохраняются в правильном порядке."""
        # Arrange
        session = SessionState(
            session_id="test_session",
            cwd="/tmp",
            mcp_servers=[],
        )
        
        mock_strategy = AsyncMock()
        # Первый response с tool_calls, чтобы цикл продолжился
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_1"
        mock_tool_call.name = "test_tool"
        mock_tool_call.arguments = {}
        
        responses = [
            AgentResponse(
                text="First response",
                tool_calls=[mock_tool_call],
                stop_reason="tool_use",
            ),
            AgentResponse(text="Second response", tool_calls=[], stop_reason="end_turn"),
        ]
        mock_strategy.execute.return_value = responses[0]
        mock_strategy.continue_execution.side_effect = responses[1:]
        
        # Mock tool registry для обработки tool call
        mock_tool_registry = MagicMock()
        mock_tool_registry.execute_tool = AsyncMock(return_value={"result": "ok"})
        mock_tool_registry.get.return_value = MagicMock(
            requires_permission=False,
            kind="other",
        )
        
        replay_manager = ReplayManager()
        
        loop = AgentLoop(
            strategy=mock_strategy,
            tool_registry=mock_tool_registry,
            tool_call_handler=MagicMock(),
            permission_manager=MagicMock(),
            state_manager=MagicMock(),
            content_extractor=MagicMock(),
            content_validator=MagicMock(),
            content_formatter=MagicMock(),
            replay_manager=replay_manager,
            plan_builder=MagicMock(),
            system_prompt_builder=MagicMock(),
        )
        
        # Act
        await loop.run(
            session=session,
            session_id="test_session",
            initial_prompt="Hello",
        )
        
        # Assert
        agent_chunks = [
            event for event in session.events_history
            if event.get("update", {}).get("sessionUpdate") == "agent_message_chunk"
        ]
        
        # Должно быть 2 chunk (по одному на каждый response)
        assert len(agent_chunks) == 2
        
        # Проверяем порядок
        texts = [chunk["update"]["content"]["text"] for chunk in agent_chunks]
        assert texts[0] == "First response"
        assert texts[1] == "Second response"

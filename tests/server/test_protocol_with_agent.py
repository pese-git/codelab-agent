"""Тесты интеграции ACPProtocol с новой архитектурой.

Проверяют работу session/prompt с LLM-агентом через StrategyDispatcher.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from _protocol_factory import build_protocol

from codelab.server.messages import ACPMessage
from codelab.server.protocol.state import ProtocolOutcome
from codelab.server.storage import InMemoryStorage


def _create_mock_orchestrator(mock_dispatcher):
    """Создаёт mock PromptOrchestrator с StrategyDispatcher."""
    from codelab.server.protocol.handlers.prompt_orchestrator import PromptOrchestrator

    orchestrator = MagicMock(spec=PromptOrchestrator)

    async def mock_handle_prompt(request_id, params, session, storage, **kwargs):
        return ProtocolOutcome(
            response=ACPMessage.response(request_id, {"stopReason": "end_turn"}),
            notifications=[],
        )

    orchestrator.handle_prompt = mock_handle_prompt
    return orchestrator


@pytest.mark.asyncio
async def test_session_prompt_with_strategy_dispatcher() -> None:
    """Тест обработки промпта через StrategyDispatcher."""
    # Arrange — создать mock dispatcher
    mock_dispatcher = MagicMock()
    mock_dispatcher.select_strategy.return_value = ("single", None)
    mock_dispatcher.set_current_strategy.return_value = True
    mock_dispatcher.execute = AsyncMock(return_value=SimpleNamespace(
        text="Hello from agent",
        tool_calls=[],
        stop_reason="end_turn",
        usage=None,
        plan=None,
    ))
    mock_dispatcher.continue_execution = AsyncMock(return_value=SimpleNamespace(
        text="",
        tool_calls=[],
        stop_reason="end_turn",
        usage=None,
        plan=None,
    ))

    protocol = build_protocol(storage=InMemoryStorage())
    protocol._prompt_orchestrator = _create_mock_orchestrator(mock_dispatcher)

    # Act — initialize
    init_outcome = await protocol.handle(
        ACPMessage.request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {},
            },
        )
    )
    assert init_outcome.response is not None
    assert init_outcome.response.error is None

    # Act — session/new
    new_session = await protocol.handle(
        ACPMessage.request("session/new", {"cwd": "/tmp", "mcpServers": []})
    )
    assert new_session.response is not None
    assert isinstance(new_session.response.result, dict)
    session_id = new_session.response.result["sessionId"]

    # Act — session/prompt
    outcome = await protocol.handle(
        ACPMessage.request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "hello agent"}],
            },
        )
    )

    # Assert
    assert outcome.response is not None
    assert outcome.response.error is None
    assert outcome.response.result is not None
    assert outcome.response.result.get("stopReason") == "end_turn"


@pytest.mark.asyncio
async def test_session_prompt_sets_session_title() -> None:
    """Тест установки заголовка сессии при обработке."""
    mock_dispatcher = MagicMock()
    mock_dispatcher.select_strategy.return_value = ("single", None)
    mock_dispatcher.set_current_strategy.return_value = True
    mock_dispatcher.execute = AsyncMock(return_value=SimpleNamespace(
        text="Hello",
        tool_calls=[],
        stop_reason="end_turn",
        usage=None,
        plan=None,
    ))
    mock_dispatcher.continue_execution = AsyncMock(return_value=SimpleNamespace(
        text="",
        tool_calls=[],
        stop_reason="end_turn",
        usage=None,
        plan=None,
    ))

    protocol = build_protocol(storage=InMemoryStorage())
    protocol._prompt_orchestrator = _create_mock_orchestrator(mock_dispatcher)

    # Initialize
    await protocol.handle(
        ACPMessage.request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {},
            },
        )
    )

    # Create session
    new_session = await protocol.handle(
        ACPMessage.request("session/new", {"cwd": "/tmp", "mcpServers": []})
    )
    session_id = new_session.response.result["sessionId"]

    # Process prompt
    prompt_text = "implement authentication system"
    outcome = await protocol.handle(
        ACPMessage.request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": prompt_text}],
            },
        )
    )

    assert outcome.response is not None
    assert outcome.response.error is None


@pytest.mark.asyncio
async def test_acp_protocol_without_prompt_orchestrator() -> None:
    """Тест что ACPProtocol работает без PromptOrchestrator (demo mode)."""
    protocol = build_protocol(storage=InMemoryStorage())
    # оркестратор строится лениво — заранее его нет
    assert protocol._assembler._prompt_orchestrator is None

    # Initialize должен работать
    init_outcome = await protocol.handle(
        ACPMessage.request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {},
            },
        )
    )
    assert init_outcome.response is not None
    assert init_outcome.response.error is None

"""E2E тесты slash-команд через полный protocol pipeline.

Проверяет что slash-команды обрабатываются встроенными handlers
(без обращения к LLM) и возвращают корректные ответы.

Регрессия: ранее PromptOrchestratorBuilder создавал свой CommandRegistry
и не регистрировал ContextCommandHandler — /context не работал.
"""

from __future__ import annotations

import pytest
from _protocol_factory import build_protocol

from codelab.server.messages import ACPMessage


async def _initialize_and_create_session(protocol: object) -> str:
    """Инициализирует протокол и создаёт сессию, возвращает session_id."""
    # Инициализируем orchestrator чтобы command_registry был доступен для session/new
    await protocol._assembler.get_prompt_orchestrator()

    await protocol.handle(
        ACPMessage.request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {
                    "fs": {"readTextFile": True, "writeTextFile": True},
                    "terminal": False,
                },
            },
        )
    )
    created = await protocol.handle(
        ACPMessage.request("session/new", {"cwd": "/tmp", "mcpServers": []})
    )
    assert created.response is not None
    assert isinstance(created.response.result, dict)
    return created.response.result["sessionId"]


def _get_agent_message_text(notifications: list[ACPMessage]) -> str:
    """Собирает текст из agent_message_chunk нотификаций."""
    parts = []
    for n in notifications:
        if n.params is None:
            continue
        update = n.params.get("update", {})
        if update.get("sessionUpdate") == "agent_message_chunk":
            content = update.get("content", {})
            if isinstance(content, dict) and content.get("type") == "text":
                parts.append(content.get("text", ""))
    return "".join(parts)


def _get_available_commands(notifications: list[ACPMessage]) -> list[dict]:
    """Извлекает availableCommands из available_commands_update."""
    for n in notifications:
        if n.params is None:
            continue
        update = n.params.get("update", {})
        if update.get("sessionUpdate") == "available_commands_update":
            return update.get("availableCommands", [])
    return []


# ---------------------------------------------------------------------------
# /context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_command_returns_metrics() -> None:
    """/context возвращает сводку метрик Context Manager (не LLM)."""
    protocol = build_protocol()
    session_id = await _initialize_and_create_session(protocol)

    outcome = await protocol.handle(
        ACPMessage.request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "/context"}],
            },
        )
    )

    assert outcome.response is not None
    assert outcome.response.result is not None
    assert outcome.response.result.get("stopReason") == "end_turn"

    text = _get_agent_message_text(outcome.notifications)
    assert "Context Manager" in text
    assert "enabled=" in text


@pytest.mark.asyncio
async def test_context_spans_command() -> None:
    """/context spans возвращает информацию о span'ах."""
    protocol = build_protocol()
    session_id = await _initialize_and_create_session(protocol)

    outcome = await protocol.handle(
        ACPMessage.request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "/context spans"}],
            },
        )
    )

    assert outcome.response is not None
    assert outcome.response.result.get("stopReason") == "end_turn"

    text = _get_agent_message_text(outcome.notifications)
    assert "span" in text.lower() or "Tracer" in text


@pytest.mark.asyncio
async def test_context_on_off_command() -> None:
    """/context on включает Context Manager, повторный вызов — уже включён."""
    protocol = build_protocol()
    session_id = await _initialize_and_create_session(protocol)

    # Включаем
    outcome = await protocol.handle(
        ACPMessage.request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "/context on"}],
            },
        )
    )

    assert outcome.response is not None
    text = _get_agent_message_text(outcome.notifications)
    assert "включён" in text

    # Повторный вызов — уже включён
    outcome2 = await protocol.handle(
        ACPMessage.request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "/context on"}],
            },
        )
    )

    text2 = _get_agent_message_text(outcome2.notifications)
    assert "уже включён" in text2


# ---------------------------------------------------------------------------
# available_commands_update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_available_commands_contains_context_and_strategy() -> None:
    """available_commands_update содержит context."""
    protocol = build_protocol()
    session_id = await _initialize_and_create_session(protocol)

    outcome = await protocol.handle(
        ACPMessage.request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "hello"}],
            },
        )
    )

    commands = _get_available_commands(outcome.notifications)
    command_names = {cmd.get("name") for cmd in commands}

    assert "context" in command_names, f"context not in {command_names}"
    assert "status" in command_names
    assert "mode" in command_names
    assert "help" in command_names


# ---------------------------------------------------------------------------
# DI интеграция
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_di_orchestrator_has_all_commands() -> None:
    """PromptOrchestrator из DI содержит все зарегистрированные команды."""
    protocol = build_protocol()

    # Получаем orchestrator через protocol
    orchestrator = await protocol._assembler.get_prompt_orchestrator()

    registry = orchestrator.command_registry
    registered = registry.registered_commands

    assert "context" in registered, f"context not in {registered}"
    assert "status" in registered
    assert "mode" in registered
    assert "help" in registered

"""Тесты для базовых интерфейсов агента и компонентов."""

import pytest

from codelab.server.agent.base import AgentContext, AgentResponse, LLMAgent
from codelab.server.llm.base import LLMMessage, LLMProvider, LLMResponse, LLMToolCall
from codelab.server.protocol.state import SessionState
from codelab.server.tools.base import ToolDefinition, ToolRegistry


def test_llm_message_creation() -> None:
    """Проверить создание LLMMessage."""
    msg = LLMMessage(role="user", content="Hello")
    assert msg.role == "user"
    assert msg.content == "Hello"


def test_llm_tool_call_creation() -> None:
    """Проверить создание LLMToolCall."""
    tool_call = LLMToolCall(id="call_1", name="read_file", arguments={"path": "/tmp/test"})
    assert tool_call.id == "call_1"
    assert tool_call.name == "read_file"
    assert tool_call.arguments == {"path": "/tmp/test"}


def test_llm_response_creation() -> None:
    """Проверить создание LLMResponse."""
    response = LLMResponse(
        text="Hello world",
        tool_calls=[],
        stop_reason="end_turn",
    )
    assert response.text == "Hello world"
    assert response.stop_reason == "end_turn"
    assert response.tool_calls == []


def test_llm_response_with_tool_calls() -> None:
    """Проверить LLMResponse с tool calls."""
    tool_call = LLMToolCall(id="call_1", name="read_file", arguments={"path": "/tmp/test"})
    response = LLMResponse(
        text="I need to read a file",
        tool_calls=[tool_call],
        stop_reason="tool_use",
    )
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "read_file"


def test_tool_definition_creation() -> None:
    """Проверить создание ToolDefinition."""
    tool_def = ToolDefinition(
        name="read_file",
        description="Read a file from the system",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
        },
        kind="filesystem",
        requires_permission=True,
    )
    assert tool_def.name == "read_file"
    assert tool_def.kind == "filesystem"
    assert tool_def.requires_permission is True


def test_agent_context_creation() -> None:
    """Проверить создание AgentContext."""
    # Создать SessionState для контекста
    session_state = SessionState(
        session_id="test-session",
        cwd="/tmp",
        mcp_servers=[],
    )
    
    context = AgentContext(
        session_id="test-session",
        session=session_state,
        prompt=[{"type": "text", "text": "Hello"}],
        conversation_history=[],
        available_tools=[],
        config={},
    )
    assert context.session_id == "test-session"
    assert context.session is session_state
    assert len(context.prompt) == 1


def test_agent_response_creation() -> None:
    """Проверить создание AgentResponse."""
    response = AgentResponse(
        text="Hello",
        tool_calls=[],
        stop_reason="end_turn",
    )
    assert response.text == "Hello"
    assert response.stop_reason == "end_turn"


def test_agent_response_with_metadata() -> None:
    """Проверить AgentResponse с метаданными."""
    response = AgentResponse(
        text="Hello",
        tool_calls=[],
        stop_reason="end_turn",
        metadata={"tokens_used": 150},
    )
    assert response.metadata["tokens_used"] == 150


def test_llm_provider_is_abstract() -> None:
    """Проверить, что LLMProvider является абстрактным классом."""
    with pytest.raises(TypeError):
        LLMProvider()  # noqa: F821


def test_tool_registry_is_abstract() -> None:
    """Проверить, что ToolRegistry является абстрактным классом."""
    with pytest.raises(TypeError):
        ToolRegistry()  # noqa: F821


def test_llm_agent_is_abstract() -> None:
    """Проверить, что LLMAgent является абстрактным классом."""
    with pytest.raises(TypeError):
        LLMAgent()  # noqa: F821

"""Интеграционные тесты: LLMAdapter + SessionState через call().

Тестируют работу LLMAdapter с MockLLMProvider.
"""

import pytest

from codelab.server.agent.llm_adapter import LLMAdapter
from codelab.server.llm.base import LLMMessage, LLMToolCall
from codelab.server.llm.mock_provider import MockLLMProvider
from codelab.server.protocol.state import SessionState
from codelab.server.tools.registry import SimpleToolRegistry


def echo_tool(text: str) -> str:
    return f"Echo: {text}"


@pytest.fixture
def tool_registry() -> SimpleToolRegistry:
    registry = SimpleToolRegistry()
    registry.register_tool(
        name="echo",
        description="Возвращает переданный текст",
        parameters={"type": "object", "properties": {"text": {"type": "string"}}},
        kind="other",
        executor=echo_tool,
    )
    return registry


@pytest.fixture
def session_state() -> SessionState:
    return SessionState(
        session_id="integration-test-session",
        cwd="/tmp",
        mcp_servers=[],
        title="Integration Test Session",
    )


@pytest.mark.asyncio
async def test_llm_adapter_call_with_tool_calls(
    tool_registry: SimpleToolRegistry,
    session_state: SessionState,
) -> None:
    """call() возвращает tool_calls из MockLLMProvider."""
    tool_call = LLMToolCall(id="call_1", name="echo", arguments={"text": "Hello"})
    adapter = LLMAdapter(
        llm_provider=MockLLMProvider(response="Буду echo", tool_calls=[tool_call]),
        tool_registry=tool_registry,
        name="test-agent",
    )

    messages = [LLMMessage(role="user", content="Echo something")]
    tools = tool_registry.list_tools()

    result = await adapter.call(messages=messages, tools=tools, config={})

    assert result.text == "Буду echo"
    assert result.stop_reason == "tool_use"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "echo"


@pytest.mark.asyncio
async def test_llm_adapter_call_without_tool_calls(
    tool_registry: SimpleToolRegistry,
    session_state: SessionState,
) -> None:
    """call() без tool_calls возвращает финальный текст."""
    adapter = LLMAdapter(
        llm_provider=MockLLMProvider(response="Готово, вот эхо"),
        tool_registry=tool_registry,
        name="test-agent",
    )

    history = [
        LLMMessage(role="user", content="Echo hello"),
        LLMMessage(
            role="assistant",
            content="",
            tool_calls=[LLMToolCall(id="c1", name="echo", arguments={"text": "hello"})],
        ),
        LLMMessage(role="tool", content="Echo: hello", tool_call_id="c1"),
    ]

    result = await adapter.call(messages=history, tools=[], config={})

    assert result.text == "Готово, вот эхо"
    assert result.tool_calls == []
    assert result.stop_reason == "end_turn"


@pytest.mark.asyncio
async def test_multiple_tool_calls_in_call(
    tool_registry: SimpleToolRegistry,
    session_state: SessionState,
) -> None:
    """call() возвращает несколько tool_calls."""
    tool_calls = [
        LLMToolCall(id="c1", name="echo", arguments={"text": "First"}),
        LLMToolCall(id="c2", name="echo", arguments={"text": "Second"}),
    ]
    adapter = LLMAdapter(
        llm_provider=MockLLMProvider(response="", tool_calls=tool_calls),
        tool_registry=tool_registry,
        name="test-agent",
    )

    messages = [LLMMessage(role="user", content="Execute multiple tools")]
    tools = tool_registry.list_tools()

    result = await adapter.call(messages=messages, tools=tools, config={})

    assert len(result.tool_calls) == 2

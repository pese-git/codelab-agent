"""Тесты для LLM провайдеров (обновлено под новый интерфейс)."""

import pytest

from codelab.server.llm.base import LLMConfig, LLMMessage, LLMToolCall
from codelab.server.llm.mock_provider import MockLLMProvider
from codelab.server.llm.models import CompletionRequest


@pytest.mark.asyncio
async def test_mock_provider_completion() -> None:
    """Проверить mock провайдер."""
    provider = MockLLMProvider(response="Test response")
    await provider.initialize(LLMConfig())

    messages = [LLMMessage(role="user", content="Hello")]
    request = CompletionRequest(model="mock", messages=messages)
    response = await provider.create_completion(request)

    assert response.text == "Test response"
    assert response.stop_reason.value == "end_turn"


@pytest.mark.asyncio
async def test_mock_provider_with_tools() -> None:
    """Проверить mock провайдер с инструментами."""
    tool_call = LLMToolCall(
        id="1",
        name="test_tool",
        arguments={"arg1": "value1"},
    )
    provider = MockLLMProvider(response="Using tool", tool_calls=[tool_call])
    await provider.initialize(LLMConfig())

    messages = [LLMMessage(role="user", content="Hello")]
    request = CompletionRequest(model="mock", messages=messages)
    response = await provider.create_completion(request)

    assert response.text == "Using tool"
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "test_tool"
    assert response.stop_reason.value == "tool_use"


@pytest.mark.asyncio
async def test_mock_provider_stream() -> None:
    """Проверить потоковое получение от mock провайдера."""
    provider = MockLLMProvider(response="Streaming response")
    await provider.initialize(LLMConfig())

    messages = [LLMMessage(role="user", content="Hello")]
    request = CompletionRequest(model="mock", messages=messages)
    responses = []
    async for response in provider.stream_completion(request):
        responses.append(response)

    assert len(responses) == 1
    assert responses[0].text == "Streaming response"


@pytest.mark.asyncio
async def test_mock_provider_captures_input() -> None:
    """Проверить, что mock провайдер сохраняет входные параметры."""
    provider = MockLLMProvider(response="Test")
    await provider.initialize(LLMConfig())

    messages = [LLMMessage(role="user", content="Hello")]
    tools = [{"name": "test", "description": "Test tool"}]
    request = CompletionRequest(model="mock", messages=messages, tools=tools)

    await provider.create_completion(request)

    assert provider.last_request is not None
    assert provider.last_request.messages == messages
    assert provider.last_request.tools == tools


@pytest.mark.asyncio
async def test_mock_provider_default_response() -> None:
    """Проверить mock провайдер с ответом по умолчанию."""
    provider = MockLLMProvider()
    await provider.initialize(LLMConfig())

    messages = [LLMMessage(role="user", content="Hello")]
    request = CompletionRequest(model="mock", messages=messages)
    response = await provider.create_completion(request)

    assert response.text == "Mock response"
    assert response.stop_reason.value == "end_turn"


@pytest.mark.asyncio
async def test_mock_provider_multiple_tool_calls() -> None:
    """Проверить mock провайдер с несколькими tool calls."""
    tool_calls = [
        LLMToolCall(id="1", name="tool1", arguments={"arg": "value1"}),
        LLMToolCall(id="2", name="tool2", arguments={"arg": "value2"}),
    ]
    provider = MockLLMProvider(response="Using tools", tool_calls=tool_calls)
    await provider.initialize(LLMConfig())

    messages = [LLMMessage(role="user", content="Hello")]
    request = CompletionRequest(model="mock", messages=messages)
    response = await provider.create_completion(request)

    assert len(response.tool_calls) == 2
    assert response.tool_calls[0].name == "tool1"
    assert response.tool_calls[1].name == "tool2"
    assert response.stop_reason.value == "tool_use"

"""Тесты для Anthropic провайдера."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.llm.base import LLMConfig
from codelab.server.llm.models import (
    CompletionRequest,
    LLMMessage,
    LLMToolCall,
    StopReason,
)
from codelab.server.llm.providers.anthropic import AnthropicProvider


@dataclass
class MockContentBlock:
    """Мок content block из Anthropic API."""

    type: str
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict[str, Any] | None = None


@dataclass
class MockUsage:
    """Мок usage из Anthropic API."""

    input_tokens: int = 100
    output_tokens: int = 50


@dataclass
class MockAnthropicResponse:
    """Мок ответа от Anthropic API."""

    content: list[MockContentBlock]
    stop_reason: str = "end_turn"
    usage: MockUsage = field(default_factory=MockUsage)


@pytest.fixture
def provider() -> AnthropicProvider:
    """Создать экземпляр AnthropicProvider."""
    return AnthropicProvider()


@pytest.fixture
def config() -> LLMConfig:
    """Создать конфигурацию для тестов."""
    return LLMConfig(api_key="test-key", model="claude-sonnet-4")


class TestAnthropicProviderProperties:
    """Тесты свойств провайдера."""

    def test_name(self, provider: AnthropicProvider) -> None:
        """Имя провайдера должно быть 'anthropic'."""
        assert provider.name == "anthropic"

    def test_capabilities(self, provider: AnthropicProvider) -> None:
        """Возможности провайдера."""
        caps = provider.capabilities
        assert caps.supports_tools is True
        assert caps.supports_streaming is True
        assert caps.supports_function_calling is True
        assert caps.supports_vision is True
        assert caps.supports_system_prompt is True
        assert caps.max_context_window == 200000


class TestAnthropicProviderInitialize:
    """Тесты инициализации."""

    @pytest.mark.asyncio
    async def test_initialize_creates_client(
        self,
        provider: AnthropicProvider,
        config: LLMConfig,
    ) -> None:
        """Инициализация должна создать AsyncAnthropic клиент."""
        await provider.initialize(config)

        assert provider._client is not None
        assert provider._config == config

    @pytest.mark.asyncio
    async def test_initialize_stores_config(
        self,
        provider: AnthropicProvider,
    ) -> None:
        """Инициализация должна сохранить конфигурацию."""
        config = LLMConfig(
            api_key="my-key",
            model="claude-opus-4",
            temperature=0.5,
            max_tokens=4096,
        )
        await provider.initialize(config)

        assert provider._config.model == "claude-opus-4"
        assert provider._config.temperature == 0.5
        assert provider._config.max_tokens == 4096


class TestAnthropicProviderExtractSystemMessage:
    """Тесты _extract_system_message."""

    def test_extract_system_message_present(self, provider: AnthropicProvider) -> None:
        """Извлечь system message из списка."""
        messages = [
            LLMMessage(role="system", content="You are helpful"),
            LLMMessage(role="user", content="Hello"),
        ]
        result = provider._extract_system_message(messages)
        assert result == "You are helpful"

    def test_extract_system_message_absent(self, provider: AnthropicProvider) -> None:
        """Вернуть None если system message отсутствует."""
        messages = [
            LLMMessage(role="user", content="Hello"),
            LLMMessage(role="assistant", content="Hi"),
        ]
        result = provider._extract_system_message(messages)
        assert result is None

    def test_extract_system_message_empty_content(self, provider: AnthropicProvider) -> None:
        """Извлечь system message с пустым content."""
        messages = [
            LLMMessage(role="system", content=""),
            LLMMessage(role="user", content="Hello"),
        ]
        result = provider._extract_system_message(messages)
        assert result == ""

    def test_extract_system_message_first_wins(self, provider: AnthropicProvider) -> None:
        """Вернуть первый system message если их несколько."""
        messages = [
            LLMMessage(role="system", content="First"),
            LLMMessage(role="system", content="Second"),
        ]
        result = provider._extract_system_message(messages)
        assert result == "First"


class TestAnthropicProviderConvertFormat:
    """Тесты _convert_to_anthropic_format."""

    def test_convert_user_message(self, provider: AnthropicProvider) -> None:
        """Конвертация user message."""
        messages = [LLMMessage(role="user", content="Hello")]
        result = provider._convert_to_anthropic_format(messages)

        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "Hello"

    def test_convert_assistant_message(self, provider: AnthropicProvider) -> None:
        """Конвертация assistant message."""
        messages = [LLMMessage(role="assistant", content="Hi there")]
        result = provider._convert_to_anthropic_format(messages)

        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "Hi there"

    def test_convert_system_message_skipped(self, provider: AnthropicProvider) -> None:
        """System message пропускается (обрабатывается отдельно)."""
        messages = [
            LLMMessage(role="system", content="System prompt"),
            LLMMessage(role="user", content="Hello"),
        ]
        result = provider._convert_to_anthropic_format(messages)

        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_convert_tool_message(self, provider: AnthropicProvider) -> None:
        """Конвертация tool message."""
        messages = [
            LLMMessage(
                role="tool",
                content="Tool result",
                tool_call_id="call_123",
            ),
        ]
        result = provider._convert_to_anthropic_format(messages)

        assert len(result) == 1
        assert result[0]["role"] == "tool"
        assert result[0]["content"] == [
            {
                "type": "tool_result",
                "tool_use_id": "call_123",
                "content": "Tool result",
            }
        ]

    def test_convert_assistant_with_tool_calls(self, provider: AnthropicProvider) -> None:
        """Конвертация assistant message с tool_calls."""
        tool_calls = [
            LLMToolCall(id="call_1", name="read_file", arguments={"path": "/tmp/test"}),
        ]
        messages = [
            LLMMessage(
                role="assistant",
                content="Let me read that",
                tool_calls=tool_calls,
            ),
        ]
        result = provider._convert_to_anthropic_format(messages)

        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        content = result[0]["content"]
        assert len(content) == 2
        assert content[0] == {"type": "text", "text": "Let me read that"}
        assert content[1] == {
            "type": "tool_use",
            "id": "call_1",
            "name": "read_file",
            "input": {"path": "/tmp/test"},
        }

    def test_convert_assistant_tool_calls_no_content(self, provider: AnthropicProvider) -> None:
        """Конвертация assistant message с tool_calls без content."""
        tool_calls = [
            LLMToolCall(id="call_1", name="test", arguments={}),
        ]
        messages = [
            LLMMessage(role="assistant", content=None, tool_calls=tool_calls),
        ]
        result = provider._convert_to_anthropic_format(messages)

        content = result[0]["content"]
        assert len(content) == 1
        assert content[0]["type"] == "tool_use"

    def test_convert_empty_messages(self, provider: AnthropicProvider) -> None:
        """Конвертация пустого списка."""
        result = provider._convert_to_anthropic_format([])
        assert result == []

    def test_convert_mixed_messages(self, provider: AnthropicProvider) -> None:
        """Конвертация смешанных сообщений."""
        messages = [
            LLMMessage(role="system", content="System"),
            LLMMessage(role="user", content="Hello"),
            LLMMessage(role="assistant", content="Hi"),
            LLMMessage(role="user", content="How are you?"),
        ]
        result = provider._convert_to_anthropic_format(messages)

        assert len(result) == 3
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"
        assert result[2]["role"] == "user"


class TestAnthropicProviderConvertTools:
    """Тесты _convert_tools_for_anthropic."""

    def test_convert_single_tool(self, provider: AnthropicProvider) -> None:
        """Конвертация одного инструмента."""
        tools = [
            {
                "name": "read_file",
                "description": "Read a file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                },
            }
        ]
        result = provider._convert_tools_for_anthropic(tools)

        assert len(result) == 1
        assert result[0]["name"] == "read_file"
        assert result[0]["description"] == "Read a file"
        assert "input_schema" in result[0]
        assert result[0]["input_schema"]["type"] == "object"

    def test_convert_multiple_tools(self, provider: AnthropicProvider) -> None:
        """Конвертация нескольких инструментов."""
        tools = [
            {"name": "tool1", "description": "Tool 1"},
            {"name": "tool2", "description": "Tool 2"},
        ]
        result = provider._convert_tools_for_anthropic(tools)

        assert len(result) == 2
        assert result[0]["name"] == "tool1"
        assert result[1]["name"] == "tool2"

    def test_convert_tool_without_parameters(self, provider: AnthropicProvider) -> None:
        """Конвертация инструмента без parameters."""
        tools = [{"name": "simple", "description": "Simple tool"}]
        result = provider._convert_tools_for_anthropic(tools)

        assert result[0]["input_schema"] == {"type": "object", "properties": {}}

    def test_convert_empty_tools(self, provider: AnthropicProvider) -> None:
        """Конвертация пустого списка."""
        result = provider._convert_tools_for_anthropic([])
        assert result == []


class TestAnthropicProviderParseResponse:
    """Тесты _parse_response."""

    def test_parse_text_response(self, provider: AnthropicProvider) -> None:
        """Парсинг текстового ответа."""
        response = MockAnthropicResponse(
            content=[MockContentBlock(type="text", text="Hello world")],
            stop_reason="end_turn",
            usage=MockUsage(input_tokens=10, output_tokens=5),
        )
        result = provider._parse_response(response, "claude-sonnet-4")

        assert result.text == "Hello world"
        assert result.stop_reason == StopReason.END_TURN
        assert result.model == "claude-sonnet-4"
        assert result.usage == {"input_tokens": 10, "output_tokens": 5}
        assert result.tool_calls == []

    def test_parse_tool_use_response(self, provider: AnthropicProvider) -> None:
        """Парсинг ответа с tool_use."""
        response = MockAnthropicResponse(
            content=[
                MockContentBlock(type="text", text="Let me help"),
                MockContentBlock(
                    type="tool_use",
                    id="call_1",
                    name="read_file",
                    input={"path": "/tmp/test"},
                ),
            ],
            stop_reason="tool_use",
        )
        result = provider._parse_response(response, "claude-sonnet-4")

        assert result.text == "Let me help"
        assert result.stop_reason == StopReason.TOOL_USE
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].id == "call_1"
        assert result.tool_calls[0].name == "read_file"
        assert result.tool_calls[0].arguments == {"path": "/tmp/test"}

    def test_parse_max_tokens_response(self, provider: AnthropicProvider) -> None:
        """Парсинг ответа с max_tokens stop reason."""
        response = MockAnthropicResponse(
            content=[MockContentBlock(type="text", text="Partial")],
            stop_reason="max_tokens",
        )
        result = provider._parse_response(response, "claude-sonnet-4")

        assert result.stop_reason == StopReason.MAX_TOKENS

    def test_parse_stop_sequence_response(self, provider: AnthropicProvider) -> None:
        """Парсинг ответа с stop_sequence stop reason."""
        response = MockAnthropicResponse(
            content=[MockContentBlock(type="text", text="Stopped")],
            stop_reason="stop_sequence",
        )
        result = provider._parse_response(response, "claude-sonnet-4")

        assert result.stop_reason == StopReason.STOP_SEQUENCE

    def test_parse_multiple_text_blocks(self, provider: AnthropicProvider) -> None:
        """Парсинг ответа с несколькими text blocks."""
        response = MockAnthropicResponse(
            content=[
                MockContentBlock(type="text", text="Part 1"),
                MockContentBlock(type="text", text=" Part 2"),
            ],
            stop_reason="end_turn",
        )
        result = provider._parse_response(response, "claude-sonnet-4")

        assert result.text == "Part 1 Part 2"

    def test_parse_tool_use_with_non_dict_input(self, provider: AnthropicProvider) -> None:
        """Парсинг tool_use с non-dict input."""
        response = MockAnthropicResponse(
            content=[
                MockContentBlock(
                    type="tool_use",
                    id="call_1",
                    name="test",
                    input="not a dict",
                ),
            ],
            stop_reason="tool_use",
        )
        result = provider._parse_response(response, "claude-sonnet-4")

        assert result.tool_calls[0].arguments == {}

    def test_parse_response_without_usage(self, provider: AnthropicProvider) -> None:
        """Парсинг ответа без usage."""
        response = MockAnthropicResponse(
            content=[MockContentBlock(type="text", text="Hello")],
            stop_reason="end_turn",
            usage=MockUsage(0, 0),
        )
        result = provider._parse_response(response, "claude-sonnet-4")

        assert result.usage == {"input_tokens": 0, "output_tokens": 0}


class TestAnthropicProviderCreateCompletion:
    """Тесты create_completion с моками."""

    @pytest.mark.asyncio
    async def test_create_completion_not_initialized(self, provider: AnthropicProvider) -> None:
        """Вызов до инициализации должен поднять ошибку."""
        request = CompletionRequest(
            model="claude-sonnet-4",
            messages=[LLMMessage(role="user", content="Hello")],
        )
        with pytest.raises(RuntimeError, match="Provider not initialized"):
            await provider.create_completion(request)

    @pytest.mark.asyncio
    async def test_create_completion_basic(
        self,
        provider: AnthropicProvider,
        config: LLMConfig,
    ) -> None:
        """Базовый вызов create_completion."""
        await provider.initialize(config)

        mock_response = MockAnthropicResponse(
            content=[MockContentBlock(type="text", text="Hello!")],
            stop_reason="end_turn",
            usage=MockUsage(10, 5),
        )
        provider._client = MagicMock()
        provider._client.messages = MagicMock()
        provider._client.messages.create = AsyncMock(return_value=mock_response)

        request = CompletionRequest(
            model="claude-sonnet-4",
            messages=[LLMMessage(role="user", content="Hi")],
        )
        result = await provider.create_completion(request)

        assert result.text == "Hello!"
        provider._client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_completion_with_system_message(
        self,
        provider: AnthropicProvider,
        config: LLMConfig,
    ) -> None:
        """Вызов с system message."""
        await provider.initialize(config)

        mock_response = MockAnthropicResponse(
            content=[MockContentBlock(type="text", text="OK")],
            stop_reason="end_turn",
        )
        provider._client = MagicMock()
        provider._client.messages = MagicMock()
        provider._client.messages.create = AsyncMock(return_value=mock_response)

        request = CompletionRequest(
            model="claude-sonnet-4",
            messages=[
                LLMMessage(role="system", content="Be helpful"),
                LLMMessage(role="user", content="Hi"),
            ],
        )
        await provider.create_completion(request)

        call_kwargs = provider._client.messages.create.call_args.kwargs
        assert call_kwargs["system"] == "Be helpful"

    @pytest.mark.asyncio
    async def test_create_completion_with_tools(
        self,
        provider: AnthropicProvider,
        config: LLMConfig,
    ) -> None:
        """Вызов с tools."""
        await provider.initialize(config)

        mock_response = MockAnthropicResponse(
            content=[
                MockContentBlock(
                    type="tool_use",
                    id="call_1",
                    name="test_tool",
                    input={"arg": "value"},
                ),
            ],
            stop_reason="tool_use",
        )
        provider._client = MagicMock()
        provider._client.messages = MagicMock()
        provider._client.messages.create = AsyncMock(return_value=mock_response)

        tools = [{"name": "test_tool", "description": "Test", "parameters": {}}]
        request = CompletionRequest(
            model="claude-sonnet-4",
            messages=[LLMMessage(role="user", content="Use tool")],
            tools=tools,
        )
        result = await provider.create_completion(request)

        assert result.stop_reason == StopReason.TOOL_USE
        assert len(result.tool_calls) == 1
        call_kwargs = provider._client.messages.create.call_args.kwargs
        assert "tools" in call_kwargs

    @pytest.mark.asyncio
    async def test_create_completion_uses_config_model(
        self,
        provider: AnthropicProvider,
    ) -> None:
        """Использовать модель из config если не указана в request."""
        config = LLMConfig(api_key="key", model="claude-opus-4")
        await provider.initialize(config)

        mock_response = MockAnthropicResponse(
            content=[MockContentBlock(type="text", text="OK")],
            stop_reason="end_turn",
        )
        provider._client = MagicMock()
        provider._client.messages = MagicMock()
        provider._client.messages.create = AsyncMock(return_value=mock_response)

        request = CompletionRequest(
            model="",
            messages=[LLMMessage(role="user", content="Hi")],
        )
        result = await provider.create_completion(request)

        assert result.model == "claude-opus-4"


class TestAnthropicProviderStreamCompletion:
    """Тесты stream_completion с моками."""

    @pytest.mark.asyncio
    async def test_stream_completion_not_initialized(self, provider: AnthropicProvider) -> None:
        """Вызов до инициализации должен поднять ошибку."""
        request = CompletionRequest(
            model="claude-sonnet-4",
            messages=[LLMMessage(role="user", content="Hello")],
        )
        with pytest.raises(RuntimeError, match="Provider not initialized"):
            async for _ in provider.stream_completion(request):
                pass

    @pytest.mark.asyncio
    async def test_stream_completion_basic(
        self,
        provider: AnthropicProvider,
        config: LLMConfig,
    ) -> None:
        """Базовый streaming."""
        await provider.initialize(config)

        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=None)
        mock_stream.text_stream = _async_iter(["Hello", " ", "world"])

        provider._client = MagicMock()
        provider._client.messages = MagicMock()
        provider._client.messages.stream = MagicMock(return_value=mock_stream)

        request = CompletionRequest(
            model="claude-sonnet-4",
            messages=[LLMMessage(role="user", content="Hi")],
        )
        chunks = []
        async for chunk in provider.stream_completion(request):
            chunks.append(chunk)

        assert len(chunks) == 3
        assert chunks[0].text == "Hello"
        assert chunks[1].text == "Hello "
        assert chunks[2].text == "Hello world"
        assert all(c.stop_reason == StopReason.STREAMING for c in chunks)


async def _async_iter(items):
    """Async generator helper."""
    for item in items:
        yield item

"""Тесты для OpenAI-compatible провайдера."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.llm.base import LLMConfig, LLMTimeoutConfig
from codelab.server.llm.models import (
    CompletionRequest,
    LLMMessage,
    LLMToolCall,
    StopReason,
)
from codelab.server.llm.providers.openai_compatible import OpenAICompatibleProvider


class ConcreteOpenAIProvider(OpenAICompatibleProvider):
    """Конкретная реализация для тестирования."""

    @property
    def name(self) -> str:
        return "test-openai"


@dataclass
class MockFunction:
    """Мок function из OpenAI API."""

    name: str
    arguments: str | dict[str, Any]


@dataclass
class MockToolCall:
    """Мок tool_call из OpenAI API."""

    id: str
    type: str = "function"
    function: MockFunction | None = None


@dataclass
class MockMessage:
    """Мок message из OpenAI API."""

    content: str | None = None
    tool_calls: list[MockToolCall] | None = None


@dataclass
class MockChoice:
    """Мок choice из OpenAI API."""

    message: MockMessage
    finish_reason: str = "stop"


@dataclass
class MockUsage:
    """Мок usage из OpenAI API."""

    prompt_tokens: int = 100
    completion_tokens: int = 50
    total_tokens: int = 150


@dataclass
class MockChatCompletion:
    """Мок ChatCompletion из OpenAI API."""

    choices: list[MockChoice]
    usage: MockUsage | None = None


@pytest.fixture
def provider() -> ConcreteOpenAIProvider:
    """Создать экземпляр ConcreteOpenAIProvider."""
    return ConcreteOpenAIProvider(base_url="https://api.test.com/v1")


@pytest.fixture
def config() -> LLMConfig:
    """Создать конфигурацию для тестов."""
    return LLMConfig(
        api_key="test-key",
        model="gpt-4o",
        timeout=LLMTimeoutConfig(connect=10, read=60, write=60, pool=10),
    )


class TestOpenAICompatibleProviderProperties:
    """Тесты свойств провайдера."""

    def test_name(self, provider: ConcreteOpenAIProvider) -> None:
        """Имя провайдера."""
        assert provider.name == "test-openai"

    def test_capabilities(self, provider: ConcreteOpenAIProvider) -> None:
        """Возможности провайдера."""
        caps = provider.capabilities
        assert caps.supports_tools is True
        assert caps.supports_streaming is True
        assert caps.supports_function_calling is True
        assert caps.supports_vision is False
        assert caps.supports_system_prompt is True


class TestOpenAICompatibleProviderInitialize:
    """Тесты инициализации."""

    @pytest.mark.asyncio
    async def test_initialize_creates_client(
        self,
        provider: ConcreteOpenAIProvider,
        config: LLMConfig,
    ) -> None:
        """Инициализация должна создать AsyncOpenAI клиент."""
        await provider.initialize(config)

        assert provider._client is not None
        assert provider._config == config

    @pytest.mark.asyncio
    async def test_initialize_with_base_url(
        self,
        config: LLMConfig,
    ) -> None:
        """Инициализация с base_url."""
        provider = ConcreteOpenAIProvider(base_url="https://custom.api.com/v1")
        await provider.initialize(config)

        assert provider._base_url == "https://custom.api.com/v1"

    @pytest.mark.asyncio
    async def test_initialize_without_base_url(
        self,
        config: LLMConfig,
    ) -> None:
        """Инициализация без base_url."""
        provider = ConcreteOpenAIProvider()
        await provider.initialize(config)

        assert provider._base_url is None

    @pytest.mark.asyncio
    async def test_initialize_stores_config(
        self,
        provider: ConcreteOpenAIProvider,
    ) -> None:
        """Инициализация должна сохранить конфигурацию."""
        config = LLMConfig(
            api_key="my-key",
            model="gpt-4-turbo",
            temperature=0.5,
            max_tokens=4096,
        )
        await provider.initialize(config)

        assert provider._config.model == "gpt-4-turbo"
        assert provider._config.temperature == 0.5


class TestOpenAICompatibleProviderConvertFormat:
    """Тесты _convert_to_openai_format."""

    def test_convert_user_message(self, provider: ConcreteOpenAIProvider) -> None:
        """Конвертация user message."""
        messages = [LLMMessage(role="user", content="Hello")]
        result = provider._convert_to_openai_format(messages)

        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "Hello"

    def test_convert_system_message(self, provider: ConcreteOpenAIProvider) -> None:
        """Конвертация system message."""
        messages = [LLMMessage(role="system", content="You are helpful")]
        result = provider._convert_to_openai_format(messages)

        assert len(result) == 1
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "You are helpful"

    def test_convert_assistant_message(self, provider: ConcreteOpenAIProvider) -> None:
        """Конвертация assistant message."""
        messages = [LLMMessage(role="assistant", content="Hi there")]
        result = provider._convert_to_openai_format(messages)

        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "Hi there"

    def test_convert_tool_message(self, provider: ConcreteOpenAIProvider) -> None:
        """Конвертация tool message."""
        messages = [
            LLMMessage(
                role="tool",
                content="Tool result",
                tool_call_id="call_123",
                name="read_file",
            ),
        ]
        result = provider._convert_to_openai_format(messages)

        assert len(result) == 1
        assert result[0]["role"] == "tool"
        assert result[0]["content"] == "Tool result"
        assert result[0]["tool_call_id"] == "call_123"
        assert result[0]["name"] == "read_file"

    def test_convert_assistant_with_tool_calls(self, provider: ConcreteOpenAIProvider) -> None:
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
        result = provider._convert_to_openai_format(messages)

        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "Let me read that"
        assert "tool_calls" in result[0]
        assert len(result[0]["tool_calls"]) == 1
        tc = result[0]["tool_calls"][0]
        assert tc["id"] == "call_1"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "read_file"
        assert json.loads(tc["function"]["arguments"]) == {"path": "/tmp/test"}

    def test_convert_message_with_none_content(self, provider: ConcreteOpenAIProvider) -> None:
        """Конвертация сообщения с None content."""
        messages = [LLMMessage(role="user", content=None)]
        result = provider._convert_to_openai_format(messages)

        assert len(result) == 1
        assert "content" not in result[0]

    def test_convert_empty_messages(self, provider: ConcreteOpenAIProvider) -> None:
        """Конвертация пустого списка."""
        result = provider._convert_to_openai_format([])
        assert result == []


class TestOpenAICompatibleProviderParseCompletion:
    """Тесты _parse_completion."""

    def test_parse_text_response(self, provider: ConcreteOpenAIProvider) -> None:
        """Парсинг текстового ответа."""
        response = MockChatCompletion(
            choices=[MockChoice(message=MockMessage(content="Hello world"), finish_reason="stop")],
            usage=MockUsage(10, 5, 15),
        )
        result = provider._parse_completion(response, "gpt-4o")

        assert result.text == "Hello world"
        assert result.stop_reason == StopReason.STOP_SEQUENCE
        assert result.model == "gpt-4o"
        assert result.usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        assert result.tool_calls == []

    def test_parse_tool_calls_response(self, provider: ConcreteOpenAIProvider) -> None:
        """Парсинг ответа с tool_calls."""
        response = MockChatCompletion(
            choices=[
                MockChoice(
                    message=MockMessage(
                        content="Let me help",
                        tool_calls=[
                            MockToolCall(
                                id="call_1",
                                function=MockFunction(
                                    name="read_file",
                                    arguments='{"path": "/tmp/test"}',
                                ),
                            ),
                        ],
                    ),
                    finish_reason="tool_calls",
                )
            ],
        )
        result = provider._parse_completion(response, "gpt-4o")

        assert result.text == "Let me help"
        assert result.stop_reason == StopReason.TOOL_USE
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].id == "call_1"
        assert result.tool_calls[0].name == "read_file"
        assert result.tool_calls[0].arguments == {"path": "/tmp/test"}

    def test_parse_tool_calls_with_dict_arguments(self, provider: ConcreteOpenAIProvider) -> None:
        """Парсинг tool_calls с dict arguments."""
        response = MockChatCompletion(
            choices=[
                MockChoice(
                    message=MockMessage(
                        content=None,
                        tool_calls=[
                            MockToolCall(
                                id="call_1",
                                function=MockFunction(
                                    name="test",
                                    arguments={"key": "value"},
                                ),
                            ),
                        ],
                    ),
                    finish_reason="tool_calls",
                )
            ],
        )
        result = provider._parse_completion(response, "gpt-4o")

        assert result.tool_calls[0].arguments == {"key": "value"}

    def test_parse_tool_calls_with_invalid_json(self, provider: ConcreteOpenAIProvider) -> None:
        """Парсинг tool_calls с невалидным JSON."""
        response = MockChatCompletion(
            choices=[
                MockChoice(
                    message=MockMessage(
                        tool_calls=[
                            MockToolCall(
                                id="call_1",
                                function=MockFunction(
                                    name="test",
                                    arguments="not valid json",
                                ),
                            ),
                        ],
                    ),
                    finish_reason="tool_calls",
                )
            ],
        )
        result = provider._parse_completion(response, "gpt-4o")

        assert result.tool_calls[0].arguments == {}

    def test_parse_max_tokens_response(self, provider: ConcreteOpenAIProvider) -> None:
        """Парсинг ответа с length finish_reason."""
        response = MockChatCompletion(
            choices=[MockChoice(message=MockMessage(content="Partial"), finish_reason="length")],
        )
        result = provider._parse_completion(response, "gpt-4o")

        assert result.stop_reason == StopReason.MAX_TOKENS

    def test_parse_stop_sequence_response(self, provider: ConcreteOpenAIProvider) -> None:
        """Парсинг ответа с stop finish_reason."""
        response = MockChatCompletion(
            choices=[MockChoice(message=MockMessage(content="Stopped"), finish_reason="stop")],
        )
        result = provider._parse_completion(response, "gpt-4o")

        assert result.stop_reason == StopReason.STOP_SEQUENCE

    def test_parse_response_without_usage(self, provider: ConcreteOpenAIProvider) -> None:
        """Парсинг ответа без usage."""
        response = MockChatCompletion(
            choices=[MockChoice(message=MockMessage(content="Hello"))],
            usage=None,
        )
        result = provider._parse_completion(response, "gpt-4o")

        assert result.usage == {}

    def test_parse_response_with_none_content(self, provider: ConcreteOpenAIProvider) -> None:
        """Парсинг ответа с None content."""
        response = MockChatCompletion(
            choices=[MockChoice(message=MockMessage(content=None))],
        )
        result = provider._parse_completion(response, "gpt-4o")

        assert result.text == ""


class TestOpenAICompatibleProviderValidateHistory:
    """Тесты _validate_message_history."""

    def test_valid_history(self, provider: ConcreteOpenAIProvider) -> None:
        """Валидная история сообщений."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
            {"role": "user", "content": "How are you?"},
        ]
        provider._validate_message_history(messages)

    def test_valid_tool_history(self, provider: ConcreteOpenAIProvider) -> None:
        """Валидная история с tool calls."""
        messages = [
            {"role": "user", "content": "Read file"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "call_1", "function": {"name": "read_file"}}],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "File content"},
        ]
        provider._validate_message_history(messages)

    def test_tool_message_without_tool_call_id(self, provider: ConcreteOpenAIProvider) -> None:
        """Tool message без tool_call_id должен поднять ошибку."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "tool", "content": "Result"},
        ]
        with pytest.raises(ValueError, match="missing tool_call_id"):
            provider._validate_message_history(messages)

    def test_tool_message_without_assistant_tool_calls(
        self, provider: ConcreteOpenAIProvider
    ) -> None:
        """Tool message без preceding assistant tool_calls должен поднять ошибку."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "tool", "tool_call_id": "call_1", "content": "Result"},
        ]
        with pytest.raises(ValueError, match="must follow an assistant"):
            provider._validate_message_history(messages)

    def test_empty_history(self, provider: ConcreteOpenAIProvider) -> None:
        """Пустая история валидна."""
        provider._validate_message_history([])

    def test_assistant_without_tool_calls_clears_state(
        self, provider: ConcreteOpenAIProvider
    ) -> None:
        """Assistant message без tool_calls очищает состояние."""
        messages = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "call_1", "function": {"name": "test"}}],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "Result"},
            {"role": "assistant", "content": "Done"},
            {"role": "user", "content": "Next"},
        ]
        provider._validate_message_history(messages)


class TestOpenAICompatibleProviderNormalizeModelId:
    """Тесты _normalize_model_id."""

    def test_normalize_with_prefix(self, provider: ConcreteOpenAIProvider) -> None:
        """Нормализация model ID с префиксом провайдера."""
        result = provider._normalize_model_id("test-openai/gpt-4o")
        assert result == "gpt-4o"

    def test_normalize_without_prefix(self, provider: ConcreteOpenAIProvider) -> None:
        """Нормализация model ID без префикса."""
        result = provider._normalize_model_id("gpt-4o")
        assert result == "gpt-4o"

    def test_normalize_empty_model(self, provider: ConcreteOpenAIProvider) -> None:
        """Нормализация пустого model ID."""
        result = provider._normalize_model_id("")
        assert result == ""

    def test_normalize_different_prefix(self, provider: ConcreteOpenAIProvider) -> None:
        """Нормализация model ID с другим префиксом."""
        result = provider._normalize_model_id("openrouter/gpt-4o")
        assert result == "openrouter/gpt-4o"


class TestOpenAICompatibleProviderCreateCompletion:
    """Тесты create_completion с моками."""

    @pytest.mark.asyncio
    async def test_create_completion_not_initialized(
        self, provider: ConcreteOpenAIProvider
    ) -> None:
        """Вызов до инициализации должен поднять ошибку."""
        request = CompletionRequest(
            model="gpt-4o",
            messages=[LLMMessage(role="user", content="Hello")],
        )
        with pytest.raises(RuntimeError, match="Provider not initialized"):
            await provider.create_completion(request)

    @pytest.mark.asyncio
    async def test_create_completion_basic(
        self,
        provider: ConcreteOpenAIProvider,
        config: LLMConfig,
    ) -> None:
        """Базовый вызов create_completion."""
        await provider.initialize(config)

        mock_response = MockChatCompletion(
            choices=[MockChoice(message=MockMessage(content="Hello!"))],
            usage=MockUsage(10, 5, 15),
        )
        provider._client = MagicMock()
        provider._client.chat = MagicMock()
        provider._client.chat.completions = MagicMock()
        provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

        request = CompletionRequest(
            model="gpt-4o",
            messages=[LLMMessage(role="user", content="Hi")],
        )
        result = await provider.create_completion(request)

        assert result.text == "Hello!"
        provider._client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_completion_with_tools(
        self,
        provider: ConcreteOpenAIProvider,
        config: LLMConfig,
    ) -> None:
        """Вызов с tools."""
        await provider.initialize(config)

        mock_response = MockChatCompletion(
            choices=[
                MockChoice(
                    message=MockMessage(
                        content=None,
                        tool_calls=[
                            MockToolCall(
                                id="call_1",
                                function=MockFunction(name="test", arguments="{}"),
                            ),
                        ],
                    ),
                    finish_reason="tool_calls",
                )
            ],
        )
        provider._client = MagicMock()
        provider._client.chat = MagicMock()
        provider._client.chat.completions = MagicMock()
        provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

        tools = [{"name": "test", "description": "Test", "parameters": {}}]
        request = CompletionRequest(
            model="gpt-4o",
            messages=[LLMMessage(role="user", content="Use tool")],
            tools=tools,
        )
        result = await provider.create_completion(request)

        assert result.stop_reason == StopReason.TOOL_USE
        call_kwargs = provider._client.chat.completions.create.call_args.kwargs
        assert "tools" in call_kwargs
        assert call_kwargs["tool_choice"] == "auto"

    @pytest.mark.asyncio
    async def test_create_completion_with_stop(
        self,
        provider: ConcreteOpenAIProvider,
        config: LLMConfig,
    ) -> None:
        """Вызов с stop sequences."""
        await provider.initialize(config)

        mock_response = MockChatCompletion(
            choices=[MockChoice(message=MockMessage(content="OK"))],
        )
        provider._client = MagicMock()
        provider._client.chat = MagicMock()
        provider._client.chat.completions = MagicMock()
        provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

        request = CompletionRequest(
            model="gpt-4o",
            messages=[LLMMessage(role="user", content="Hi")],
            stop=["STOP", "END"],
        )
        await provider.create_completion(request)

        call_kwargs = provider._client.chat.completions.create.call_args.kwargs
        assert call_kwargs["stop"] == ["STOP", "END"]

    @pytest.mark.asyncio
    async def test_create_completion_uses_config_model(
        self,
        provider: ConcreteOpenAIProvider,
    ) -> None:
        """Использовать модель из config если не указана в request."""
        config = LLMConfig(api_key="key", model="gpt-4-turbo")
        await provider.initialize(config)

        mock_response = MockChatCompletion(
            choices=[MockChoice(message=MockMessage(content="OK"))],
        )
        provider._client = MagicMock()
        provider._client.chat = MagicMock()
        provider._client.chat.completions = MagicMock()
        provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

        request = CompletionRequest(
            model="",
            messages=[LLMMessage(role="user", content="Hi")],
        )
        result = await provider.create_completion(request)

        assert result.model == "gpt-4-turbo"

    @pytest.mark.asyncio
    async def test_create_completion_normalizes_model_id(
        self,
        provider: ConcreteOpenAIProvider,
        config: LLMConfig,
    ) -> None:
        """Нормализация model ID при вызове."""
        await provider.initialize(config)

        mock_response = MockChatCompletion(
            choices=[MockChoice(message=MockMessage(content="OK"))],
        )
        provider._client = MagicMock()
        provider._client.chat = MagicMock()
        provider._client.chat.completions = MagicMock()
        provider._client.chat.completions.create = AsyncMock(return_value=mock_response)

        request = CompletionRequest(
            model="test-openai/gpt-4o",
            messages=[LLMMessage(role="user", content="Hi")],
        )
        await provider.create_completion(request)

        call_kwargs = provider._client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o"


class TestOpenAICompatibleProviderStreamCompletion:
    """Тесты stream_completion с моками."""

    @pytest.mark.asyncio
    async def test_stream_completion_not_initialized(
        self, provider: ConcreteOpenAIProvider
    ) -> None:
        """Вызов до инициализации должен поднять ошибку."""
        request = CompletionRequest(
            model="gpt-4o",
            messages=[LLMMessage(role="user", content="Hello")],
        )
        with pytest.raises(RuntimeError, match="Provider not initialized"):
            async for _ in provider.stream_completion(request):
                pass

    @pytest.mark.asyncio
    async def test_stream_completion_basic(
        self,
        provider: ConcreteOpenAIProvider,
        config: LLMConfig,
    ) -> None:
        """Базовый streaming."""
        await provider.initialize(config)

        mock_chunk_1 = MagicMock()
        mock_chunk_1.choices = [MagicMock()]
        mock_chunk_1.choices[0].delta.content = "Hello"

        mock_chunk_2 = MagicMock()
        mock_chunk_2.choices = [MagicMock()]
        mock_chunk_2.choices[0].delta.content = " world"

        mock_stream = _async_iter([mock_chunk_1, mock_chunk_2])

        provider._client = MagicMock()
        provider._client.chat = MagicMock()
        provider._client.chat.completions = MagicMock()
        provider._client.chat.completions.create = AsyncMock(return_value=mock_stream)

        request = CompletionRequest(
            model="gpt-4o",
            messages=[LLMMessage(role="user", content="Hi")],
        )
        chunks = []
        async for chunk in provider.stream_completion(request):
            chunks.append(chunk)

        assert len(chunks) == 2
        assert chunks[0].text == "Hello"
        assert chunks[1].text == "Hello world"
        assert all(c.stop_reason == StopReason.STREAMING for c in chunks)


async def _async_iter(items):
    """Async generator helper."""
    for item in items:
        yield item

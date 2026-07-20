"""Coverage tests for LiteLLMProvider."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from litellm.exceptions import (
    AuthenticationError,
    BadRequestError,
    RateLimitError,
    ServiceUnavailableError,
)
from litellm.exceptions import (
    Timeout as LiteLLMTimeout,
)

from codelab.server.llm.base import LLMConfig
from codelab.server.llm.content_parts import ContentPart
from codelab.server.llm.errors import ProviderError, ProviderErrorType
from codelab.server.llm.models import (
    CompletionRequest,
    LLMMessage,
    StopReason,
)
from codelab.server.llm.providers.litellm_provider import LiteLLMProvider


@pytest.fixture
def provider() -> LiteLLMProvider:
    return LiteLLMProvider()


def _config(
    *,
    api_key: str | None = "test-key",
    base_url: str | None = "https://proxy.example.com",
    model: str | None = "openai/gpt-4o",
) -> LLMConfig:
    return LLMConfig(api_key=api_key, base_url=base_url, model=model or "openai/gpt-4o")


@pytest.fixture
async def initialized_provider() -> LiteLLMProvider:
    p = LiteLLMProvider()
    await p.initialize(_config())
    return p


@dataclass
class _FakeUsage:
    prompt_tokens: int = 10
    completion_tokens: int = 20
    total_tokens: int = 30


@dataclass
class _FakeFunction:
    name: str | None = None
    arguments: str | dict[str, Any] | None = None


@dataclass
class _FakeToolCall:
    id: str
    type: str = "function"
    function: _FakeFunction | None = None


@dataclass
class _FakeMessage:
    content: str | None = None
    tool_calls: list[_FakeToolCall] | None = None


@dataclass
class _FakeChoice:
    message: _FakeMessage
    finish_reason: str = "stop"


@dataclass
class _FakeResponse:
    choices: list[_FakeChoice]
    usage: _FakeUsage | None = None


@dataclass
class _FakeDelta:
    content: str | None = None
    tool_calls: list[_FakeToolCall] | None = None


@dataclass
class _FakeStreamChoice:
    delta: _FakeDelta | None = None
    finish_reason: str | None = None


@dataclass
class _FakeStreamChunk:
    choices: list[_FakeStreamChoice] = field(default_factory=list)
    usage: _FakeUsage | None = None


class _FakeAsyncStream:
    """Async-iterable, возвращающая заданные chunk-и."""

    def __init__(self, chunks: list[_FakeStreamChunk]) -> None:
        self._chunks = chunks

    def __aiter__(self) -> AsyncIterator[_FakeStreamChunk]:
        return self._aiter()

    async def _aiter(self) -> AsyncIterator[_FakeStreamChunk]:
        for chunk in self._chunks:
            yield chunk


class TestLiteLLMProviderBasics:
    """Базовые свойства и initialize."""

    def test_name(self, provider: LiteLLMProvider) -> None:
        assert provider.name == "litellm"

    def test_capabilities(self, provider: LiteLLMProvider) -> None:
        caps = provider.capabilities
        assert caps.supports_tools is True
        assert caps.supports_streaming is True
        assert caps.supports_function_calling is True
        assert caps.supports_vision is True
        assert caps.supports_audio is True
        assert caps.supports_system_prompt is True

    async def test_initialize_stores_config(
        self, provider: LiteLLMProvider
    ) -> None:
        cfg = _config()
        await provider.initialize(cfg)
        assert provider._config is cfg


class TestResolveModel:
    """_resolve_model: приоритеты выбора модели."""

    def test_request_model_wins(self, provider: LiteLLMProvider) -> None:
        provider._config = _config(model="openai/gpt-4o")
        assert provider._resolve_model("bedrock/claude") == "bedrock/claude"

    def test_config_model_when_request_empty(
        self, provider: LiteLLMProvider
    ) -> None:
        provider._config = _config(model="openai/gpt-4o-mini")
        assert provider._resolve_model("") == "openai/gpt-4o-mini"

    def test_default_when_both_empty(self, provider: LiteLLMProvider) -> None:
        provider._config = LLMConfig(model="")
        assert provider._resolve_model("") == "gpt-4o"

    def test_strips_own_provider_prefix_from_request(
        self, provider: LiteLLMProvider
    ) -> None:
        # "litellm/" — внутренний селектор провайдера, litellm его не понимает.
        assert provider._resolve_model("litellm/openai/MiniMax-M3") == "openai/MiniMax-M3"

    def test_strips_own_provider_prefix_from_config(
        self, provider: LiteLLMProvider
    ) -> None:
        provider._config = _config(model="litellm/anthropic/claude-3-5-sonnet")
        assert provider._resolve_model("") == "anthropic/claude-3-5-sonnet"

    def test_keeps_backend_prefix_without_litellm_selector(
        self, provider: LiteLLMProvider
    ) -> None:
        # Уже в формате litellm — не трогаем.
        assert provider._resolve_model("openai/gpt-4o") == "openai/gpt-4o"


class TestBuildCallKwargs:
    """_build_call_kwargs: формирование параметров вызова."""

    async def test_omits_api_key_when_none(
        self, initialized_provider: LiteLLMProvider
    ) -> None:
        p = LiteLLMProvider()
        await p.initialize(LLMConfig(api_key=None, base_url=None, model="gpt-4o"))
        req = CompletionRequest(
            model="gpt-4o",
            messages=[LLMMessage(role="user", content="hi")],
        )
        kwargs = p._build_call_kwargs(request=req, model="gpt-4o", stream=False)
        assert "api_key" not in kwargs
        assert "api_base" not in kwargs

    async def test_includes_api_key_and_base_url(
        self, initialized_provider: LiteLLMProvider
    ) -> None:
        req = CompletionRequest(
            model="gpt-4o",
            messages=[LLMMessage(role="user", content="hi")],
        )
        kwargs = initialized_provider._build_call_kwargs(
            request=req, model="gpt-4o", stream=False
        )
        assert kwargs["api_key"] == "test-key"
        assert kwargs["api_base"] == "https://proxy.example.com"

    async def test_includes_timeout_from_config(
        self, initialized_provider: LiteLLMProvider
    ) -> None:
        req = CompletionRequest(
            model="gpt-4o",
            messages=[LLMMessage(role="user", content="hi")],
        )
        kwargs = initialized_provider._build_call_kwargs(
            request=req, model="gpt-4o", stream=False
        )
        assert kwargs["timeout"] == 300.0

    async def test_stream_flag(self, initialized_provider: LiteLLMProvider) -> None:
        req = CompletionRequest(
            model="gpt-4o",
            messages=[LLMMessage(role="user", content="hi")],
        )
        kwargs = initialized_provider._build_call_kwargs(
            request=req, model="gpt-4o", stream=True
        )
        assert kwargs["stream"] is True

    async def test_includes_tools(self, initialized_provider: LiteLLMProvider) -> None:
        req = CompletionRequest(
            model="gpt-4o",
            messages=[LLMMessage(role="user", content="hi")],
            tools=[{"type": "function", "function": {"name": "fn"}}],
        )
        kwargs = initialized_provider._build_call_kwargs(
            request=req, model="gpt-4o", stream=False
        )
        assert kwargs["tools"] == [
            {"type": "function", "function": {"name": "fn"}}
        ]
        assert kwargs["tool_choice"] == "auto"

    async def test_includes_stop(self, initialized_provider: LiteLLMProvider) -> None:
        req = CompletionRequest(
            model="gpt-4o",
            messages=[LLMMessage(role="user", content="hi")],
            stop=["STOP"],
        )
        kwargs = initialized_provider._build_call_kwargs(
            request=req, model="gpt-4o", stream=False
        )
        assert kwargs["stop"] == ["STOP"]


class TestCreateCompletion:
    """create_completion: успешный путь + парсинг ответа."""

    async def test_text_response(
        self, initialized_provider: LiteLLMProvider
    ) -> None:
        response = _FakeResponse(
            choices=[_FakeChoice(message=_FakeMessage(content="hello"))],
            usage=_FakeUsage(),
        )
        with patch(
            "codelab.server.llm.providers.litellm_provider.acompletion",
            new=AsyncMock(return_value=response),
        ) as mock_ac:
            result = await initialized_provider.create_completion(
                CompletionRequest(
                    model="gpt-4o",
                    messages=[LLMMessage(role="user", content="hi")],
                )
            )

        assert result.text == "hello"
        assert result.tool_calls == []
        assert result.stop_reason == StopReason.STOP_SEQUENCE
        assert result.model == "gpt-4o"
        assert result.usage == {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        }
        mock_ac.assert_awaited_once()

    async def test_tool_call_response(
        self, initialized_provider: LiteLLMProvider
    ) -> None:
        response = _FakeResponse(
            choices=[
                _FakeChoice(
                    message=_FakeMessage(
                        content="",
                        tool_calls=[
                            _FakeToolCall(
                                id="c1",
                                function=_FakeFunction(
                                    name="get_weather", arguments='{"city":"SPB"}'
                                ),
                            )
                        ],
                    ),
                    finish_reason="tool_calls",
                )
            ]
        )
        with patch(
            "codelab.server.llm.providers.litellm_provider.acompletion",
            new=AsyncMock(return_value=response),
        ):
            result = await initialized_provider.create_completion(
                CompletionRequest(
                    model="gpt-4o",
                    messages=[LLMMessage(role="user", content="weather?")],
                )
            )

        assert result.stop_reason == StopReason.TOOL_USE
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "get_weather"
        assert result.tool_calls[0].arguments == {"city": "SPB"}

    async def test_multimodal_content(
        self, initialized_provider: LiteLLMProvider
    ) -> None:
        response = _FakeResponse(
            choices=[_FakeChoice(message=_FakeMessage(content="ok"))]
        )
        with patch(
            "codelab.server.llm.providers.litellm_provider.acompletion",
            new=AsyncMock(return_value=response),
        ) as mock_ac:
            await initialized_provider.create_completion(
                CompletionRequest(
                    model="gpt-4o",
                    messages=[
                        LLMMessage(
                            role="user",
                            content=[
                                ContentPart.make_text("what is this?"),
                                ContentPart.make_image("BASE64", "image/png"),
                            ],
                        )
                    ],
                )
            )

        call_kwargs = mock_ac.call_args.kwargs
        sent_messages = call_kwargs["messages"]
        assert sent_messages[0]["content"] == [
            {"type": "text", "text": "what is this?"},
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,BASE64"},
            },
        ]

    async def test_uses_request_model(
        self, initialized_provider: LiteLLMProvider
    ) -> None:
        response = _FakeResponse(
            choices=[_FakeChoice(message=_FakeMessage(content="ok"))]
        )
        with patch(
            "codelab.server.llm.providers.litellm_provider.acompletion",
            new=AsyncMock(return_value=response),
        ) as mock_ac:
            await initialized_provider.create_completion(
                CompletionRequest(
                    model="bedrock/anthropic.claude-3-sonnet",
                    messages=[LLMMessage(role="user", content="hi")],
                )
            )
        assert (
            mock_ac.call_args.kwargs["model"] == "bedrock/anthropic.claude-3-sonnet"
        )

    async def test_not_initialized_raises(self, provider: LiteLLMProvider) -> None:
        with pytest.raises(RuntimeError, match="not initialized"):
            await provider.create_completion(
                CompletionRequest(
                    model="gpt-4o",
                    messages=[LLMMessage(role="user", content="hi")],
                )
            )


class TestStreamCompletion:
    """stream_completion: дельты + сборка tool_calls + финальный chunk."""

    async def test_streaming_text(
        self, initialized_provider: LiteLLMProvider
    ) -> None:
        chunks = [
            _FakeStreamChunk(
                choices=[_FakeStreamChoice(delta=_FakeDelta(content="Hel"))]
            ),
            _FakeStreamChunk(
                choices=[_FakeStreamChoice(delta=_FakeDelta(content="lo"))]
            ),
            _FakeStreamChunk(
                choices=[_FakeStreamChoice(finish_reason="stop")],
                usage=_FakeUsage(
                    prompt_tokens=5,
                    completion_tokens=2,
                    total_tokens=7,
                ),
            ),
        ]
        with patch(
            "codelab.server.llm.providers.litellm_provider.acompletion",
            new=AsyncMock(return_value=_FakeAsyncStream(chunks)),
        ):
            collected = []
            async for resp in initialized_provider.stream_completion(
                CompletionRequest(
                    model="gpt-4o",
                    messages=[LLMMessage(role="user", content="hi")],
                )
            ):
                collected.append(resp)

        # 2 промежуточных + 1 финальный
        assert len(collected) == 3
        assert collected[0].text == "Hel"
        assert collected[0].stop_reason == StopReason.STREAMING
        assert collected[1].text == "lo"
        assert collected[1].stop_reason == StopReason.STREAMING

        # Финальный
        final = collected[2]
        assert final.text == "Hello"
        assert final.stop_reason == StopReason.STOP_SEQUENCE
        assert final.usage == {
            "prompt_tokens": 5,
            "completion_tokens": 2,
            "total_tokens": 7,
        }

    async def test_streaming_tool_calls(
        self, initialized_provider: LiteLLMProvider
    ) -> None:
        chunks = [
            _FakeStreamChunk(
                choices=[
                    _FakeStreamChoice(
                        delta=_FakeDelta(
                            tool_calls=[
                                _FakeToolCall(
                                    id="c1",
                                    function=_FakeFunction(name="fn", arguments=""),
                                )
                            ]
                        )
                    )
                ]
            ),
            _FakeStreamChunk(
                choices=[
                    _FakeStreamChoice(
                        delta=_FakeDelta(
                            tool_calls=[
                                _FakeToolCall(
                                    id="c1",
                                    function=_FakeFunction(
                                        name=None, arguments='{"k":'
                                    ),
                                )
                            ]
                        )
                    )
                ]
            ),
            _FakeStreamChunk(
                choices=[
                    _FakeStreamChoice(
                        delta=_FakeDelta(
                            tool_calls=[
                                _FakeToolCall(id="c1", function=_FakeFunction(arguments='"v"}'))
                            ]
                        ),
                        finish_reason="tool_calls",
                    )
                ]
            ),
        ]
        with patch(
            "codelab.server.llm.providers.litellm_provider.acompletion",
            new=AsyncMock(return_value=_FakeAsyncStream(chunks)),
        ):
            collected = []
            async for resp in initialized_provider.stream_completion(
                CompletionRequest(
                    model="gpt-4o",
                    messages=[LLMMessage(role="user", content="hi")],
                    tools=[{"type": "function", "function": {"name": "fn"}}],
                )
            ):
                collected.append(resp)

        final = collected[-1]
        assert final.stop_reason == StopReason.TOOL_USE
        assert len(final.tool_calls) == 1
        assert final.tool_calls[0].id == "c1"
        assert final.tool_calls[0].name == "fn"
        assert final.tool_calls[0].arguments == {"k": "v"}

    async def test_streaming_chunks_without_choices_skipped(
        self, initialized_provider: LiteLLMProvider
    ) -> None:
        chunks = [
            _FakeStreamChunk(choices=[]),
            _FakeStreamChunk(
                choices=[_FakeStreamChoice(delta=_FakeDelta(content="x"))]
            ),
        ]
        with patch(
            "codelab.server.llm.providers.litellm_provider.acompletion",
            new=AsyncMock(return_value=_FakeAsyncStream(chunks)),
        ):
            collected = []
            async for resp in initialized_provider.stream_completion(
                CompletionRequest(
                    model="gpt-4o",
                    messages=[LLMMessage(role="user", content="hi")],
                )
            ):
                collected.append(resp)

        # 1 дельта + 1 финальный
        assert len(collected) == 2
        assert collected[0].text == "x"


class TestMapException:
    """_map_exception: маппинг litellm-исключений в ProviderError."""

    def test_authentication_error(self, provider: LiteLLMProvider) -> None:
        exc = AuthenticationError(
            message="bad key", llm_provider="openai", model="gpt-4o"
        )
        err = provider._map_exception(exc)
        assert isinstance(err, ProviderError)
        assert err.error_type == ProviderErrorType.AUTH_ERROR
        assert err.retryable is False
        assert err.provider_id == "litellm"

    def test_rate_limit_error(self, provider: LiteLLMProvider) -> None:
        exc = RateLimitError(
            message="slow down", llm_provider="openai", model="gpt-4o"
        )
        err = provider._map_exception(exc)
        assert err.error_type == ProviderErrorType.RATE_LIMIT
        assert err.retryable is True

    def test_timeout_error(self, provider: LiteLLMProvider) -> None:
        exc = LiteLLMTimeout(
            message="timed out", llm_provider="openai", model="gpt-4o"
        )
        err = provider._map_exception(exc)
        assert err.error_type == ProviderErrorType.TIMEOUT
        assert err.retryable is True

    def test_service_unavailable_error(self, provider: LiteLLMProvider) -> None:
        exc = ServiceUnavailableError(
            message="down", llm_provider="openai", model="gpt-4o"
        )
        err = provider._map_exception(exc)
        assert err.error_type == ProviderErrorType.SERVICE_UNAVAILABLE
        assert err.retryable is True

    def test_bad_request_error(self, provider: LiteLLMProvider) -> None:
        exc = BadRequestError(
            message="bad req", llm_provider="openai", model="gpt-4o"
        )
        err = provider._map_exception(exc)
        assert err.error_type == ProviderErrorType.INVALID_REQUEST
        assert err.retryable is False

    def test_unknown_error(self, provider: LiteLLMProvider) -> None:
        err = provider._map_exception(ValueError("oops"))
        assert err.error_type == ProviderErrorType.UNKNOWN
        assert err.provider_id == "litellm"


class TestErrorPropagation:
    """create_completion/stream_completion оборачивают исключения в ProviderError."""

    async def test_create_completion_raises_provider_error(
        self, initialized_provider: LiteLLMProvider
    ) -> None:
        exc = AuthenticationError(
            message="bad", llm_provider="openai", model="gpt-4o"
        )
        with patch(
            "codelab.server.llm.providers.litellm_provider.acompletion",
            new=AsyncMock(side_effect=exc),
        ):
            with pytest.raises(ProviderError) as exc_info:
                await initialized_provider.create_completion(
                    CompletionRequest(
                        model="gpt-4o",
                        messages=[LLMMessage(role="user", content="hi")],
                    )
                )
        assert exc_info.value.error_type == ProviderErrorType.AUTH_ERROR
        assert exc_info.value.__cause__ is exc

    async def test_stream_completion_raises_provider_error(
        self, initialized_provider: LiteLLMProvider
    ) -> None:
        exc = RateLimitError(
            message="rl", llm_provider="openai", model="gpt-4o"
        )
        with patch(
            "codelab.server.llm.providers.litellm_provider.acompletion",
            new=AsyncMock(side_effect=exc),
        ):
            with pytest.raises(ProviderError) as exc_info:
                async for _ in initialized_provider.stream_completion(
                    CompletionRequest(
                        model="gpt-4o",
                        messages=[LLMMessage(role="user", content="hi")],
                    )
                ):
                    pass
        assert exc_info.value.error_type == ProviderErrorType.RATE_LIMIT
        assert exc_info.value.__cause__ is exc

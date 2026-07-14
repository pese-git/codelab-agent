"""Интеграционный тест LiteLLMProvider через Registry и Resolver.

Проверяет полный поток:
- Регистрация LiteLLMProvider в LLMProviderRegistry
- Резолвинг через ModelResolver
- Сквозной вызов create_completion с моком litellm.acompletion
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, patch

from codelab.server.llm.base import LLMConfig, LLMTimeoutConfig
from codelab.server.llm.models import (
    CompletionRequest,
    LLMMessage,
    ModelInfo,
    ProviderInfo,
    StopReason,
)
from codelab.server.llm.providers.litellm_provider import LiteLLMProvider
from codelab.server.llm.registry import LLMProviderRegistry
from codelab.server.llm.resolver import ModelResolver


@dataclass
class _FakeUsage:
    prompt_tokens: int = 5
    completion_tokens: int = 7
    total_tokens: int = 12


@dataclass
class _FakeMessage:
    content: str | None = None
    tool_calls: list[Any] | None = None


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


@dataclass
class _FakeStreamChoice:
    delta: _FakeDelta | None = None
    finish_reason: str | None = None


@dataclass
class _FakeStreamChunk:
    choices: list[_FakeStreamChoice] = field(default_factory=list)
    usage: _FakeUsage | None = None


class _FakeAsyncStream:
    def __init__(self, chunks: list[_FakeStreamChunk]) -> None:
        self._chunks = chunks

    def __aiter__(self) -> AsyncIterator[_FakeStreamChunk]:
        return self._aiter()

    async def _aiter(self) -> AsyncIterator[_FakeStreamChunk]:
        for c in self._chunks:
            yield c


def _make_registry_with_litellm() -> LLMProviderRegistry:
    registry = LLMProviderRegistry()
    registry.register(
        "litellm",
        LiteLLMProvider,
        info=ProviderInfo(
            id="litellm",
            name="LiteLLM",
            base_url=None,
            models=[
                ModelInfo(
                    id="openai/gpt-4o",
                    provider_id="litellm",
                    context_window=128000,
                    max_output_tokens=16384,
                )
            ],
        ),
    )
    return registry


class TestLiteLLMIntegration:
    """Сквозной сценарий Registry → Resolver → LiteLLMProvider."""

    async def test_registry_resolver_create_completion(self) -> None:
        registry = _make_registry_with_litellm()
        resolver = ModelResolver(registry, default_provider="litellm")

        provider, model_id = await resolver.resolve("litellm/openai/gpt-4o")
        assert isinstance(provider, LiteLLMProvider)
        assert model_id == "openai/gpt-4o"

        response_obj = _FakeResponse(
            choices=[_FakeChoice(message=_FakeMessage(content="hello via litellm"))],
            usage=_FakeUsage(),
        )
        with patch(
            "codelab.server.llm.providers.litellm_provider.acompletion",
            new=AsyncMock(return_value=response_obj),
        ) as mock_ac:
            result = await provider.create_completion(
                CompletionRequest(
                    model=model_id,
                    messages=[LLMMessage(role="user", content="hi")],
                )
            )

        assert result.text == "hello via litellm"
        assert result.stop_reason == StopReason.STOP_SEQUENCE
        assert result.model == "openai/gpt-4o"
        # api_key и api_base прокинуты в litellm из LLMConfig провайдера
        call_kwargs = mock_ac.call_args.kwargs
        assert call_kwargs["model"] == "openai/gpt-4o"

    async def test_registry_resolver_stream_completion(self) -> None:
        registry = _make_registry_with_litellm()
        resolver = ModelResolver(registry, default_provider="litellm")

        provider, model_id = await resolver.resolve("litellm/openai/gpt-4o")

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
                    prompt_tokens=3, completion_tokens=2, total_tokens=5
                ),
            ),
        ]
        with patch(
            "codelab.server.llm.providers.litellm_provider.acompletion",
            new=AsyncMock(return_value=_FakeAsyncStream(chunks)),
        ):
            collected = []
            async for resp in provider.stream_completion(
                CompletionRequest(
                    model=model_id,
                    messages=[LLMMessage(role="user", content="hi")],
                )
            ):
                collected.append(resp)

        # 2 дельты + 1 финальный
        assert len(collected) == 3
        assert collected[0].text == "Hel"
        assert collected[0].stop_reason == StopReason.STREAMING
        final = collected[-1]
        assert final.text == "Hello"
        assert final.stop_reason == StopReason.STOP_SEQUENCE
        assert final.usage == {
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "total_tokens": 5,
        }

    async def test_initialize_with_custom_config(self) -> None:
        registry = LLMProviderRegistry()
        registry.register("litellm", LiteLLMProvider)
        cfg = LLMConfig(
            api_key="custom-key",
            model="bedrock/anthropic.claude-3-sonnet",
            base_url="https://custom-proxy",
            timeout=LLMTimeoutConfig(read=120.0),
        )
        registry.set_default_config(cfg)

        provider = await registry.get_provider("litellm")

        assert provider._config is not None
        assert provider._config.api_key == "custom-key"
        assert provider._config.base_url == "https://custom-proxy"
        assert provider._config.timeout.read == 120.0

"""Coverage tests for FallbackOrchestrator uncovered lines."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codelab.server.llm.base import CompletionRequest, LLMMessage
from codelab.server.llm.errors import (
    AllProvidersFailed,
    ProviderError,
    ProviderErrorType,
)
from codelab.server.llm.fallback.config import FallbackConfig
from codelab.server.llm.fallback.orchestrator import FallbackOrchestrator
from codelab.server.llm.fallback.sequential import SequentialFallback
from codelab.server.llm.models import CompletionResponse, StopReason


def _make_error_provider(name: str, error: ProviderError) -> MagicMock:
    """Create a mock provider that raises an error on completion."""
    provider = MagicMock()
    provider.name = name
    provider.create_completion = AsyncMock(side_effect=error)
    return provider


def _make_stream_provider(name: str, chunks: list[CompletionResponse]) -> MagicMock:
    """Create a mock provider that yields streaming chunks."""
    provider = MagicMock()
    provider.name = name

    async def _stream(request: CompletionRequest) -> None:
        for chunk in chunks:
            yield chunk

    provider.stream_completion = _stream
    return provider


class TestFallbackOrchestratorCoverage:
    """Tests covering uncovered lines in FallbackOrchestrator."""

    @pytest.mark.asyncio
    async def test_all_providers_failed_after_exhausting_attempts(self) -> None:
        """Raise AllProvidersFailed when all retryable attempts are exhausted."""
        config = FallbackConfig(
            enabled=True,
            max_attempts=2,
            retry_on=[
                ProviderErrorType.RATE_LIMIT,
                ProviderErrorType.TIMEOUT,
                ProviderErrorType.SERVICE_UNAVAILABLE,
            ],
        )
        strategy = SequentialFallback()
        orchestrator = FallbackOrchestrator(strategy, config)

        primary = _make_error_provider(
            "openai",
            ProviderError("Rate limited", error_type=ProviderErrorType.RATE_LIMIT),
        )
        secondary = _make_error_provider(
            "anthropic",
            ProviderError("Timeout", error_type=ProviderErrorType.TIMEOUT),
        )

        request = CompletionRequest(
            model="gpt-4o",
            messages=[LLMMessage(role="user", content="Hi")],
        )

        with pytest.raises(AllProvidersFailed) as exc_info:
            await orchestrator.execute_completion([primary, secondary], request)

        assert len(exc_info.value.errors) == 2
        assert exc_info.value.errors[0].provider_id == "openai"
        assert exc_info.value.errors[1].provider_id == "anthropic"

    @pytest.mark.asyncio
    async def test_execute_streaming_disabled_uses_first_provider(self) -> None:
        """When fallback is disabled, streaming uses the first provider directly."""
        config = FallbackConfig(enabled=False)
        strategy = SequentialFallback()
        orchestrator = FallbackOrchestrator(strategy, config)

        chunks = [
            CompletionResponse(text="Hello", stop_reason=StopReason.STREAMING, model="gpt-4o"),
            CompletionResponse(
                text="Hello world", stop_reason=StopReason.STREAMING, model="gpt-4o"
            ),
        ]
        provider = _make_stream_provider("openai", chunks)

        request = CompletionRequest(
            model="gpt-4o",
            messages=[LLMMessage(role="user", content="Hi")],
        )

        result = []
        async for chunk in orchestrator.execute_streaming([provider], request):
            result.append(chunk)

        assert [c.text for c in result] == ["Hello", "Hello world"]

    @pytest.mark.asyncio
    async def test_execute_streaming_enabled_uses_first_provider(self) -> None:
        """When fallback is enabled, streaming still uses the first provider with a warning."""
        config = FallbackConfig(enabled=True)
        strategy = SequentialFallback()
        orchestrator = FallbackOrchestrator(strategy, config)

        chunks = [
            CompletionResponse(text="Chunk", stop_reason=StopReason.STREAMING, model="gpt-4o"),
        ]
        provider = _make_stream_provider("openai", chunks)

        request = CompletionRequest(
            model="gpt-4o",
            messages=[LLMMessage(role="user", content="Hi")],
        )

        with patch("codelab.server.llm.fallback.orchestrator.logger.warning") as mock_warning:
            result = []
            async for chunk in orchestrator.execute_streaming([provider], request):
                result.append(chunk)

        assert [c.text for c in result] == ["Chunk"]
        mock_warning.assert_called_once_with(
            "streaming fallback not supported, using first provider"
        )

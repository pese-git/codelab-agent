"""Coverage tests for SequentialFallback circuit breaker branches."""

from unittest.mock import MagicMock

import pytest

from codelab.server.llm.errors import ProviderError, ProviderErrorType
from codelab.server.llm.fallback.base import FallbackContext
from codelab.server.llm.fallback.sequential import SequentialFallback


def _make_mock_provider(name: str) -> MagicMock:
    """Create a simple mock provider with the given name."""
    provider = MagicMock()
    provider.name = name
    return provider


class TestSequentialFallbackCircuitBreakerCoverage:
    """Tests covering SequentialFallback circuit breaker branches."""

    @pytest.mark.asyncio
    async def test_select_provider_skips_open_circuit(self) -> None:
        """Provider with an open circuit breaker must be skipped."""
        circuit_breaker = MagicMock()
        circuit_breaker.is_circuit_open = MagicMock(side_effect=lambda pid: pid == "openai")

        fallback = SequentialFallback(circuit_breaker=circuit_breaker)
        candidates = [
            _make_mock_provider("openai"),
            _make_mock_provider("anthropic"),
        ]
        context = FallbackContext()

        provider = await fallback.select_provider(candidates, {}, context)

        assert provider.name == "anthropic"
        circuit_breaker.is_circuit_open.assert_any_call("openai")

    def test_on_success_records_success_on_circuit_breaker(self) -> None:
        """on_success must record success on the circuit breaker."""
        circuit_breaker = MagicMock()
        fallback = SequentialFallback(circuit_breaker=circuit_breaker)

        fallback.on_success("openai")

        circuit_breaker.record_success.assert_called_once_with("openai")

    def test_on_failure_records_failure_on_circuit_breaker(self) -> None:
        """on_failure must record failure on the circuit breaker."""
        circuit_breaker = MagicMock()
        fallback = SequentialFallback(circuit_breaker=circuit_breaker)
        error = ProviderError("Timeout", error_type=ProviderErrorType.TIMEOUT)

        fallback.on_failure("openai", error)

        circuit_breaker.record_failure.assert_called_once_with("openai", error)

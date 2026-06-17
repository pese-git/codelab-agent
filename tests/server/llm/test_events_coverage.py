"""Coverage tests for ProviderEventBus uncovered branches."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from codelab.server.llm.events import (
    FallbackTriggered,
    ModelsUpdated,
    ProviderEvent,
    ProviderEventBus,
    ProviderInitialized,
)


@dataclass
class CustomProviderEvent(ProviderEvent):
    """Custom event subtype used to trigger the fallback logging branch."""

    detail: str = ""


class TestProviderEventBusCoverage:
    """Tests covering listener exception handling and all _log_event branches."""

    @pytest.mark.asyncio
    async def test_global_listener_exception_is_logged(self) -> None:
        """Exceptions from global listeners must be caught and logged."""
        bus = ProviderEventBus()
        failing_listener = AsyncMock(side_effect=RuntimeError("global listener failed"))
        bus.subscribe_all(failing_listener)

        with patch("codelab.server.llm.events.logger") as mock_logger:
            await bus.publish(ProviderInitialized(provider_id="openai", model="gpt-4o"))

        failing_listener.assert_awaited_once()
        mock_logger.error.assert_called_once()
        assert mock_logger.error.call_args.kwargs["event_type"] == "ProviderInitialized"

    @pytest.mark.asyncio
    async def test_specific_listener_exception_is_logged(self) -> None:
        """Exceptions from specific listeners must be caught and logged."""
        bus = ProviderEventBus()
        failing_listener = AsyncMock(side_effect=RuntimeError("specific listener failed"))
        bus.subscribe(ProviderInitialized, failing_listener)

        with patch("codelab.server.llm.events.logger") as mock_logger:
            await bus.publish(ProviderInitialized(provider_id="openai", model="gpt-4o"))

        failing_listener.assert_awaited_once()
        mock_logger.error.assert_called_once()
        assert mock_logger.error.call_args.kwargs["event_type"] == "ProviderInitialized"

    @pytest.mark.asyncio
    async def test_models_updated_event_is_logged(self) -> None:
        """ModelsUpdated event must be logged with the model count."""
        bus = ProviderEventBus()

        with patch("codelab.server.llm.events.logger") as mock_logger:
            await bus.publish(ModelsUpdated(provider_id="openai", models=["gpt-4o", "gpt-4-turbo"]))

        mock_logger.info.assert_called_once_with(
            "models updated",
            provider_id="openai",
            models_count=2,
        )

    @pytest.mark.asyncio
    async def test_fallback_triggered_event_is_logged(self) -> None:
        """FallbackTriggered event must be logged as a warning."""
        bus = ProviderEventBus()

        with patch("codelab.server.llm.events.logger") as mock_logger:
            await bus.publish(
                FallbackTriggered(
                    provider_id="fallback",
                    from_provider="openai",
                    to_provider="anthropic",
                    reason="rate limit",
                )
            )

        mock_logger.warning.assert_called_once_with(
            "fallback triggered",
            from_provider="openai",
            to_provider="anthropic",
            reason="rate limit",
        )

    @pytest.mark.asyncio
    async def test_unknown_event_is_logged_as_debug(self) -> None:
        """Unknown event subtypes must be logged as debug messages."""
        bus = ProviderEventBus()

        with patch("codelab.server.llm.events.logger") as mock_logger:
            await bus.publish(CustomProviderEvent(provider_id="custom", detail="test"))

        mock_logger.debug.assert_called_once_with(
            "provider event",
            event_type="CustomProviderEvent",
            provider_id="custom",
        )

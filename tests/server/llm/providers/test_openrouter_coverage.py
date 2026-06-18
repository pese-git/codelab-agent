"""Coverage tests for OpenRouter provider."""

import pytest

from codelab.server.llm.providers.openrouter import OpenRouterProvider


@pytest.fixture
def provider() -> OpenRouterProvider:
    """Create an OpenRouterProvider instance."""
    return OpenRouterProvider()


class TestOpenRouterProvider:
    """Tests covering OpenRouterProvider initialization and name."""

    def test_name(self, provider: OpenRouterProvider) -> None:
        """Provider name must be 'openrouter'."""
        assert provider.name == "openrouter"

    def test_default_base_url(self, provider: OpenRouterProvider) -> None:
        """Default base URL must point to the OpenRouter API."""
        assert provider._base_url == "https://openrouter.ai/api/v1"

    def test_default_model(self, provider: OpenRouterProvider) -> None:
        """Default model must be 'openai/gpt-4o'."""
        assert provider._default_model == "openai/gpt-4o"

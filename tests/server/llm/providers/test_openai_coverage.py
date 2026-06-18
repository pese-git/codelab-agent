"""Coverage tests for OpenAI provider."""

import pytest

from codelab.server.llm.providers.openai import OpenAIProvider


@pytest.fixture
def provider() -> OpenAIProvider:
    """Create an OpenAIProvider instance."""
    return OpenAIProvider()


class TestOpenAIProvider:
    """Tests covering OpenAIProvider initialization and name."""

    def test_name(self, provider: OpenAIProvider) -> None:
        """Provider name must be 'openai'."""
        assert provider.name == "openai"

    def test_default_base_url(self, provider: OpenAIProvider) -> None:
        """Default base URL must be None to use the standard OpenAI endpoint."""
        assert provider._base_url is None

    def test_default_model(self, provider: OpenAIProvider) -> None:
        """Default model must be 'gpt-4o'."""
        assert provider._default_model == "gpt-4o"

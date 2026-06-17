"""Coverage tests for Go provider."""

import pytest

from codelab.server.llm.providers.go import GoProvider


@pytest.fixture
def provider() -> GoProvider:
    """Create a GoProvider instance."""
    return GoProvider()


class TestGoProvider:
    """Tests covering GoProvider initialization and name."""

    def test_name(self, provider: GoProvider) -> None:
        """Provider name must be 'go'."""
        assert provider.name == "go"

    def test_default_base_url(self, provider: GoProvider) -> None:
        """Default base URL must point to the Go API."""
        assert provider._base_url == "https://go.opencode.ai/v1"

    def test_default_model(self, provider: GoProvider) -> None:
        """Default model must be 'gpt-4o'."""
        assert provider._default_model == "gpt-4o"

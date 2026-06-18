"""Coverage tests for Zen provider."""

import pytest

from codelab.server.llm.providers.zen import ZenProvider


@pytest.fixture
def provider() -> ZenProvider:
    """Create a ZenProvider instance."""
    return ZenProvider()


class TestZenProvider:
    """Tests covering ZenProvider initialization and name."""

    def test_name(self, provider: ZenProvider) -> None:
        """Provider name must be 'zen'."""
        assert provider.name == "zen"

    def test_default_base_url(self, provider: ZenProvider) -> None:
        """Default base URL must point to the Zen API."""
        assert provider._base_url == "https://zen.opencode.ai/v1"

    def test_default_model(self, provider: ZenProvider) -> None:
        """Default model must be 'claude-sonnet-4'."""
        assert provider._default_model == "claude-sonnet-4"

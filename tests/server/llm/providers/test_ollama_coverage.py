"""Coverage tests for Ollama provider."""

import pytest

from codelab.server.llm.providers.ollama import OllamaProvider


@pytest.fixture
def provider() -> OllamaProvider:
    """Create an OllamaProvider instance."""
    return OllamaProvider()


class TestOllamaProvider:
    """Tests covering OllamaProvider initialization and name."""

    def test_name(self, provider: OllamaProvider) -> None:
        """Provider name must be 'ollama'."""
        assert provider.name == "ollama"

    def test_default_base_url(self, provider: OllamaProvider) -> None:
        """Default base URL must point to the local Ollama server."""
        assert provider._base_url == "http://localhost:11434/v1"

    def test_default_model(self, provider: OllamaProvider) -> None:
        """Default model must be 'llama3.1:8b'."""
        assert provider._default_model == "llama3.1:8b"

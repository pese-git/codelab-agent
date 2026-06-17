"""Ollama провайдер.

OpenAI-compatible провайдер для локального Ollama API.
"""

from __future__ import annotations

from codelab.server.llm.providers.openai_compatible import OpenAICompatibleProvider


class OllamaProvider(OpenAICompatibleProvider):
    """Провайдер для Ollama API.

    Ollama — локальный сервер для запуска LLM моделей.
    """

    def __init__(self) -> None:
        """Инициализация."""
        super().__init__(
            base_url="http://localhost:11434/v1",
            default_model="llama3.1:8b",
        )

    @property
    def name(self) -> str:
        """Имя провайдера."""
        return "ollama"

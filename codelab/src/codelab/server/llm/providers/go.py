"""OpenCode Go провайдер.

OpenAI-compatible провайдер для Go API.
"""

from __future__ import annotations

from codelab.server.llm.providers.openai_compatible import OpenAICompatibleProvider


class GoProvider(OpenAICompatibleProvider):
    """Провайдер для OpenCode Go API."""

    def __init__(self) -> None:
        """Инициализация."""
        super().__init__(
            base_url="https://go.opencode.ai/v1",
            default_model="gpt-4o",
        )

    @property
    def name(self) -> str:
        """Имя провайдера."""
        return "go"

"""OpenCode Zen провайдер.

OpenAI-compatible провайдер для Zen API.
"""

from __future__ import annotations

from codelab.server.llm.providers.openai_compatible import OpenAICompatibleProvider


class ZenProvider(OpenAICompatibleProvider):
    """Провайдер для OpenCode Zen API."""

    def __init__(self) -> None:
        """Инициализация."""
        super().__init__(
            base_url="https://zen.opencode.ai/v1",
            default_model="claude-sonnet-4",
        )

    @property
    def name(self) -> str:
        """Имя провайдера."""
        return "zen"

"""OpenRouter провайдер.

OpenAI-compatible провайдер для OpenRouter API.
"""

from __future__ import annotations

from codelab.server.llm.providers.openai_compatible import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    """Провайдер для OpenRouter API.

    OpenRouter — агрегатор LLM моделей от разных провайдеров.
    """

    def __init__(self) -> None:
        """Инициализация."""
        super().__init__(
            base_url="https://openrouter.ai/api/v1",
            default_model="openai/gpt-4o",
        )

    @property
    def name(self) -> str:
        """Имя провайдера."""
        return "openrouter"

"""LM Studio провайдер.

OpenAI-compatible провайдер для локального LM Studio API.
"""

from __future__ import annotations

from codelab.server.llm.providers.openai_compatible import OpenAICompatibleProvider


class LMStudioProvider(OpenAICompatibleProvider):
    """Провайдер для LM Studio API.

    LM Studio — десктопное приложение для запуска LLM моделей локально.
    """

    def __init__(self) -> None:
        """Инициализация."""
        super().__init__(
            base_url="http://localhost:1234/v1",
            default_model="local-model",
        )

    @property
    def name(self) -> str:
        """Имя провайдера."""
        return "lmstudio"

"""OpenAI LLM провайдер.

Наследуется от OpenAICompatibleProvider.
"""

from __future__ import annotations

from codelab.server.llm.providers.openai_compatible import OpenAICompatibleProvider


class OpenAIProvider(OpenAICompatibleProvider):
    """Провайдер для взаимодействия с OpenAI API.

    Наследует всю логику от OpenAICompatibleProvider.
    """

    def __init__(self) -> None:
        """Инициализация провайдера."""
        super().__init__(
            base_url=None,  # Использовать стандартный OpenAI URL
            default_model="gpt-4o",
        )

    @property
    def name(self) -> str:
        """Имя провайдера."""
        return "openai"

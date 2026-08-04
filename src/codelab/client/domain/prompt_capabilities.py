"""Ошибка неподдерживаемого контента промпта.

Сам VO возможностей промпта живёт в `codelab.shared.prompt_capabilities`: по ACP это
`agentCapabilities.promptCapabilities`, о которых говорят обе стороны, поэтому тип
общий (Shared Kernel). Здесь остаётся клиентское исключение — оно про поведение
клиента, а не про форму протокола.
"""

from __future__ import annotations

from codelab.shared.prompt_capabilities import PromptCapabilities

__all__ = ["PromptCapabilities", "UnsupportedContentError"]


class UnsupportedContentError(Exception):
    """Исключение при попытке отправить неподдерживаемый контент."""

    def __init__(self, content_type: str, capabilities: PromptCapabilities) -> None:
        self.content_type = content_type
        self.capabilities = capabilities
        super().__init__(
            f"Agent does not support {content_type} content "
            f"(promptCapabilities.{self._capability_name} is false)"
        )

    @property
    def _capability_name(self) -> str:
        """Имя capability для сообщения об ошибке."""
        mapping = {
            "image": "image",
            "audio": "audio",
            "resource": "embeddedContext",
        }
        return mapping.get(self.content_type, self.content_type)

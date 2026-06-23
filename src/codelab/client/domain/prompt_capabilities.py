"""Prompt Capabilities - domain модель для возможностей агента.

Инкапсулирует promptCapabilities агента, полученные при инициализации.
Согласно ACP спецификации определяет, какие типы контента могут быть
отправлены в промпте.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PromptCapabilities:
    """Возможности агента для обработки промптов.

    Определяет, какие типы мультимодального контента поддерживаются агентом.
    Согласно ACP спецификации (02-Initialization.md):
    - text и resource_link поддерживаются всегда (baseline)
    - image, audio, embeddedContext требуют явной поддержки

    Attributes:
        image: Поддержка изображений в промпте.
        audio: Поддержка аудио в промпте.
        embedded_context: Поддержка embedded resources в промпте.
    """

    image: bool = False
    audio: bool = False
    embedded_context: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PromptCapabilities:
        """Создает PromptCapabilities из dict.

        Args:
            data: Dict с capabilities (promptCapabilities из agentCapabilities).

        Returns:
            PromptCapabilities instance.
        """
        if data is None:
            return cls()
        return cls(
            image=bool(data.get("image", False)),
            audio=bool(data.get("audio", False)),
            embedded_context=bool(data.get("embeddedContext", False)),
        )

    @classmethod
    def from_server_capabilities(
        cls,
        server_capabilities: dict[str, Any] | None,
    ) -> PromptCapabilities:
        """Извлекает PromptCapabilities из server_capabilities.

        Args:
            server_capabilities: Полные capabilities сервера из initialize response.

        Returns:
            PromptCapabilities instance.
        """
        if server_capabilities is None:
            return cls()
        prompt_caps = server_capabilities.get("promptCapabilities")
        return cls.from_dict(prompt_caps)

    def supports_image(self) -> bool:
        """Проверяет поддержку изображений."""
        return self.image

    def supports_audio(self) -> bool:
        """Проверяет поддержку аудио."""
        return self.audio

    def supports_embedded_context(self) -> bool:
        """Проверяет поддержку embedded resources."""
        return self.embedded_context

    def supports_multimodal(self) -> bool:
        """Проверяет поддержку любого мультимодального контента."""
        return self.image or self.audio or self.embedded_context

    def to_dict(self) -> dict[str, Any]:
        """Сериализует в dict."""
        return {
            "image": self.image,
            "audio": self.audio,
            "embeddedContext": self.embedded_context,
        }


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

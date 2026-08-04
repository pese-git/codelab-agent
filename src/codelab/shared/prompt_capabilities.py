"""PromptCapabilities — общий доменный VO мультимодальных возможностей промпта.

По ACP (``02-Initialization.md``) ``image``/``audio``/``embeddedContext`` входят в
``agentCapabilities.promptCapabilities``: это возможности **агента** принимать такой
контент в промпте. Клиент их читает из ответа ``initialize``, агент — объявляет.
Обе стороны говорят об одном и том же, поэтому тип живёт в Shared Kernel рядом с
``ClientCapabilities`` (там — возможности клиента: файловая система и терминал).

Форму задаёт спецификация ACP, а не внутренняя модель одной из сторон: ключи
``to_dict``/``from_dict`` — ровно wire-имена (``embeddedContext`` в camelCase).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PromptCapabilities:
    """Мультимодальные возможности промпта, объявляемые агентом.

    ACP baseline: ``text`` и ``resource_link`` поддерживаются всегда и в этот VO
    не входят. Явной поддержки требуют только три типа ниже.

    Атрибуты:
        image: Изображения в промпте.
        audio: Аудио в промпте.
        embedded_context: Встроенные ресурсы (embedded resources).
    """

    image: bool = False
    audio: bool = False
    embedded_context: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PromptCapabilities:
        """Собрать VO из ACP-словаря ``promptCapabilities``.

        Args:
            data: Словарь ``promptCapabilities`` либо ``None`` (возможностей нет).
        """
        if data is None:
            return cls()
        return cls(
            image=bool(data.get("image", False)),
            audio=bool(data.get("audio", False)),
            embedded_context=bool(data.get("embeddedContext", False)),
        )

    @classmethod
    def from_agent_capabilities(
        cls,
        agent_capabilities: dict[str, Any] | None,
    ) -> PromptCapabilities:
        """Извлечь возможности промпта из ``agentCapabilities`` ответа ``initialize``."""
        if agent_capabilities is None:
            return cls()
        return cls.from_dict(agent_capabilities.get("promptCapabilities"))

    def supports_image(self) -> bool:
        """Поддержка изображений."""
        return self.image

    def supports_audio(self) -> bool:
        """Поддержка аудио."""
        return self.audio

    def supports_embedded_context(self) -> bool:
        """Поддержка встроенных ресурсов."""
        return self.embedded_context

    def supports_multimodal(self) -> bool:
        """Поддержка хотя бы одного мультимодального типа."""
        return self.image or self.audio or self.embedded_context

    def to_dict(self) -> dict[str, Any]:
        """Сериализовать в ACP wire-форму (``embeddedContext`` — camelCase)."""
        return {
            "image": self.image,
            "audio": self.audio,
            "embeddedContext": self.embedded_context,
        }

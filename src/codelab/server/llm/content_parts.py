"""Доменная модель для multimodal содержимого.

ContentPart — frozen dataclass, представляющий одну часть содержимого
в pipeline обработки промпта. Неизменяемый, типобезопасный.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ContentPart:
    """Часть содержимого промпта.

    Атрибуты:
        type: Тип содержимого ("text", "image" или "audio").
        text: Текстовое содержимое (для type="text").
        data: Base64 данные (для type="image" или type="audio").
        mime_type: MIME-тип (для type="image" или type="audio").
    """

    type: Literal["text", "image", "audio"]
    text: str | None = None
    data: str | None = None
    mime_type: str | None = None

    @staticmethod
    def make_text(value: str) -> ContentPart:
        """Создать текстовую часть содержимого."""
        return ContentPart(type="text", text=value)

    @staticmethod
    def make_image(data: str, mime_type: str) -> ContentPart:
        """Создать часть содержимого изображения."""
        return ContentPart(type="image", data=data, mime_type=mime_type)

    @staticmethod
    def make_audio(data: str, mime_type: str) -> ContentPart:
        """Создать часть содержимого аудио."""
        return ContentPart(type="audio", data=data, mime_type=mime_type)

    @property
    def is_multimodal(self) -> bool:
        """Возвращает True если часть не текстовая."""
        return self.type != "text"

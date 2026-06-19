"""Domain model для промпта пользователя."""

from __future__ import annotations

from dataclasses import dataclass, field

from .conversation import Image, Resource


@dataclass(frozen=True)
class UserPrompt:
    """Domain model для промпта пользователя.

    Инкапсулирует текстовое содержимое и мультимодальные данные.
    """

    text: str = ""
    resources: list[Resource] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)

    @property
    def has_multimodal(self) -> bool:
        return bool(self.resources or self.images)

    def get_text_preview(self, max_length: int = 100) -> str:
        if len(self.text) <= max_length:
            return self.text
        return self.text[:max_length] + "..."

"""Content Blocks - domain модели для мультимодального контента.

Согласно ACP спецификации (06-Content.md), content blocks представляют
отображаемую информацию, которая проходит через протокол.

Эти модели являются domain-концептами и не должны зависеть от
infrastructural деталей.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class ContentBlock(ABC):
    """Базовый класс для всех типов контента.

    Согласно ACP спецификации, все content blocks имеют поле 'type'
    и могут быть сериализованы в dict для передачи по протоколу.
    """

    @property
    @abstractmethod
    def type_name(self) -> str:
        """Имя типа контента для сериализации."""
        ...

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Сериализует content block в dict для ACP протокола.

        Возвращает:
            Dict представление для JSON-RPC сообщения.
        """
        ...


@dataclass(frozen=True)
class TextContent(ContentBlock):
    """Текстовый контент.

    Базовый тип контента, поддерживаемый всеми агентами.
    """

    text: str
    """Текстовое содержимое."""

    @property
    def type_name(self) -> str:
        return "text"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "text",
            "text": self.text,
        }


@dataclass(frozen=True)
class ImageContent(ContentBlock):
    """Изображение.

    Требует promptCapabilities.image от агента.
    """

    data: str
    """Base64-encoded image data."""

    mime_type: str
    """MIME type изображения (image/png, image/jpeg, image/gif, image/webp)."""

    uri: str | None = None
    """Опциональный URI источника изображения."""

    @property
    def type_name(self) -> str:
        return "image"

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "type": "image",
            "data": self.data,
            "mimeType": self.mime_type,
        }
        if self.uri is not None:
            result["uri"] = self.uri
        return result


@dataclass(frozen=True)
class AudioContent(ContentBlock):
    """Аудио контент.

    Требует promptCapabilities.audio от агента.
    """

    data: str
    """Base64-encoded audio data."""

    mime_type: str
    """MIME type аудио (audio/wav, audio/mp3)."""

    @property
    def type_name(self) -> str:
        return "audio"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "audio",
            "data": self.data,
            "mimeType": self.mime_type,
        }


@dataclass(frozen=True)
class ResourceContent(ContentBlock):
    """Embedded resource - встроенный ресурс.

    Предпочтительный способ включения контекста в промпт,
    так как избегает дополнительных round-trips.

    Требует promptCapabilities.embeddedContext от агента.
    """

    uri: str
    """URI ресурса."""

    text: str | None = None
    """Текстовое содержимое ресурса."""

    blob: str | None = None
    """Base64-encoded binary data (если не text)."""

    mime_type: str | None = None
    """MIME type ресурса."""

    @property
    def type_name(self) -> str:
        return "resource"

    def to_dict(self) -> dict[str, Any]:
        resource_data: dict[str, Any] = {"uri": self.uri}
        if self.text is not None:
            resource_data["text"] = self.text
        if self.blob is not None:
            resource_data["blob"] = self.blob
        if self.mime_type is not None:
            resource_data["mimeType"] = self.mime_type

        return {
            "type": "resource",
            "resource": resource_data,
        }


@dataclass(frozen=True)
class ResourceLinkContent(ContentBlock):
    """Ссылка на ресурс.

    Поддерживается всегда (baseline), не требует специальных capabilities.
    """

    uri: str
    """URI ресурса."""

    name: str
    """Человекочитаемое имя ресурса."""

    mime_type: str | None = None
    """MIME type ресурса."""

    description: str | None = None
    """Описание содержимого ресурса."""

    size: int | None = None
    """Размер ресурса в байтах."""

    @property
    def type_name(self) -> str:
        return "resource_link"

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "type": "resource_link",
            "uri": self.uri,
            "name": self.name,
        }
        if self.mime_type is not None:
            result["mimeType"] = self.mime_type
        if self.description is not None:
            result["description"] = self.description
        if self.size is not None:
            result["size"] = self.size
        return result


@dataclass(frozen=True)
class ResourceLink:
    """Упрощенная ссылка на ресурс для использования в prompts.

    Алиас для ResourceLinkContent для удобства использования.
    """

    uri: str
    name: str
    mime_type: str | None = None
    description: str | None = None
    size: int | None = None

    def to_content_block(self) -> ResourceLinkContent:
        """Преобразует в ResourceLinkContent."""
        return ResourceLinkContent(
            uri=self.uri,
            name=self.name,
            mime_type=self.mime_type,
            description=self.description,
            size=self.size,
        )


def content_blocks_to_dicts(blocks: list[ContentBlock]) -> list[dict[str, Any]]:
    """Преобразует список content blocks в list of dicts.

    Args:
        blocks: Список ContentBlock объектов.

    Returns:
        Список dict для ACP протокола.
    """
    return [block.to_dict() for block in blocks]

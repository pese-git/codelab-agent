"""Content Types для ACP протокола.

Этот пакет содержит типы контента, используемые в ACP протоколе
для передачи различных видов данных: текст, изображения, аудио,
встроенные ресурсы и ссылки на ресурсы.

Типы контента реализованы как Pydantic модели с валидацией
и используются как в серверной, так и в клиентской части.
"""

from codelab.shared.content.audio import ALLOWED_AUDIO_MIME_TYPES, AudioContent
from codelab.shared.content.base import (
    BlobResource,
    ContentBlock,
    EmbeddedResource,
    TextResource,
)
from codelab.shared.content.embedded import EmbeddedResourceContent
from codelab.shared.content.image import ALLOWED_IMAGE_MIME_TYPES, ImageContent
from codelab.shared.content.resource_link import ResourceLinkContent
from codelab.shared.content.text import TextContent

__all__ = [
    # Базовые типы ресурсов
    "TextResource",
    "BlobResource",
    "EmbeddedResource",
    "ContentBlock",
    # Типы контента
    "TextContent",
    "ImageContent",
    "AudioContent",
    "EmbeddedResourceContent",
    "ResourceLinkContent",
    # Константы
    "ALLOWED_IMAGE_MIME_TYPES",
    "ALLOWED_AUDIO_MIME_TYPES",
]

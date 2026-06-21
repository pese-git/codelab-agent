"""Content Builder - domain service для построения content blocks.

Отвечает за:
- Валидацию контента против capabilities агента
- Построение списка content blocks для отправки
- Преобразование domain моделей в dict для ACP протокола
"""

from __future__ import annotations

from typing import Any

from .content_blocks import (
    AudioContent,
    ContentBlock,
    ImageContent,
    ResourceContent,
    ResourceLinkContent,
    TextContent,
)
from .prompt_capabilities import PromptCapabilities, UnsupportedContentError


class ContentBuilder:
    """Domain service для построения content blocks.

    Инкапсулирует бизнес-логику проверки capabilities и формирования
    списка content blocks для отправки в промпте.

    Согласно ACP спецификации:
    - text и resource_link поддерживаются всегда (baseline)
    - image требует promptCapabilities.image
    - audio требует promptCapabilities.audio
    - resource требует promptCapabilities.embeddedContext
    """

    def build_prompt_content(
        self,
        text: str | None,
        capabilities: PromptCapabilities,
        images: list[ImageContent] | None = None,
        audio: list[AudioContent] | None = None,
        resources: list[ResourceContent] | None = None,
        resource_links: list[ResourceLinkContent] | None = None,
    ) -> list[ContentBlock]:
        """Строит список content blocks для промпта.

        Проверяет capabilities агента и формирует список content blocks.
        Text и resource_link поддерживаются всегда, для остальных типов
        проверяются соответствующие capabilities.

        Args:
            text: Текстовый контент (обязательный).
            capabilities: Prompt capabilities агента.
            images: Список изображений (требует image capability).
            audio: Список аудио (требует audio capability).
            resources: Список embedded resources (требует embeddedContext).
            resource_links: Список ссылок на ресурсы (baseline).

        Returns:
            Список ContentBlock объектов для отправки.

        Raises:
            UnsupportedContentError: Если агент не поддерживает тип контента.
        """
        blocks: list[ContentBlock] = []

        # 1. Текстовый контент (всегда поддерживается)
        if text:
            blocks.append(TextContent(text=text))

        # 2. Изображения (требует image capability)
        if images:
            self._validate_capability(
                capabilities.supports_image(),
                "image",
                capabilities,
            )
            blocks.extend(images)

        # 3. Аудио (требует audio capability)
        if audio:
            self._validate_capability(
                capabilities.supports_audio(),
                "audio",
                capabilities,
            )
            blocks.extend(audio)

        # 4. Embedded resources (требует embeddedContext capability)
        if resources:
            self._validate_capability(
                capabilities.supports_embedded_context(),
                "resource",
                capabilities,
            )
            blocks.extend(resources)

        # 5. Resource links (всегда поддерживается - baseline)
        if resource_links:
            blocks.extend(resource_links)

        return blocks

    def to_dicts(self, blocks: list[ContentBlock]) -> list[dict[str, Any]]:
        """Преобразует content blocks в list of dicts для ACP протокола.

        Args:
            blocks: Список ContentBlock объектов.

        Returns:
            Список dict для JSON-RPC сообщения.
        """
        return [block.to_dict() for block in blocks]

    def _validate_capability(
        self,
        supported: bool,
        content_type: str,
        capabilities: PromptCapabilities,
    ) -> None:
        """Проверяет поддержку типа контента.

        Args:
            supported: Поддерживается ли тип.
            content_type: Имя типа контента.
            capabilities: Prompt capabilities агента.

        Raises:
            UnsupportedContentError: Если тип не поддерживается.
        """
        if not supported:
            raise UnsupportedContentError(content_type, capabilities)

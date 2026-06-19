"""Mapper между domain UserPrompt и ACP ContentBlocks."""

from __future__ import annotations

from typing import Any

from codelab.server.domain.conversation import Image, Resource
from codelab.server.domain.prompt import UserPrompt


class PromptMapper:
    """Конвертер между domain UserPrompt и ACP content blocks."""

    @staticmethod
    def from_acp_blocks(blocks: list[dict[str, Any]]) -> UserPrompt:
        """Конвертировать ACP content blocks в domain UserPrompt."""
        text_parts: list[str] = []
        resources: list[Resource] = []
        images: list[Image] = []

        for block in blocks:
            match block.get("type"):
                case "text":
                    text_parts.append(block.get("text", ""))
                case "resource":
                    resources.append(Resource.from_acp(block))
                case "image":
                    images.append(Image.from_acp(block))

        return UserPrompt(
            text="\n".join(text_parts),
            resources=resources,
            images=images,
        )

    @staticmethod
    def to_acp_blocks(prompt: UserPrompt) -> list[dict[str, Any]]:
        """Конвертировать domain UserPrompt в ACP content blocks."""
        blocks: list[dict[str, Any]] = []
        if prompt.text:
            blocks.append({"type": "text", "text": prompt.text})
        for resource in prompt.resources:
            blocks.append(resource.to_acp())
        for image in prompt.images:
            blocks.append(image.to_acp())
        return blocks

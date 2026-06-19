"""Mapper между domain ConversationMessage и ACP Protocol HistoryMessage."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from codelab.server.domain.conversation import (
    ConversationMessage,
    Image,
    MessageContent,
    Resource,
)
from codelab.server.domain.value_objects import MessageRole
from codelab.server.models import HistoryMessage


class HistoryMapper:
    """Конвертер между domain ConversationMessage и protocol HistoryMessage."""

    @staticmethod
    def to_protocol(domain: ConversationMessage) -> HistoryMessage:
        """Конвертировать domain ConversationMessage в protocol HistoryMessage."""
        content_blocks: list[dict[str, Any]] = []
        if domain.content.text:
            content_blocks.append({"type": "text", "text": domain.content.text})
        for resource in domain.content.resources:
            content_blocks.append(resource.to_acp())
        for image in domain.content.images:
            content_blocks.append(image.to_acp())

        role_str = domain.role.value
        if role_str == "tool":
            role_str = "assistant"

        return HistoryMessage(
            role=role_str,
            content=content_blocks if content_blocks else domain.content.text,
            timestamp=domain.timestamp.isoformat() if domain.timestamp else None,
            tool_call_id=domain.tool_call_id,
        )

    @staticmethod
    def to_domain(protocol: HistoryMessage) -> ConversationMessage:
        """Конвертировать protocol HistoryMessage в domain ConversationMessage."""
        role = _parse_role(protocol.role)
        content = _parse_content(protocol.content)
        timestamp = (
            datetime.fromisoformat(protocol.timestamp)
            if protocol.timestamp
            else datetime.now()
        )
        return ConversationMessage(
            role=role,
            content=content,
            timestamp=timestamp,
            tool_call_id=protocol.tool_call_id,
        )


def _parse_role(role: str) -> MessageRole:
    try:
        return MessageRole(role)
    except ValueError:
        return MessageRole.USER


def _parse_content(content: list[Any] | str | None) -> MessageContent:
    if content is None:
        return MessageContent()
    if isinstance(content, str):
        return MessageContent(text=content)

    text_parts: list[str] = []
    resources: list[Resource] = []
    images: list[Image] = []

    for block in content:
        if isinstance(block, str):
            text_parts.append(block)
            continue
        if isinstance(block, dict):
            block_type = block.get("type", "")
            if block_type == "text":
                text_parts.append(block.get("text", ""))
            elif block_type == "resource":
                resources.append(Resource.from_acp(block))
            elif block_type == "image":
                images.append(Image.from_acp(block))
            continue
        if hasattr(block, "text") and block.text:
            text_parts.append(block.text)

    return MessageContent(text="\n".join(text_parts), resources=resources, images=images)

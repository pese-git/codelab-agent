"""Mapper между domain ConversationMessage и ACP Protocol HistoryMessage.

Единственный путь сериализации истории (write-фаза D2-b, ADR-006). Тотальный и
двунаправленный: SessionMapper делегирует сюда оба направления.

Дуальные слоты wire `HistoryMessage` (`text` vs `content`) — артефакт LLM-транспорта,
не доменная семантика: у всех ролей одно понятие «содержимое» (`MessageContent`).
Выбор слота — политика этого маппера (решение №2, ADR-006), роль-driven и тотальная:
- assistant (без блочного контента) → плоский `text`, `content=null`;
- tool (без блочного контента)      → `content` как строка;
- user / system / любой блочный     → `content` как список блоков.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from codelab.server.domain.conversation import (
    ConversationMessage,
    Image,
    MessageContent,
    Resource,
)
from codelab.server.domain.tool_call import ToolCall
from codelab.server.domain.value_objects import MessageRole
from codelab.server.models import HistoryMessage


class HistoryMapper:
    """Конвертер между domain ConversationMessage и protocol HistoryMessage."""

    @staticmethod
    def to_protocol(domain: ConversationMessage) -> HistoryMessage:
        """Конвертировать domain ConversationMessage в protocol HistoryMessage."""
        role_str = domain.role.value
        content_value, text_value = _content_to_wire(role_str, domain.content)

        # Embedded LLM tool_calls: домен несёт их существующим полем `tool_calls`
        # (id/name/arguments); прочие поля доменного ToolCall в этот слот не эмитятся.
        extra: dict[str, Any] = {}
        if domain.tool_calls:
            extra["tool_calls"] = [
                {"id": tc.id, "name": tc.tool_name, "arguments": tc.arguments}
                for tc in domain.tool_calls
            ]

        return HistoryMessage(
            role=role_str,  # type: ignore[arg-type]
            content=content_value,
            text=text_value,
            timestamp=domain.timestamp.isoformat() if domain.timestamp else None,
            tool_call_id=domain.tool_call_id,
            **extra,
        )

    @staticmethod
    def to_domain(protocol: HistoryMessage | dict[str, Any]) -> ConversationMessage:
        """Конвертировать protocol HistoryMessage (или сырой dict) в domain ConversationMessage."""
        if isinstance(protocol, dict):
            protocol = HistoryMessage.model_validate(protocol)

        role = _parse_role(protocol.role)
        content = _parse_content(protocol.content)

        # Плоский `text`-слот: если структурного содержимого нет — это и есть текст сообщения.
        top_text = getattr(protocol, "text", None)
        if top_text and not (content.text or content.resources or content.images):
            content = MessageContent(text=top_text)

        # null остаётся null: ACP не синтезирует время (см. ConversationMessage.timestamp).
        timestamp = datetime.fromisoformat(protocol.timestamp) if protocol.timestamp else None
        return ConversationMessage(
            role=role,
            content=content,
            timestamp=timestamp,
            tool_calls=_parse_embedded_tool_calls(protocol),
            tool_call_id=protocol.tool_call_id,
        )


def _content_to_wire(role_str: str, content: MessageContent) -> tuple[Any, str | None]:
    """Роль-driven политика слотов (решение №2, ADR-006).

    Возвращает `(content_value, text_value)` для wire `HistoryMessage`.
    """
    has_structured = bool(content.resources or content.images)
    if not has_structured:
        if role_str == MessageRole.ASSISTANT.value:
            return None, content.text
        if role_str == MessageRole.TOOL.value:
            return content.text, None
    # user / system / любое блочное содержимое → список блоков
    return _build_blocks(content), None


def _build_blocks(content: MessageContent) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if content.text:
        blocks.append({"type": "text", "text": content.text})
    for resource in content.resources:
        blocks.append(resource.to_acp())
    for image in content.images:
        blocks.append(image.to_acp())
    return blocks


def _parse_role(role: str) -> MessageRole:
    try:
        return MessageRole(role)
    except ValueError:
        return MessageRole.USER


def _parse_embedded_tool_calls(protocol: HistoryMessage) -> list[ToolCall]:
    """Embedded LLM tool_calls (`[{id,name,arguments}]`) → domain ToolCall."""
    raw = getattr(protocol, "tool_calls", None)
    if not raw:
        return []
    result: list[ToolCall] = []
    for tc in raw:
        if isinstance(tc, dict):
            result.append(
                ToolCall(
                    id=tc.get("id", ""),
                    tool_name=tc.get("name", ""),
                    arguments=tc.get("arguments") or {},
                )
            )
    return result


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
        # Pydantic-коэрция могла превратить блоки в объекты (напр. wire MessageContent).
        block_type = getattr(block, "type", "")
        if block_type == "text" or (block_type == "" and getattr(block, "text", None)):
            text_parts.append(getattr(block, "text", "") or "")

    return MessageContent(text="\n".join(text_parts), resources=resources, images=images)

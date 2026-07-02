"""Domain models для conversation messages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .tool_call import ToolCall
from .value_objects import MessageRole


@dataclass(frozen=True)
class Resource:
    """Domain model для встроенного ресурса."""

    uri: str
    name: str | None = None
    content: str | None = None
    mime_type: str | None = None

    @classmethod
    def from_acp(cls, block: dict[str, Any]) -> Resource:
        resource = block.get("resource", {})
        return cls(
            uri=resource.get("uri", ""),
            name=resource.get("name"),
            content=resource.get("text") or resource.get("content"),
            mime_type=resource.get("mimeType"),
        )

    def to_acp(self) -> dict[str, Any]:
        result: dict[str, Any] = {"type": "resource", "resource": {"uri": self.uri}}
        if self.name is not None:
            result["resource"]["name"] = self.name
        if self.content is not None:
            result["resource"]["text"] = self.content
        if self.mime_type is not None:
            result["resource"]["mimeType"] = self.mime_type
        return result


@dataclass(frozen=True)
class Image:
    """Domain model для изображения."""

    data: str
    mime_type: str = "image/png"

    @classmethod
    def from_acp(cls, block: dict[str, Any]) -> Image:
        # Backward compatibility: поддерживаем старое поле "format"
        mime_type = block.get("mimeType") or block.get("format", "image/png")
        # Нормализация: если указан только формат без типа (например, "png"),
        # преобразуем в полный MIME-тип
        if mime_type and "/" not in mime_type:
            mime_type = f"image/{mime_type}"
        return cls(
            data=block.get("data", ""),
            mime_type=mime_type,
        )

    def to_acp(self) -> dict[str, Any]:
        return {"type": "image", "data": self.data, "mimeType": self.mime_type}


@dataclass(frozen=True)
class MessageContent:
    """Domain model для содержимого сообщения."""

    text: str = ""
    resources: list[Resource] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)


@dataclass(frozen=True)
class ConversationMessage:
    """Domain entity — сообщение в истории.

    НЕ является ACP Protocol Model. Для wire format использовать HistoryMessage.
    Конвертация через HistoryMapper.
    """

    role: MessageRole
    content: MessageContent
    timestamp: datetime = field(default_factory=datetime.now)
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None

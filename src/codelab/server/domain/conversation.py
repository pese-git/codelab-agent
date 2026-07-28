"""Domain models для conversation messages."""

from __future__ import annotations

from collections.abc import Sequence
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

    @classmethod
    def from_acp_blocks(cls, blocks: Sequence[Any]) -> MessageContent:
        """Собрать содержимое из ACP content blocks.

        Единственная реализация разбора блоков: её используют и history-seam
        (`Session.add_user_message`), и `HistoryMapper` при чтении хранилища
        (фаза B ADR-006). Рядом с `Resource.from_acp` / `Image.from_acp`, то есть
        разбор ACP-блоков в домене — уже принятая здесь конвенция.

        Неизвестные типы блоков игнорируются: содержимое сообщения не должно
        падать из-за расширения протокола.
        """
        text_parts: list[str] = []
        resources: list[Resource] = []
        images: list[Image] = []

        for block in blocks:
            if isinstance(block, str):
                text_parts.append(block)
                continue
            if not isinstance(block, dict):
                continue
            match block.get("type", ""):
                case "text":
                    text_parts.append(block.get("text", ""))
                case "resource":
                    resources.append(Resource.from_acp(block))
                case "image":
                    images.append(Image.from_acp(block))

        return cls(text="\n".join(text_parts), resources=resources, images=images)


@dataclass(frozen=True)
class ConversationMessage:
    """Domain entity — сообщение в истории.

    НЕ является ACP Protocol Model. Для wire format использовать HistoryMessage.
    Конвертация через HistoryMapper.
    """

    role: MessageRole
    content: MessageContent
    # ACP не моделирует per-message timestamp; единственное время в протоколе —
    # session-level `updatedAt` (nullable). Поэтому `None` — валидное значение и
    # НЕ синтезируется при пересборке: null должен оставаться null (round-trip).
    timestamp: datetime | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None

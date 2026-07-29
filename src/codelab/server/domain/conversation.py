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
class TextBlock:
    """Domain model для текстового блока."""

    text: str

    @classmethod
    def from_acp(cls, block: dict[str, Any]) -> TextBlock:
        return cls(text=block.get("text", ""))

    def to_acp(self) -> dict[str, Any]:
        return {"type": "text", "text": self.text}


type ContentBlock = TextBlock | Resource | Image


@dataclass(frozen=True)
class MessageContent:
    """Domain model для содержимого сообщения — упорядоченные блоки.

    Порядок блоков — часть содержимого, а не деталь представления: для модели
    `[resource, text]` (файл, затем комментирующая его инструкция) и
    `[text, resource]` — разные сообщения. Поэтому источник истины один —
    `blocks`; `text`/`resources`/`images` остались как проекции для читателей,
    которым нужен только один вид блоков.

    Раньше содержимое хранилось этими тремя полями, и порядок был невосстановим:
    несколько `text`-блоков склеивались в одну строку, а обратная сборка шла
    фиксированно текст → ресурсы → картинки (блокер фазы D, ADR-006).
    """

    blocks: tuple[ContentBlock, ...] = ()

    @classmethod
    def from_text(cls, text: str) -> MessageContent:
        """Содержимое из одной строки (пустая строка — пустое содержимое)."""
        return cls(blocks=(TextBlock(text=text),) if text else ())

    @classmethod
    def from_acp_blocks(cls, blocks: Sequence[Any]) -> MessageContent:
        """Собрать содержимое из ACP content blocks, сохраняя порядок.

        Единственная реализация разбора блоков: её используют и history-seam
        (`Session.add_user_message`), и `HistoryMapper` при чтении хранилища
        (фаза B ADR-006). Рядом с `Resource.from_acp` / `Image.from_acp`, то есть
        разбор ACP-блоков в домене — уже принятая здесь конвенция.

        Неизвестные типы блоков игнорируются: содержимое сообщения не должно
        падать из-за расширения протокола. Пустые `text`-блоки отбрасываются —
        так же, как их отбрасывала прежняя сборка wire-блоков.
        """
        parsed: list[ContentBlock] = []

        for block in blocks:
            if isinstance(block, str):
                if block:
                    parsed.append(TextBlock(text=block))
                continue
            if not isinstance(block, dict):
                continue
            match block.get("type", ""):
                case "text":
                    text_block = TextBlock.from_acp(block)
                    if text_block.text:
                        parsed.append(text_block)
                case "resource":
                    parsed.append(Resource.from_acp(block))
                case "image":
                    parsed.append(Image.from_acp(block))

        return cls(blocks=tuple(parsed))

    def to_acp_blocks(self) -> list[dict[str, Any]]:
        """Содержимое → ACP content blocks в исходном порядке."""
        return [block.to_acp() for block in self.blocks]

    @property
    def text(self) -> str:
        """Текст сообщения: все `text`-блоки через перевод строки."""
        return "\n".join(block.text for block in self.blocks if isinstance(block, TextBlock))

    @property
    def resources(self) -> list[Resource]:
        """Только ресурсы, в исходном порядке."""
        return [block for block in self.blocks if isinstance(block, Resource)]

    @property
    def images(self) -> list[Image]:
        """Только картинки, в исходном порядке."""
        return [block for block in self.blocks if isinstance(block, Image)]


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

"""FakeContentCodec — реализация порта `ContentCodec` для тестов ядра.

Не зависит от ACP: доказывает, что `HistoryBuilder` работает с любым кодеком,
подставленным driving-адаптером. Декодирует минимальный набор блоков
(text/image), достаточный для юнит-тестов истории.
"""

from __future__ import annotations

from typing import Any

from codelab.server.llm.content_parts import ContentPart


class FakeContentCodec:
    """Минимальный `ContentCodec` для тестов (text + image)."""

    def decode(self, blocks: list[dict[str, Any]]) -> list[ContentPart]:
        parts: list[ContentPart] = []
        for block in blocks:
            block_type = block.get("type")
            if block_type == "text":
                parts.append(ContentPart.make_text(block.get("text", "")))
            elif block_type == "image":
                parts.append(
                    ContentPart.make_image(
                        data=block.get("data", ""),
                        mime_type=block.get("mimeType", "application/octet-stream"),
                    )
                )
        return parts

"""ACP-адаптер порта `ContentCodec`: ACP `ContentBlock` → `llm.ContentPart`.

Driving-адаптер ACP (ADR-005, шов №2). Декодирует ACP-форму содержимого (dict-и)
в канонический `ContentPart` для ядра. Ранее жил в ядре как `agent.acp_content_mapper`
(ACP-специфика внутри `agent/`); перенесён в `protocol/` без изменения логики.
"""

from __future__ import annotations

from typing import Any

from codelab.server.llm.content_parts import ContentPart


class ACPContentCodec:
    """Реализация `ContentCodec` для ACP: декодирует ACP `ContentBlock` в `ContentPart`."""

    def decode(self, blocks: list[dict[str, Any]]) -> list[ContentPart]:
        """Декодировать список ACP `ContentBlock` в список `ContentPart`.

        Args:
            blocks: Список ACP content blocks.

        Returns:
            Список ContentPart.
        """
        result: list[ContentPart] = []
        for block in blocks:
            part = self._map_single(block)
            if part is not None:
                result.append(part)
        return result

    def _map_single(self, block: dict[str, Any]) -> ContentPart | None:
        block_type = block.get("type")

        if block_type == "text":
            text = block.get("text", "")
            return ContentPart.make_text(text)

        if block_type == "image":
            data = block.get("data", "")
            mime_type = block.get("mimeType", "application/octet-stream")
            return ContentPart.make_image(data=data, mime_type=mime_type)

        if block_type == "audio":
            data = block.get("data", "")
            mime_type = block.get("mimeType", "audio/wav")
            return ContentPart.make_audio(data=data, mime_type=mime_type)

        if block_type == "resource":
            resource = block.get("resource", {})
            uri = resource.get("uri", "")
            text = resource.get("text", "")
            return ContentPart.make_text(f"[Resource: {uri}]\n{text}")

        if block_type == "resource_link":
            uri = block.get("uri", "")
            name = block.get("name", "")
            return ContentPart.make_text(f"[Resource link: {name} ({uri})]")

        return None

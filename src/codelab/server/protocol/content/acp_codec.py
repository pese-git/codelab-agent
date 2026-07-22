"""ACPContentCodec — ACP-адаптер для порта ContentCodec (ADR-005, Фаза 2).

Реализует ``ContentCodec`` (driven-порт из ``agent/contracts/ports.py``)
для ACP wire-формата. Декодирует список ACP ContentBlock dict в
``llm.ContentPart`` — канон контента ядра.

До Фазы 2 маппер жил в ``agent/acp_content_mapper.py`` (нарушение
шестигранника: ACP-форма контента внутри ядра). Перенесён сюда как
ACP-адаптер. Имя класса сохранено (``ACPContentMapper``) для
обратной совместимости, плюс ``ACPContentCodec`` как новый alias
для прямой реализации ``ContentCodec`` Protocol.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from codelab.server.llm.content_parts import ContentPart


class ACPContentCodec:
    """ACP-реализация ``ContentCodec``: декодирует ACP ContentBlock dict.

    Поддерживаемые типы блоков (ACP 05-Prompt Turn):
    - ``text``: ``{"type": "text", "text": "..."}``
    - ``image``: ``{"type": "image", "data": base64, "mimeType": "..."}``
    - ``audio``: ``{"type": "audio", "data": base64, "mimeType": "..."}``
    - ``resource``: ``{"type": "resource", "resource": {"uri": ..., "text": ...}}``
    - ``resource_link``: ``{"type": "resource_link", "uri": ..., "name": ...}``

    Неизвестные типы блоков пропускаются (return None на одиночном маппинге).
    """

    def decode(
        self,
        blocks: Sequence[Mapping[str, Any]],
    ) -> list[ContentPart]:
        """Декодировать список content-блоков в ``ContentPart``.

        Args:
            blocks: Список ACP content blocks.

        Returns:
            Список ContentPart (только успешно декодированные).
        """
        result: list[ContentPart] = []
        for block in blocks:
            part = self._map_single(dict(block))
            if part is not None:
                result.append(part)
        return result

    # Legacy alias для обратной совместимости с ``HistoryBuilder``.
    def map_blocks(
        self,
        blocks: Sequence[Mapping[str, Any]],
    ) -> list[ContentPart]:
        """Синоним ``decode()`` — сохранён для ACP-сценариев, вызывающих
        ``ACPContentMapper().map_blocks(...)`` напрямую (например,
        ``prompt_orchestrator``).
        """
        return self.decode(blocks)

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


# Legacy alias — некоторые места (prompt_orchestrator, тесты) импортируют
# ``ACPContentMapper`` по старому имени. Сохранено для обратной совместимости
# в Фазе 2; будет удалено в Фазе 4 при стабилизации импорта.
ACPContentMapper = ACPContentCodec


__all__ = ["ACPContentCodec", "ACPContentMapper"]

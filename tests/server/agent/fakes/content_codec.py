"""FakeContentCodec — тестовая реализация ContentCodec (ADR-005, Фаза 2).

Используется в unit-тестах, где нужно изолировать HistoryBuilder от ACP
формата и проверить, что HistoryBuilder корректно использует инжектированный
codec через DI (не создаёт ACPContentMapper внутри).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from codelab.server.llm.content_parts import ContentPart


class FakeContentCodec:
    """Предсказуемая реализация ``ContentCodec`` для тестов.

    Поведение:
    - Каждый dict-блок конвертируется в ``ContentPart.make_text(json.dumps(block))``
      (стабильный, детерминированный, видимый в ассертах).
    - Список blocks-аргументов сохраняется в ``self.calls`` для проверки.

    Если вход ``None`` или пустой — возвращает ``[]`` (без вызовов).
    """

    def __init__(self) -> None:
        self.calls: list[Sequence[Mapping[str, Any]]] = []

    def decode(
        self,
        blocks: Sequence[Mapping[str, Any]],
    ) -> list[ContentPart]:
        self.calls.append(blocks)
        if not blocks:
            return []
        return [
            ContentPart.make_text(_stable_repr(block))
            for block in blocks
        ]


def _stable_repr(block: Mapping[str, Any]) -> str:
    """Стабильное текстовое представление блока для тестов."""
    import json

    return json.dumps(dict(block), sort_keys=True, ensure_ascii=False)


__all__ = ["FakeContentCodec"]

"""Описание ACP content-блоков текстом.

Дом выбран по слоям, а не по удобству. Рендер нужен двум сторонам: turn-пути
(`protocol/handlers/.../tool_processor.py`) и MCP-адаптеру (`mcp/tool_adapter.py`). Пока он жил в
`protocol/content/`, MCP-адаптер тянул `protocol` — а `mcp` лежит ниже `agent` по контракту
`Server layers`, поэтому это инверсия слоёв, и `import-linter` её ловит. Список исключений контракта
пуст намеренно («протечку чинить, обходные абстракции не вводить»), так что правильный ответ —
перенести рендер туда, откуда его вправе звать оба.

`shared/content/` — этот дом: пакет уже владеет словарём ACP-контента (`TextContent`,
`ImageContent`, `AudioContent`, `EmbeddedResourceContent`, `ResourceLinkContent`) и является листом,
то есть доступен любому слою. Новая абстракция не вводится — расширяется существующий пакет.

**Зачем рендер существует.** Результат инструмента доходит до модели строкой, поэтому нетекстовый
блок иначе исчезает бесследно: MCP-инструмент, вернувший только изображение, давал модели
`"Success"`. Описание не заменяет данные — доставка самих данных идёт отдельным тактом, за шагом C
расщепления документа сессии (ADR-007), иначе один скриншот стоит сотни МБ записи.
"""

from __future__ import annotations

from typing import Any


def describe_acp_content(content_items: list[dict[str, Any]]) -> str:
    """Описать ACP-блоки текстом, сохраняя их порядок.

    Порядок — часть содержимого, а не деталь представления, поэтому блоки не переупорядочиваются
    и не группируются по типу.

    Неизвестные типы блоков пропускаются: расширение протокола не должно ронять путь результата
    инструмента. `text` отдаётся как есть — для него описание и есть само содержимое.
    """
    parts: list[str] = []

    for item in content_items:
        rendered = _describe_item(item)
        if rendered:
            parts.append(rendered)

    return "\n\n".join(parts)


def _describe_item(item: dict[str, Any]) -> str | None:
    """Описание одного блока (`None` — описывать нечего)."""
    content_type = item.get("type")

    if content_type == "text":
        return item.get("text") or None

    if content_type == "content":
        # ACP-конверт `ToolCallContent`: разворачиваем и описываем вложенный блок. Без этого
        # конверт пропускался целиком, и терминальный результат описывался пустой строкой.
        inner = item.get("content")
        return _describe_item(inner) if isinstance(inner, dict) else None

    if content_type == "diff":
        path = item.get("path", "")
        old_text = item.get("oldText", "") or ""
        new_text = item.get("newText", "") or ""
        return f"File: {path}\n\nOld:\n```\n{old_text}\n```\n\nNew:\n```\n{new_text}\n```"

    if content_type == "image":
        return _describe_media(item, kind="Image")

    if content_type == "audio":
        return _describe_media(item, kind="Audio")

    if content_type == "embedded":
        embedded = item.get("content", [])
        if isinstance(embedded, list):
            return f"[Embedded content]\n{describe_acp_content(embedded)}"
        return None

    if content_type == "resource_link":
        return f"[Resource: {item.get('uri', '')}]"

    return None


def _describe_media(item: dict[str, Any], *, kind: str) -> str:
    """Описание медиа-блока по **настоящим** полям ACP.

    ACP `ImageContent`/`AudioContent` несут `mimeType`, `data` и необязательный `uri`. Прежняя
    реализация читала `alt_text` и `format`, которых в этих блоках нет вовсе, поэтому на любом
    реальном блоке давала бесполезное `[Image: Image (unknown)]`. Старые ключи приняты как
    запасные: их могут прислать внутренние производители, и терять подпись из-за смены имени поля
    не стоит.

    `data` в описание не попадает намеренно: это base64, и его место — не в тексте для модели.
    """
    mime_type = item.get("mimeType") or item.get("format") or "unknown"
    label = item.get("alt_text")
    uri = item.get("uri")

    parts = [f"{kind}: {mime_type}"]
    if label:
        parts.append(str(label))
    if uri:
        parts.append(str(uri))
    return f"[{', '.join(parts)}]"

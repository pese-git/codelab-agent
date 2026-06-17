"""Маппер MCP content → ACP content.

Конвертирует контент из формата MCP tool results в формат ACP ContentBlock.
ACP и MCP используют совместимую структуру ContentBlock, что позволяет
передавать контент от MCP инструментов без трансформации.

Поддерживаемые типы:
- text → TextContent
- image → ImageContent
- resource → EmbeddedResourceContent (TextResource или BlobResource)

Reference:
- ACP 06-Content.md: "The Agent Client Protocol uses the same ContentBlock
  structure as the Model Context Protocol (MCP)."
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ContentMapperError(Exception):
    """Ошибка при маппинге MCP content в ACP content."""

    pass


def mcp_text_to_acp(item: dict[str, Any]) -> dict[str, Any]:
    """Конвертировать MCP text content в ACP TextContent.

    Args:
        item: MCP text content dict с полями {type: "text", text: str}.

    Returns:
        ACP TextContent dict.

    Raises:
        ContentMapperError: Если отсутствует обязательное поле text.
    """
    text = item.get("text")
    if text is None:
        raise ContentMapperError("MCP text content missing 'text' field")

    result: dict[str, Any] = {"type": "text", "text": str(text)}

    annotations = item.get("annotations")
    if annotations is not None:
        result["annotations"] = annotations

    return result


def mcp_image_to_acp(item: dict[str, Any]) -> dict[str, Any]:
    """Конвертировать MCP image content в ACP ImageContent.

    MCP и ACP используют одинаковый формат для изображений:
    {type: "image", data: base64, mimeType: str}.

    Args:
        item: MCP image content dict с полями
              {type: "image", data: str, mimeType: str}.

    Returns:
        ACP ImageContent dict.

    Raises:
        ContentMapperError: Если отсутствуют обязательные поля.
    """
    data = item.get("data")
    mime_type = item.get("mimeType") or item.get("mime_type")

    if data is None:
        raise ContentMapperError("MCP image content missing 'data' field")
    if mime_type is None:
        raise ContentMapperError("MCP image content missing 'mimeType' field")

    result: dict[str, Any] = {
        "type": "image",
        "data": str(data),
        "mimeType": str(mime_type),
    }

    uri = item.get("uri")
    if uri is not None:
        result["uri"] = str(uri)

    annotations = item.get("annotations")
    if annotations is not None:
        result["annotations"] = annotations

    return result


def mcp_embedded_to_acp(item: dict[str, Any]) -> dict[str, Any]:
    """Конвертировать MCP embedded resource в ACP EmbeddedResourceContent.

    MCP embedded resource содержит поле resource с данными.
    Если resource содержит 'text' — это TextResource.
    Если resource содержит 'blob' — это BlobResource.

    Args:
        item: MCP embedded resource dict с полями
              {type: "resource", resource: {uri, text|blob, mimeType?}}.

    Returns:
        ACP EmbeddedResourceContent dict.

    Raises:
        ContentMapperError: Если отсутствует resource или обязательные поля.
    """
    resource = item.get("resource")
    if resource is None:
        raise ContentMapperError(
            "MCP embedded resource content missing 'resource' field"
        )

    if not isinstance(resource, dict):
        raise ContentMapperError(
            f"MCP embedded resource must be a dict, got {type(resource).__name__}"
        )

    uri = resource.get("uri")
    if uri is None:
        raise ContentMapperError("MCP embedded resource missing 'uri' field")

    acp_resource: dict[str, Any] = {"uri": str(uri)}

    mime_type = resource.get("mimeType") or resource.get("mime_type")
    if mime_type is not None:
        acp_resource["mimeType"] = str(mime_type)

    if "text" in resource:
        acp_resource["text"] = str(resource["text"])
    elif "blob" in resource:
        acp_resource["blob"] = str(resource["blob"])
    else:
        raise ContentMapperError(
            "MCP embedded resource must contain either 'text' or 'blob' field"
        )

    result: dict[str, Any] = {"type": "resource", "resource": acp_resource}

    annotations = item.get("annotations")
    if annotations is not None:
        result["annotations"] = annotations

    return result


def mcp_content_item_to_acp(item: dict[str, Any]) -> dict[str, Any] | None:
    """Конвертировать один элемент MCP content в ACP ContentBlock.

    Определяет тип контента по полю 'type' и делегирует
    соответствующей функции конвертации.

    Args:
        item: Элемент MCP content dict.

    Returns:
        ACP ContentBlock dict или None если тип не поддерживается.
    """
    content_type = item.get("type")

    if content_type == "text":
        return mcp_text_to_acp(item)
    elif content_type == "image":
        return mcp_image_to_acp(item)
    elif content_type == "resource":
        return mcp_embedded_to_acp(item)
    else:
        logger.warning("Unsupported MCP content type: %s, skipping", content_type)
        return None


def mcp_content_to_acp_list(
    content: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Конвертировать список MCP content в список ACP ContentBlock.

    Основная функция маппинга — обрабатывает все элементы контента
    и возвращает список ACP-совместимых блоков. Неподдерживаемые
    типы пропускаются с warning в лог.

    Args:
        content: Список элементов MCP content из MCPCallToolResult.

    Returns:
        Список ACP ContentBlock dicts.
    """
    result: list[dict[str, Any]] = []

    for item in content:
        if not isinstance(item, dict):
            logger.warning(
                "Skipping non-dict MCP content item: %s", type(item).__name__
            )
            continue

        try:
            acp_item = mcp_content_item_to_acp(item)
            if acp_item is not None:
                result.append(acp_item)
        except ContentMapperError as e:
            logger.warning("Failed to convert MCP content item: %s", e)
            continue

    return result


def extract_text_from_acp_content(
    content: list[dict[str, Any]],
) -> str:
    """Извлечь текстовый контент из списка ACP ContentBlock.

    Объединяет текст из всех TextContent блоков.
    Используется для обратной совместимости — получения
    текстового вывода из мультимодального контента.

    Args:
        content: Список ACP ContentBlock dicts.

    Returns:
        Объединённый текст из всех текстовых блоков.
    """
    texts: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            text = item.get("text", "")
            if text:
                texts.append(str(text))
    return "\n".join(texts)

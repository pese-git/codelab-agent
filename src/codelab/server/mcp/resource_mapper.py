"""Маппинг MCP Resource моделей в ACP Content типы.

Обеспечивает конвертацию MCP ресурсных моделей в ACP ContentBlock типы
для интеграции MCP ресурсов с ACP протоколом.

Согласовано с:
- MCP spec: https://modelcontextprotocol.io/specification/
- ACP spec: ContentBlock::resource_link
"""

from ...shared.content.resource_link import ResourceLinkContent
from .models import MCPResource


def mcp_resource_to_resource_link(resource: MCPResource) -> ResourceLinkContent:
    """Конвертировать MCPResource в ACP ResourceLinkContent.

    Маппинг полей:
    - uri → uri (обязательное)
    - name → name (обязательное)
    - mime_type → mimeType
    - title → title
    - description → description
    - size → size
    - annotations → annotations (как dict)

    Args:
        resource: MCP ресурс для конвертации.

    Returns:
        ResourceLinkContent для ACP протокола.
    """
    annotations_dict = None
    if resource.annotations is not None:
        annotations_dict = resource.annotations.model_dump(
            by_alias=True, exclude_none=True
        )

    return ResourceLinkContent(
        uri=resource.uri,
        name=resource.name,
        mimeType=resource.mime_type,
        title=resource.title,
        description=resource.description,
        size=resource.size,
        annotations=annotations_dict,
    )


def mcp_resources_to_resource_links(
    resources: list[MCPResource],
) -> list[ResourceLinkContent]:
    """Конвертировать список MCP ресурсов в список ACP ResourceLinkContent.

    Args:
        resources: Список MCP ресурсов.

    Returns:
        Список ResourceLinkContent для ACP протокола.
    """
    return [mcp_resource_to_resource_link(r) for r in resources]

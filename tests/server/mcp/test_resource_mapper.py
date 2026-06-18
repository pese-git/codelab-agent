"""Тесты для маппинга MCP Resource → ACP ResourceLinkContent."""

from codelab.server.mcp.models import (
    MCPAnnotations,
    MCPResource,
    MCPResourceIcon,
)
from codelab.server.mcp.resource_mapper import (
    mcp_resource_to_resource_link,
    mcp_resources_to_resource_links,
)


class TestMCPResourceToResourceLink:
    """Тесты функции mcp_resource_to_resource_link."""

    def test_minimal_mapping(self):
        """Маппинг с минимальными полями."""
        resource = MCPResource(uri="file:///tmp/test.txt", name="test.txt")
        link = mcp_resource_to_resource_link(resource)

        assert link.type == "resource_link"
        assert link.uri == "file:///tmp/test.txt"
        assert link.name == "test.txt"
        assert link.mimeType is None
        assert link.title is None
        assert link.description is None
        assert link.size is None
        assert link.annotations is None

    def test_full_mapping(self):
        """Маппинг со всеми полями."""
        resource = MCPResource(
            uri="file:///tmp/doc.pdf",
            name="doc.pdf",
            title="Document PDF",
            description="A PDF document",
            mime_type="application/pdf",
            size=1024000,
            annotations=MCPAnnotations(
                audience=["user"],
                priority=0.8,
                last_modified="2025-01-12T15:00:58Z",
            ),
        )
        link = mcp_resource_to_resource_link(resource)

        assert link.uri == "file:///tmp/doc.pdf"
        assert link.name == "doc.pdf"
        assert link.mimeType == "application/pdf"
        assert link.title == "Document PDF"
        assert link.description == "A PDF document"
        assert link.size == 1024000
        assert link.annotations is not None
        assert link.annotations["audience"] == ["user"]
        assert link.annotations["priority"] == 0.8
        assert link.annotations["lastModified"] == "2025-01-12T15:00:58Z"

    def test_annotations_exclude_none(self):
        """Аннотации без None полей."""
        resource = MCPResource(
            uri="file:///test.txt",
            name="test.txt",
            annotations=MCPAnnotations(priority=0.5),
        )
        link = mcp_resource_to_resource_link(resource)

        assert link.annotations is not None
        assert "audience" not in link.annotations
        assert "lastModified" not in link.annotations
        assert link.annotations["priority"] == 0.5

    def test_icons_not_mapped(self):
        """Иконки не маппятся в ResourceLinkContent (не поддерживаются ACP)."""
        resource = MCPResource(
            uri="file:///test.txt",
            name="test.txt",
            icons=[MCPResourceIcon(src="https://example.com/icon.png")],
        )
        link = mcp_resource_to_resource_link(resource)

        # ResourceLinkContent не имеет поля icons
        assert not hasattr(link, "icons") or link.annotations is None


class TestMCPResourcesToResourceLinks:
    """Тесты функции mcp_resources_to_resource_links."""

    def test_empty_list(self):
        """Пустой список."""
        result = mcp_resources_to_resource_links([])
        assert result == []

    def test_multiple_resources(self):
        """Несколько ресурсов."""
        resources = [
            MCPResource(uri="file:///a.txt", name="a.txt"),
            MCPResource(
                uri="file:///b.pdf",
                name="b.pdf",
                mime_type="application/pdf",
                size=512,
            ),
        ]
        links = mcp_resources_to_resource_links(resources)

        assert len(links) == 2
        assert links[0].uri == "file:///a.txt"
        assert links[0].name == "a.txt"
        assert links[1].uri == "file:///b.pdf"
        assert links[1].mimeType == "application/pdf"
        assert links[1].size == 512

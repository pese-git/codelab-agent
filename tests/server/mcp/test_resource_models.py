"""Тесты для MCP Resource моделей."""

import pytest
from pydantic import ValidationError

from codelab.server.mcp.models import (
    MCPAnnotations,
    MCPListResourcesParams,
    MCPListResourcesResult,
    MCPListResourceTemplatesParams,
    MCPListResourceTemplatesResult,
    MCPReadResourceParams,
    MCPReadResourceResult,
    MCPResource,
    MCPResourceContent,
    MCPResourceIcon,
    MCPResourceTemplate,
)


class TestMCPAnnotations:
    """Тесты модели MCPAnnotations."""

    def test_create_empty(self):
        """Создание без полей."""
        ann = MCPAnnotations()
        assert ann.audience is None
        assert ann.priority is None
        assert ann.last_modified is None

    def test_create_full(self):
        """Создание со всеми полями."""
        ann = MCPAnnotations(
            audience=["user", "assistant"],
            priority=0.8,
            last_modified="2025-01-12T15:00:58Z",
        )
        assert ann.audience == ["user", "assistant"]
        assert ann.priority == 0.8
        assert ann.last_modified == "2025-01-12T15:00:58Z"

    def test_deserialization_camel_case(self):
        """Десериализация из camelCase."""
        data = {
            "audience": ["user"],
            "priority": 0.5,
            "lastModified": "2025-06-01T10:00:00Z",
        }
        ann = MCPAnnotations.model_validate(data)
        assert ann.last_modified == "2025-06-01T10:00:00Z"

    def test_serialization_alias(self):
        """Сериализация с alias."""
        ann = MCPAnnotations(last_modified="2025-01-01T00:00:00Z")
        data = ann.model_dump(by_alias=True)
        assert "lastModified" in data
        assert "last_modified" not in data


class TestMCPResourceIcon:
    """Тесты модели MCPResourceIcon."""

    def test_create_minimal(self):
        """Создание с минимальными полями."""
        icon = MCPResourceIcon(src="https://example.com/icon.png")
        assert icon.src == "https://example.com/icon.png"
        assert icon.mime_type is None
        assert icon.sizes is None

    def test_create_full(self):
        """Создание со всеми полями."""
        icon = MCPResourceIcon(
            src="https://example.com/icon.png",
            mime_type="image/png",
            sizes=["48x48", "96x96"],
        )
        assert icon.mime_type == "image/png"
        assert icon.sizes == ["48x48", "96x96"]

    def test_deserialization_camel_case(self):
        """Десериализация из camelCase."""
        data = {
            "src": "https://example.com/icon.png",
            "mimeType": "image/png",
            "sizes": ["48x48"],
        }
        icon = MCPResourceIcon.model_validate(data)
        assert icon.mime_type == "image/png"

    def test_serialization_alias(self):
        """Сериализация с alias."""
        icon = MCPResourceIcon(
            src="https://example.com/icon.png",
            mime_type="image/png",
        )
        data = icon.model_dump(by_alias=True)
        assert "mimeType" in data
        assert "mime_type" not in data


class TestMCPResource:
    """Тесты модели MCPResource."""

    def test_create_minimal(self):
        """Создание с минимальными полями."""
        resource = MCPResource(uri="file:///tmp/test.txt", name="test.txt")
        assert resource.uri == "file:///tmp/test.txt"
        assert resource.name == "test.txt"
        assert resource.title is None
        assert resource.description is None
        assert resource.mime_type is None
        assert resource.size is None
        assert resource.icons is None
        assert resource.annotations is None

    def test_create_full(self):
        """Создание со всеми полями."""
        resource = MCPResource(
            uri="file:///tmp/test.txt",
            name="test.txt",
            title="Test File",
            description="A test file",
            mime_type="text/plain",
            size=1024,
            icons=[MCPResourceIcon(src="https://example.com/icon.png")],
            annotations=MCPAnnotations(priority=0.8),
        )
        assert resource.title == "Test File"
        assert resource.description == "A test file"
        assert resource.mime_type == "text/plain"
        assert resource.size == 1024
        assert len(resource.icons) == 1
        assert resource.annotations.priority == 0.8

    def test_serialization_with_alias(self):
        """Сериализация с alias для mimeType."""
        resource = MCPResource(
            uri="file:///tmp/test.txt",
            name="test.txt",
            mime_type="text/plain",
        )
        data = resource.model_dump(by_alias=True)
        assert data["mimeType"] == "text/plain"
        assert "mime_type" not in data

    def test_deserialization_from_camel_case(self):
        """Десериализация из camelCase формата."""
        data = {
            "uri": "file:///tmp/test.txt",
            "name": "test.txt",
            "title": "Test",
            "description": "A test file",
            "mimeType": "text/plain",
            "size": 512,
            "annotations": {"priority": 0.5, "lastModified": "2025-01-01T00:00:00Z"},
        }
        resource = MCPResource.model_validate(data)
        assert resource.title == "Test"
        assert resource.mime_type == "text/plain"
        assert resource.size == 512
        assert resource.annotations.priority == 0.5
        assert resource.annotations.last_modified == "2025-01-01T00:00:00Z"

    def test_deserialization_from_snake_case(self):
        """Десериализация из snake_case формата (populate_by_name)."""
        data = {
            "uri": "file:///tmp/test.txt",
            "name": "test.txt",
            "mime_type": "text/plain",
        }
        resource = MCPResource.model_validate(data)
        assert resource.mime_type == "text/plain"


class TestMCPResourceTemplate:
    """Тесты модели MCPResourceTemplate."""

    def test_create_minimal(self):
        """Создание с минимальными полями."""
        template = MCPResourceTemplate(
            uri_template="file:///{path}",
            name="File template",
        )
        assert template.uri_template == "file:///{path}"
        assert template.name == "File template"
        assert template.title is None
        assert template.description is None
        assert template.mime_type is None
        assert template.icons is None
        assert template.annotations is None

    def test_create_full(self):
        """Создание со всеми полями."""
        template = MCPResourceTemplate(
            uri_template="file:///{path}",
            name="File template",
            title="Files",
            description="Template for files",
            mime_type="application/octet-stream",
            icons=[MCPResourceIcon(src="https://example.com/folder.png")],
            annotations=MCPAnnotations(audience=["user"]),
        )
        assert template.title == "Files"
        assert template.description == "Template for files"
        assert template.mime_type == "application/octet-stream"
        assert len(template.icons) == 1
        assert template.annotations.audience == ["user"]

    def test_serialization_with_alias(self):
        """Сериализация с alias для uriTemplate и mimeType."""
        template = MCPResourceTemplate(
            uri_template="file:///{path}",
            name="File template",
            mime_type="text/plain",
        )
        data = template.model_dump(by_alias=True)
        assert data["uriTemplate"] == "file:///{path}"
        assert data["mimeType"] == "text/plain"
        assert "uri_template" not in data
        assert "mime_type" not in data

    def test_deserialization_from_camel_case(self):
        """Десериализация из camelCase формата."""
        data = {
            "uriTemplate": "file:///{path}",
            "name": "File template",
            "title": "Files",
            "mimeType": "text/plain",
            "annotations": {"priority": 0.9},
        }
        template = MCPResourceTemplate.model_validate(data)
        assert template.uri_template == "file:///{path}"
        assert template.title == "Files"
        assert template.mime_type == "text/plain"
        assert template.annotations.priority == 0.9


class TestMCPListResourcesParams:
    """Тесты модели MCPListResourcesParams."""

    def test_create_empty(self):
        """Создание без cursor."""
        params = MCPListResourcesParams()
        assert params.cursor is None

    def test_create_with_cursor(self):
        """Создание с cursor."""
        params = MCPListResourcesParams(cursor="abc123")
        assert params.cursor == "abc123"

    def test_serialization_exclude_none(self):
        """Сериализация exclude_none убирает cursor."""
        params = MCPListResourcesParams()
        data = params.model_dump(exclude_none=True)
        assert data == {}

    def test_serialization_with_cursor(self):
        """Сериализация с cursor."""
        params = MCPListResourcesParams(cursor="page2")
        data = params.model_dump(exclude_none=True)
        assert data == {"cursor": "page2"}


class TestMCPListResourcesResult:
    """Тесты модели MCPListResourcesResult."""

    def test_empty_list(self):
        """Пустой список ресурсов."""
        result = MCPListResourcesResult(resources=[])
        assert result.resources == []
        assert result.next_cursor is None

    def test_with_resources(self):
        """Список с ресурсами."""
        result = MCPListResourcesResult(
            resources=[
                MCPResource(uri="file:///a.txt", name="a.txt"),
                MCPResource(uri="file:///b.txt", name="b.txt"),
            ]
        )
        assert len(result.resources) == 2
        assert result.resources[0].uri == "file:///a.txt"

    def test_with_next_cursor(self):
        """Результат с nextCursor для пагинации."""
        result = MCPListResourcesResult(
            resources=[MCPResource(uri="file:///a.txt", name="a.txt")],
            next_cursor="page2cursor",
        )
        assert result.next_cursor == "page2cursor"

    def test_deserialization(self):
        """Десериализация из dict."""
        data = {
            "resources": [
                {"uri": "file:///a.txt", "name": "a.txt", "mimeType": "text/plain"},
            ],
            "nextCursor": "next123",
        }
        result = MCPListResourcesResult.model_validate(data)
        assert len(result.resources) == 1
        assert result.resources[0].mime_type == "text/plain"
        assert result.next_cursor == "next123"

    def test_deserialization_no_cursor(self):
        """Десериализация без nextCursor (конец результатов)."""
        data = {
            "resources": [{"uri": "file:///a.txt", "name": "a.txt"}],
        }
        result = MCPListResourcesResult.model_validate(data)
        assert result.next_cursor is None


class TestMCPListResourceTemplatesParams:
    """Тесты модели MCPListResourceTemplatesParams."""

    def test_create_empty(self):
        """Создание без cursor."""
        params = MCPListResourceTemplatesParams()
        assert params.cursor is None

    def test_create_with_cursor(self):
        """Создание с cursor."""
        params = MCPListResourceTemplatesParams(cursor="tpl_cursor_1")
        assert params.cursor == "tpl_cursor_1"

    def test_serialization_exclude_none(self):
        """Сериализация exclude_none убирает cursor."""
        params = MCPListResourceTemplatesParams()
        data = params.model_dump(exclude_none=True)
        assert data == {}


class TestMCPListResourceTemplatesResult:
    """Тесты модели MCPListResourceTemplatesResult."""

    def test_empty_list(self):
        """Пустой список шаблонов."""
        result = MCPListResourceTemplatesResult()
        assert result.resource_templates == []
        assert result.next_cursor is None

    def test_with_templates(self):
        """Список с шаблонами."""
        result = MCPListResourceTemplatesResult(
            resourceTemplates=[
                MCPResourceTemplate(uri_template="file:///{path}", name="File"),
            ]
        )
        assert len(result.resource_templates) == 1

    def test_with_next_cursor(self):
        """Результат с nextCursor для пагинации."""
        result = MCPListResourceTemplatesResult(
            resourceTemplates=[
                MCPResourceTemplate(uri_template="file:///{path}", name="File"),
            ],
            next_cursor="tpl_next_cursor",
        )
        assert result.next_cursor == "tpl_next_cursor"

    def test_deserialization_from_camel_case(self):
        """Десериализация из camelCase формата."""
        data = {
            "resourceTemplates": [
                {"uriTemplate": "file:///{path}", "name": "File"},
            ],
            "nextCursor": "cursor_abc",
        }
        result = MCPListResourceTemplatesResult.model_validate(data)
        assert len(result.resource_templates) == 1
        assert result.resource_templates[0].uri_template == "file:///{path}"
        assert result.next_cursor == "cursor_abc"


class TestMCPReadResourceParams:
    """Тесты модели MCPReadResourceParams."""

    def test_create(self):
        """Создание параметров."""
        params = MCPReadResourceParams(uri="file:///tmp/test.txt")
        assert params.uri == "file:///tmp/test.txt"

    def test_serialization(self):
        """Сериализация в dict."""
        params = MCPReadResourceParams(uri="file:///tmp/test.txt")
        data = params.model_dump()
        assert data == {"uri": "file:///tmp/test.txt"}

    def test_deserialization(self):
        """Десериализация из dict."""
        params = MCPReadResourceParams.model_validate({"uri": "file:///tmp/test.txt"})
        assert params.uri == "file:///tmp/test.txt"

    def test_requires_uri(self):
        """URI обязателен."""
        with pytest.raises(ValidationError):
            MCPReadResourceParams()


class TestMCPResourceContent:
    """Тесты модели MCPResourceContent."""

    def test_text_content(self):
        """Текстовый контент."""
        content = MCPResourceContent(
            uri="file:///tmp/test.txt",
            mime_type="text/plain",
            text="Hello, world!",
        )
        assert content.get_text_content() == "Hello, world!"

    def test_blob_content(self):
        """Бинарный контент (base64)."""
        content = MCPResourceContent(
            uri="file:///tmp/image.png",
            mime_type="image/png",
            blob="iVBORw0KGgo=",
        )
        assert content.get_text_content() == "iVBORw0KGgo="

    def test_text_priority_over_blob(self):
        """Текст имеет приоритет над blob."""
        content = MCPResourceContent(
            uri="file:///tmp/test.txt",
            text="text content",
            blob="blob content",
        )
        assert content.get_text_content() == "text content"

    def test_empty_content(self):
        """Пустой контент."""
        content = MCPResourceContent(uri="file:///tmp/empty.txt")
        assert content.get_text_content() == ""

    def test_deserialization_with_alias(self):
        """Десериализация с mimeType alias."""
        data = {
            "uri": "file:///tmp/test.txt",
            "mimeType": "text/plain",
            "text": "content",
        }
        content = MCPResourceContent.model_validate(data)
        assert content.mime_type == "text/plain"


class TestMCPReadResourceResult:
    """Тесты модели MCPReadResourceResult."""

    def test_empty_contents(self):
        """Пустой результат."""
        result = MCPReadResourceResult()
        assert result.contents == []
        assert result.get_text_content() == ""

    def test_with_dict_contents(self):
        """Результат с dict contents."""
        result = MCPReadResourceResult(
            contents=[
                {"type": "text", "text": "Hello"},
                {"type": "text", "text": "World"},
            ]
        )
        assert result.get_text_content() == "Hello\nWorld"

    def test_with_typed_contents(self):
        """Результат с типизированными contents."""
        result = MCPReadResourceResult(
            contents=[
                MCPResourceContent(uri="file:///a.txt", text="Part A"),
                MCPResourceContent(uri="file:///b.txt", text="Part B"),
            ]
        )
        assert result.get_text_content() == "Part A\nPart B"

    def test_resource_type_content(self):
        """Контент типа resource."""
        result = MCPReadResourceResult(
            contents=[
                {
                    "type": "resource",
                    "resource": {"text": "Resource text"},
                }
            ]
        )
        assert result.get_text_content() == "Resource text"

    def test_resource_type_with_blob(self):
        """Контент типа resource с blob."""
        result = MCPReadResourceResult(
            contents=[
                {
                    "type": "resource",
                    "resource": {"blob": "base64data"},
                }
            ]
        )
        assert result.get_text_content() == "base64data"

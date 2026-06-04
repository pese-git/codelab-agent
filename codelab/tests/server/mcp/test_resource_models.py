"""Тесты для MCP Resource моделей."""

import pytest
from pydantic import ValidationError

from codelab.server.mcp.models import (
    MCPListResourcesResult,
    MCPListResourceTemplatesResult,
    MCPReadResourceParams,
    MCPReadResourceResult,
    MCPResource,
    MCPResourceContent,
    MCPResourceTemplate,
)


class TestMCPResource:
    """Тесты модели MCPResource."""

    def test_create_minimal(self):
        """Создание с минимальными полями."""
        resource = MCPResource(uri="file:///tmp/test.txt", name="test.txt")
        assert resource.uri == "file:///tmp/test.txt"
        assert resource.name == "test.txt"
        assert resource.description is None
        assert resource.mime_type is None

    def test_create_full(self):
        """Создание со всеми полями."""
        resource = MCPResource(
            uri="file:///tmp/test.txt",
            name="test.txt",
            description="A test file",
            mime_type="text/plain",
        )
        assert resource.description == "A test file"
        assert resource.mime_type == "text/plain"

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
            "description": "A test file",
            "mimeType": "text/plain",
        }
        resource = MCPResource.model_validate(data)
        assert resource.mime_type == "text/plain"

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
        assert template.description is None
        assert template.mime_type is None

    def test_create_full(self):
        """Создание со всеми полями."""
        template = MCPResourceTemplate(
            uri_template="file:///{path}",
            name="File template",
            description="Template for files",
            mime_type="application/octet-stream",
        )
        assert template.description == "Template for files"
        assert template.mime_type == "application/octet-stream"

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
            "mimeType": "text/plain",
        }
        template = MCPResourceTemplate.model_validate(data)
        assert template.uri_template == "file:///{path}"
        assert template.mime_type == "text/plain"


class TestMCPListResourcesResult:
    """Тесты модели MCPListResourcesResult."""

    def test_empty_list(self):
        """Пустой список ресурсов."""
        result = MCPListResourcesResult(resources=[])
        assert result.resources == []

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

    def test_deserialization(self):
        """Десериализация из dict."""
        data = {
            "resources": [
                {"uri": "file:///a.txt", "name": "a.txt", "mimeType": "text/plain"},
            ]
        }
        result = MCPListResourcesResult.model_validate(data)
        assert len(result.resources) == 1
        assert result.resources[0].mime_type == "text/plain"


class TestMCPListResourceTemplatesResult:
    """Тесты модели MCPListResourceTemplatesResult."""

    def test_empty_list(self):
        """Пустой список шаблонов."""
        result = MCPListResourceTemplatesResult()
        assert result.resource_templates == []

    def test_with_templates(self):
        """Список с шаблонами."""
        result = MCPListResourceTemplatesResult(
            resourceTemplates=[
                MCPResourceTemplate(uri_template="file:///{path}", name="File"),
            ]
        )
        assert len(result.resource_templates) == 1

    def test_deserialization_from_camel_case(self):
        """Десериализация из camelCase формата."""
        data = {
            "resourceTemplates": [
                {"uriTemplate": "file:///{path}", "name": "File"},
            ]
        }
        result = MCPListResourceTemplatesResult.model_validate(data)
        assert len(result.resource_templates) == 1
        assert result.resource_templates[0].uri_template == "file:///{path}"


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

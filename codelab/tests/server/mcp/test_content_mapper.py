"""Тесты для mcp/content_mapper.py.

Покрывают конвертацию MCP content в ACP content:
- Text content
- Image content
- Embedded resource (TextResource и BlobResource)
- Mixed content
- Error handling
"""

from __future__ import annotations

import pytest

from codelab.server.mcp.content_mapper import (
    ContentMapperError,
    extract_text_from_acp_content,
    mcp_content_item_to_acp,
    mcp_content_to_acp_list,
    mcp_embedded_to_acp,
    mcp_image_to_acp,
    mcp_text_to_acp,
)


class TestMcpTextToAcp:
    """Тесты конвертации MCP text content → ACP TextContent."""

    def test_basic_text_conversion(self) -> None:
        """Базовая конвертация text content."""
        mcp_item = {"type": "text", "text": "Hello, world!"}

        result = mcp_text_to_acp(mcp_item)

        assert result == {"type": "text", "text": "Hello, world!"}

    def test_text_with_annotations(self) -> None:
        """Text content с annotations."""
        mcp_item = {
            "type": "text",
            "text": "Content",
            "annotations": {"audience": ["user"]},
        }

        result = mcp_text_to_acp(mcp_item)

        assert result["type"] == "text"
        assert result["text"] == "Content"
        assert result["annotations"] == {"audience": ["user"]}

    def test_text_missing_text_field_raises_error(self) -> None:
        """Ошибка при отсутствии поля text."""
        mcp_item = {"type": "text"}

        with pytest.raises(ContentMapperError, match="missing 'text'"):
            mcp_text_to_acp(mcp_item)

    def test_text_empty_string_preserved(self) -> None:
        """Пустая строка сохраняется (валидация на уровне ACP)."""
        mcp_item = {"type": "text", "text": ""}

        result = mcp_text_to_acp(mcp_item)

        assert result["text"] == ""


class TestMcpImageToAcp:
    """Тесты конвертации MCP image content → ACP ImageContent."""

    def test_basic_image_conversion(self) -> None:
        """Базовая конвертация image content."""
        # Tiny 1x1 PNG image (base64)
        b64_data = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAA"
            "AABJRU5ErkJggg=="
        )
        mcp_item = {
            "type": "image",
            "data": b64_data,
            "mimeType": "image/png",
        }

        result = mcp_image_to_acp(mcp_item)

        assert result["type"] == "image"
        assert result["data"] == b64_data
        assert result["mimeType"] == "image/png"

    def test_image_with_uri(self) -> None:
        """Image content с uri."""
        mcp_item = {
            "type": "image",
            "data": "base64data",
            "mimeType": "image/jpeg",
            "uri": "file:///tmp/screenshot.png",
        }

        result = mcp_image_to_acp(mcp_item)

        assert result["uri"] == "file:///tmp/screenshot.png"

    def test_image_with_annotations(self) -> None:
        """Image content с annotations."""
        mcp_item = {
            "type": "image",
            "data": "base64data",
            "mimeType": "image/png",
            "annotations": {"priority": 1.0},
        }

        result = mcp_image_to_acp(mcp_item)

        assert result["annotations"] == {"priority": 1.0}

    def test_image_missing_data_raises_error(self) -> None:
        """Ошибка при отсутствии data."""
        mcp_item = {"type": "image", "mimeType": "image/png"}

        with pytest.raises(ContentMapperError, match="missing 'data'"):
            mcp_image_to_acp(mcp_item)

    def test_image_missing_mime_type_raises_error(self) -> None:
        """Ошибка при отсутствии mimeType."""
        mcp_item = {"type": "image", "data": "base64data"}

        with pytest.raises(ContentMapperError, match="missing 'mimeType'"):
            mcp_image_to_acp(mcp_item)

    def test_image_snake_case_mime_type(self) -> None:
        """Поддержка snake_case mimeType (из Python модели)."""
        mcp_item = {
            "type": "image",
            "data": "base64data",
            "mime_type": "image/webp",
        }

        result = mcp_image_to_acp(mcp_item)

        assert result["mimeType"] == "image/webp"


class TestMcpEmbeddedToAcp:
    """Тесты конвертации MCP embedded resource → ACP EmbeddedResourceContent."""

    def test_text_resource_conversion(self) -> None:
        """Конвертация text resource."""
        mcp_item = {
            "type": "resource",
            "resource": {
                "uri": "file:///script.py",
                "text": "def hello():\n    print('hello')",
                "mimeType": "text/x-python",
            },
        }

        result = mcp_embedded_to_acp(mcp_item)

        assert result["type"] == "resource"
        assert result["resource"]["uri"] == "file:///script.py"
        assert result["resource"]["text"] == "def hello():\n    print('hello')"
        assert result["resource"]["mimeType"] == "text/x-python"

    def test_blob_resource_conversion(self) -> None:
        """Конвертация blob resource."""
        mcp_item = {
            "type": "resource",
            "resource": {
                "uri": "file:///image.png",
                "blob": "iVBORw0KGgo=",
                "mimeType": "image/png",
            },
        }

        result = mcp_embedded_to_acp(mcp_item)

        assert result["type"] == "resource"
        assert result["resource"]["uri"] == "file:///image.png"
        assert result["resource"]["blob"] == "iVBORw0KGgo="
        assert result["resource"]["mimeType"] == "image/png"

    def test_resource_with_annotations(self) -> None:
        """Resource с annotations."""
        mcp_item = {
            "type": "resource",
            "resource": {
                "uri": "file:///test.txt",
                "text": "content",
            },
            "annotations": {"audience": ["assistant"]},
        }

        result = mcp_embedded_to_acp(mcp_item)

        assert result["annotations"] == {"audience": ["assistant"]}

    def test_resource_missing_uri_raises_error(self) -> None:
        """Ошибка при отсутствии uri."""
        mcp_item = {
            "type": "resource",
            "resource": {"text": "content"},
        }

        with pytest.raises(ContentMapperError, match="missing 'uri'"):
            mcp_embedded_to_acp(mcp_item)

    def test_resource_missing_text_and_blob_raises_error(self) -> None:
        """Ошибка при отсутствии text и blob."""
        mcp_item = {
            "type": "resource",
            "resource": {"uri": "file:///test.txt"},
        }

        with pytest.raises(ContentMapperError, match="'text' or 'blob'"):
            mcp_embedded_to_acp(mcp_item)

    def test_resource_missing_resource_field_raises_error(self) -> None:
        """Ошибка при отсутствии поля resource."""
        mcp_item = {"type": "resource"}

        with pytest.raises(ContentMapperError, match="missing 'resource'"):
            mcp_embedded_to_acp(mcp_item)

    def test_resource_not_dict_raises_error(self) -> None:
        """Ошибка если resource не dict."""
        mcp_item = {"type": "resource", "resource": "not a dict"}

        with pytest.raises(ContentMapperError, match="must be a dict"):
            mcp_embedded_to_acp(mcp_item)

    def test_resource_snake_case_mime_type(self) -> None:
        """Поддержка snake_case mimeType."""
        mcp_item = {
            "type": "resource",
            "resource": {
                "uri": "file:///test.txt",
                "text": "content",
                "mime_type": "text/plain",
            },
        }

        result = mcp_embedded_to_acp(mcp_item)

        assert result["resource"]["mimeType"] == "text/plain"


class TestMcpContentItemToAcp:
    """Тесты mcp_content_item_to_acp — dispatcher по типу."""

    def test_dispatches_text(self) -> None:
        """Диспетчеризация text content."""
        item = {"type": "text", "text": "hello"}
        result = mcp_content_item_to_acp(item)
        assert result is not None
        assert result["type"] == "text"

    def test_dispatches_image(self) -> None:
        """Диспетчеризация image content."""
        item = {"type": "image", "data": "base64", "mimeType": "image/png"}
        result = mcp_content_item_to_acp(item)
        assert result is not None
        assert result["type"] == "image"

    def test_dispatches_resource(self) -> None:
        """Диспетчеризация resource content."""
        item = {
            "type": "resource",
            "resource": {"uri": "file:///test", "text": "content"},
        }
        result = mcp_content_item_to_acp(item)
        assert result is not None
        assert result["type"] == "resource"

    def test_unknown_type_returns_none(self) -> None:
        """Неизвестный тип возвращает None."""
        item = {"type": "unknown_type", "data": "something"}
        result = mcp_content_item_to_acp(item)
        assert result is None


class TestMcpContentToAcpList:
    """Тесты mcp_content_to_acp_list — массовая конвертация."""

    def test_empty_list(self) -> None:
        """Пустой список."""
        result = mcp_content_to_acp_list([])
        assert result == []

    def test_single_text_item(self) -> None:
        """Один text item."""
        content = [{"type": "text", "text": "hello"}]
        result = mcp_content_to_acp_list(content)
        assert len(result) == 1
        assert result[0]["type"] == "text"

    def test_mixed_content(self) -> None:
        """Смешанный контент: text + image + resource."""
        content = [
            {"type": "text", "text": "Here is a screenshot:"},
            {
                "type": "image",
                "data": "base64data",
                "mimeType": "image/png",
            },
            {
                "type": "resource",
                "resource": {"uri": "file:///code.py", "text": "print('hi')"},
            },
        ]

        result = mcp_content_to_acp_list(content)

        assert len(result) == 3
        assert result[0]["type"] == "text"
        assert result[1]["type"] == "image"
        assert result[2]["type"] == "resource"

    def test_skips_unknown_types(self) -> None:
        """Пропускает неизвестные типы."""
        content = [
            {"type": "text", "text": "valid"},
            {"type": "unknown", "data": "skip me"},
            {"type": "text", "text": "also valid"},
        ]

        result = mcp_content_to_acp_list(content)

        assert len(result) == 2
        assert all(item["type"] == "text" for item in result)

    def test_skips_invalid_items(self) -> None:
        """Пропускает невалидные items."""
        content = [
            {"type": "text", "text": "valid"},
            {"type": "image"},  # missing data — invalid
            {"type": "text", "text": "also valid"},
        ]

        result = mcp_content_to_acp_list(content)

        assert len(result) == 2

    def test_skips_non_dict_items(self) -> None:
        """Пропускает non-dict items."""
        content = [
            {"type": "text", "text": "valid"},
            "not a dict",
            42,
            None,
        ]

        result = mcp_content_to_acp_list(content)

        assert len(result) == 1


class TestExtractTextFromAcpContent:
    """Тесты extract_text_from_acp_content."""

    def test_empty_list(self) -> None:
        """Пустой список."""
        result = extract_text_from_acp_content([])
        assert result == ""

    def test_single_text(self) -> None:
        """Один text block."""
        content = [{"type": "text", "text": "hello"}]
        result = extract_text_from_acp_content(content)
        assert result == "hello"

    def test_multiple_texts_joined(self) -> None:
        """Несколько text blocks объединяются."""
        content = [
            {"type": "text", "text": "line 1"},
            {"type": "text", "text": "line 2"},
        ]
        result = extract_text_from_acp_content(content)
        assert result == "line 1\nline 2"

    def test_skips_non_text_blocks(self) -> None:
        """Пропускает non-text blocks."""
        content = [
            {"type": "text", "text": "before"},
            {"type": "image", "data": "base64", "mimeType": "image/png"},
            {"type": "text", "text": "after"},
        ]
        result = extract_text_from_acp_content(content)
        assert result == "before\nafter"

    def test_mixed_content_extracts_text_only(self) -> None:
        """Из смешанного контента извлекает только текст."""
        content = [
            {"type": "text", "text": "Analysis:"},
            {"type": "image", "data": "img", "mimeType": "image/png"},
            {
                "type": "resource",
                "resource": {"uri": "file:///f", "text": "code"},
            },
            {"type": "text", "text": "Done."},
        ]
        result = extract_text_from_acp_content(content)
        assert result == "Analysis:\nDone."

"""Тесты для content extraction и validation."""

import pytest

from codelab.server.protocol.content.extractor import ContentExtractor, ExtractedContent
from codelab.server.protocol.content.validator import ContentValidator
from codelab.server.tools.base import ToolExecutionResult


class TestContentExtractor:
    """Тесты для ContentExtractor."""

    @pytest.mark.asyncio
    async def test_extract_with_text_content(self):
        """Извлечение text content из result с content."""
        extractor = ContentExtractor()
        result = ToolExecutionResult(
            success=True,
            output="test",
            content=[{"type": "text", "text": "Hello World"}]
        )

        extracted = await extractor.extract_from_result("tc1", result)

        assert extracted.tool_call_id == "tc1"
        assert extracted.has_content is True
        assert len(extracted.content_items) == 1
        assert extracted.content_items[0]["type"] == "text"
        assert extracted.content_items[0]["text"] == "Hello World"

    @pytest.mark.asyncio
    async def test_extract_with_diff_content(self):
        """Извлечение diff content из result."""
        extractor = ContentExtractor()
        result = ToolExecutionResult(
            success=True,
            output="File modified",
            content=[{
                "type": "diff",
                "path": "file.py",
                "diff": "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new"
            }]
        )

        extracted = await extractor.extract_from_result("tc2", result)

        assert extracted.has_content is True
        assert len(extracted.content_items) == 1
        assert extracted.content_items[0]["type"] == "diff"
        assert extracted.content_items[0]["path"] == "file.py"

    @pytest.mark.asyncio
    async def test_extract_with_multiple_content_items(self):
        """Извлечение нескольких content items из result."""
        extractor = ContentExtractor()
        result = ToolExecutionResult(
            success=True,
            output="Multiple",
            content=[
                {"type": "text", "text": "First"},
                {"type": "text", "text": "Second"}
            ]
        )

        extracted = await extractor.extract_from_result("tc3", result)

        assert extracted.has_content is True
        assert len(extracted.content_items) == 2

    @pytest.mark.asyncio
    async def test_extract_without_content_creates_fallback_from_output(self):
        """Извлечение из result без content создает fallback из output."""
        extractor = ContentExtractor()
        result = ToolExecutionResult(
            success=True,
            output="Plain output text"
        )

        extracted = await extractor.extract_from_result("tc4", result)

        assert extracted.has_content is False
        assert len(extracted.content_items) == 1
        assert extracted.content_items[0]["type"] == "text"
        assert extracted.content_items[0]["text"] == "Plain output text"

    @pytest.mark.asyncio
    async def test_extract_without_content_creates_fallback_from_error(self):
        """Извлечение из failed result без content создает fallback из error."""
        extractor = ContentExtractor()
        result = ToolExecutionResult(
            success=False,
            error="Execution error occurred"
        )

        extracted = await extractor.extract_from_result("tc5", result)

        assert extracted.has_content is False
        assert len(extracted.content_items) == 1
        assert extracted.content_items[0]["type"] == "text"
        assert "Execution error" in extracted.content_items[0]["text"]

    @pytest.mark.asyncio
    async def test_extract_without_content_or_output_creates_empty_fallback(self):
        """Извлечение из result без content и output создает пустой fallback."""
        extractor = ContentExtractor()
        result = ToolExecutionResult(success=True)

        extracted = await extractor.extract_from_result("tc6", result)

        assert extracted.has_content is False
        assert len(extracted.content_items) == 1
        assert extracted.content_items[0]["type"] == "text"
        assert extracted.content_items[0]["text"] == ""

    @pytest.mark.asyncio
    async def test_extract_batch_multiple_results(self):
        """Batch extraction из нескольких results."""
        extractor = ContentExtractor()
        results = [
            (
                "tc1",
                ToolExecutionResult(
                    success=True,
                    output="1",
                    content=[{"type": "text", "text": "A"}]
                )
            ),
            (
                "tc2",
                ToolExecutionResult(
                    success=True,
                    output="2",
                    content=[{"type": "text", "text": "B"}]
                )
            ),
            ("tc3", ToolExecutionResult(success=True, output="3"))
        ]

        extracted = await extractor.extract_batch(results)

        assert len(extracted) == 3
        assert extracted[0].tool_call_id == "tc1"
        assert extracted[0].has_content is True
        assert extracted[1].tool_call_id == "tc2"
        assert extracted[1].has_content is True
        assert extracted[2].tool_call_id == "tc3"
        assert extracted[2].has_content is False

    @pytest.mark.asyncio
    async def test_extract_batch_empty_list(self):
        """Batch extraction из пустого списка."""
        extractor = ContentExtractor()
        results: list[tuple[str, ToolExecutionResult]] = []

        extracted = await extractor.extract_batch(results)

        assert len(extracted) == 0

    @pytest.mark.asyncio
    async def test_extract_preserves_all_content_fields(self):
        """Извлечение сохраняет все поля content items."""
        extractor = ContentExtractor()
        result = ToolExecutionResult(
            success=True,
            output="test",
            content=[{
                "type": "image",
                "data": "base64encodeddata",
                "format": "png",
                "width": 100,
                "height": 200
            }]
        )

        extracted = await extractor.extract_from_result("tc7", result)

        assert extracted.content_items[0]["data"] == "base64encodeddata"
        assert extracted.content_items[0]["format"] == "png"
        assert extracted.content_items[0]["width"] == 100
        assert extracted.content_items[0]["height"] == 200


class TestContentValidator:
    """Тесты для ContentValidator."""

    def test_validate_text_content_valid(self):
        """Валидация валидного text content."""
        validator = ContentValidator()
        item = {"type": "text", "text": "Hello"}

        is_valid, error = validator.validate_content_item(item)

        assert is_valid is True
        assert error is None

    def test_validate_text_content_with_annotations(self):
        """Валидация text content с опциональными annotations."""
        validator = ContentValidator()
        item = {
            "type": "text",
            "text": "Hello",
            "annotations": [{"type": "strong", "start": 0, "end": 5}]
        }

        is_valid, error = validator.validate_content_item(item)

        assert is_valid is True

    def test_validate_diff_content_valid(self):
        """Валидация валидного diff content."""
        validator = ContentValidator()
        item = {"type": "diff", "path": "file.py", "diff": "..."}

        is_valid, error = validator.validate_content_item(item)

        assert is_valid is True

    def test_validate_image_content_valid(self):
        """Валидация валидного image content."""
        validator = ContentValidator()
        item = {
            "type": "image",
            "data": "base64...",
            "format": "png",
            "width": 100,
            "height": 200
        }

        is_valid, error = validator.validate_content_item(item)

        assert is_valid is True

    def test_validate_audio_content_valid(self):
        """Валидация валидного audio content."""
        validator = ContentValidator()
        item = {"type": "audio", "data": "base64...", "format": "mp3"}

        is_valid, error = validator.validate_content_item(item)

        assert is_valid is True

    def test_validate_embedded_content_valid(self):
        """Валидация валидного embedded content."""
        validator = ContentValidator()
        item = {
            "type": "embedded",
            "content": {"type": "text", "text": "Embedded"}
        }

        is_valid, error = validator.validate_content_item(item)

        assert is_valid is True

    def test_validate_resource_link_content_valid(self):
        """Валидация валидного resource_link content."""
        validator = ContentValidator()
        item = {"type": "resource_link", "uri": "https://example.com"}

        is_valid, error = validator.validate_content_item(item)

        assert is_valid is True

    def test_validate_missing_type_field(self):
        """Валидация без type поля."""
        validator = ContentValidator()
        item = {"text": "Hello"}

        is_valid, error = validator.validate_content_item(item)

        assert is_valid is False
        assert "type" in error.lower()

    def test_validate_unsupported_type(self):
        """Валидация неподдерживаемого типа."""
        validator = ContentValidator()
        item = {"type": "unknown", "data": "..."}

        is_valid, error = validator.validate_content_item(item)

        assert is_valid is False
        assert "Unsupported" in error

    def test_validate_missing_required_field_text(self):
        """Валидация text без text поля."""
        validator = ContentValidator()
        item = {"type": "text"}

        is_valid, error = validator.validate_content_item(item)

        assert is_valid is False
        assert "text" in error

    def test_validate_missing_required_field_diff(self):
        """Валидация diff без diff поля."""
        validator = ContentValidator()
        item = {"type": "diff", "path": "file.py"}

        is_valid, error = validator.validate_content_item(item)

        assert is_valid is False
        assert "diff" in error

    def test_validate_missing_required_field_image(self):
        """Валидация image без format поля."""
        validator = ContentValidator()
        item = {"type": "image", "data": "..."}

        is_valid, error = validator.validate_content_item(item)

        assert is_valid is False
        assert "format" in error

    def test_validate_content_list_all_valid(self):
        """Валидация списка с валидными content items."""
        validator = ContentValidator()
        items = [
            {"type": "text", "text": "A"},
            {"type": "diff", "path": "f.py", "diff": "..."},
            {"type": "image", "data": "...", "format": "png"}
        ]

        all_valid, errors = validator.validate_content_list(items)

        assert all_valid is True
        assert len(errors) == 0

    def test_validate_content_list_with_errors(self):
        """Валидация списка с невалидными content items."""
        validator = ContentValidator()
        items = [
            {"type": "text", "text": "Valid"},
            {"type": "invalid"},  # Missing type fields
            {"type": "diff", "path": "f.py"}  # Missing diff field
        ]

        all_valid, errors = validator.validate_content_list(items)

        assert all_valid is False
        assert len(errors) == 2

    def test_sanitize_removes_unknown_fields(self):
        """Sanitization удаляет неизвестные поля."""
        validator = ContentValidator()
        item = {
            "type": "text",
            "text": "Hello",
            "unknown_field": "should be removed",
            "another_unknown": 123
        }

        sanitized = validator.sanitize_content_item(item)

        assert "unknown_field" not in sanitized
        assert "another_unknown" not in sanitized
        assert sanitized["type"] == "text"
        assert sanitized["text"] == "Hello"

    def test_sanitize_keeps_optional_fields(self):
        """Sanitization сохраняет опциональные поля."""
        validator = ContentValidator()
        item = {
            "type": "text",
            "text": "Hello",
            "annotations": [{"type": "strong"}]
        }

        sanitized = validator.sanitize_content_item(item)

        assert "annotations" in sanitized
        assert sanitized["annotations"] == [{"type": "strong"}]

    def test_sanitize_image_with_optional_fields(self):
        """Sanitization для image с опциональными полями."""
        validator = ContentValidator()
        item = {
            "type": "image",
            "data": "base64...",
            "format": "png",
            "width": 100,
            "height": 200,
            "alt_text": "Description",
            "unknown": "value"
        }

        sanitized = validator.sanitize_content_item(item)

        assert "unknown" not in sanitized
        assert sanitized["width"] == 100
        assert sanitized["height"] == 200
        assert sanitized["alt_text"] == "Description"

    def test_sanitize_preserves_non_restricted_types(self):
        """Sanitization не удаляет поля для неизвестных типов."""
        validator = ContentValidator()
        item = {
            "type": "unknown",
            "field1": "value1",
            "field2": "value2"
        }

        sanitized = validator.sanitize_content_item(item)

        assert sanitized == item


class TestPromptOrchestratorContentIntegration:
    """Integration тесты для content в PromptOrchestrator."""

    @pytest.mark.asyncio
    async def test_extracted_content_dataclass(self):
        """Проверка ExtractedContent dataclass."""
        content = ExtractedContent(
            tool_call_id="tc1",
            content_items=[{"type": "text", "text": "test"}],
            has_content=True
        )

        assert content.tool_call_id == "tc1"
        assert len(content.content_items) == 1
        assert content.has_content is True

    @pytest.mark.asyncio
    async def test_content_extractor_with_empty_content_list(self):
        """Тест extractor с пустым списком content."""
        extractor = ContentExtractor()
        result = ToolExecutionResult(
            success=True,
            output="test",
            content=[]
        )

        extracted = await extractor.extract_from_result("tc1", result)

        # Пустой список content = fallback
        assert extracted.has_content is False
        assert len(extracted.content_items) == 1

"""Тесты для content formatting для LLM провайдеров."""

import pytest

from codelab.server.protocol.content.extractor import ExtractedContent
from codelab.server.protocol.content.formatter import ContentFormatter


class TestContentFormatter:
    """Тесты для ContentFormatter."""

    @pytest.fixture
    def formatter(self) -> ContentFormatter:
        """Создать instance ContentFormatter."""
        return ContentFormatter()

    # OpenAI Formatting Tests
    def test_format_text_for_openai(self, formatter: ContentFormatter) -> None:
        """Форматирование text content для OpenAI."""
        extracted = ExtractedContent(
            tool_call_id="tc1",
            content_items=[{"type": "text", "text": "Hello, World!"}],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="openai")

        assert result["role"] == "tool"
        assert result["tool_call_id"] == "tc1"
        assert "Hello, World!" in result["content"]

    def test_format_multiple_text_for_openai(self, formatter: ContentFormatter) -> None:
        """Форматирование нескольких text items для OpenAI."""
        extracted = ExtractedContent(
            tool_call_id="tc2",
            content_items=[
                {"type": "text", "text": "Line 1"},
                {"type": "text", "text": "Line 2"},
            ],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="openai")

        assert result["role"] == "tool"
        assert "Line 1" in result["content"]
        assert "Line 2" in result["content"]

    def test_format_diff_for_openai(self, formatter: ContentFormatter) -> None:
        """Форматирование diff content для OpenAI."""
        extracted = ExtractedContent(
            tool_call_id="tc3",
            content_items=[
                {
                    "type": "diff",
                    "path": "file.py",
                    "diff": "-old line\n+new line",
                }
            ],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="openai")

        assert result["role"] == "tool"
        assert "file.py" in result["content"]
        assert "diff" in result["content"].lower()
        assert "-old line" in result["content"]
        assert "+new line" in result["content"]

    def test_format_image_for_openai(self, formatter: ContentFormatter) -> None:
        """Форматирование image content для OpenAI."""
        extracted = ExtractedContent(
            tool_call_id="tc4",
            content_items=[
                {
                    "type": "image",
                    "data": "base64encodeddata",
                    "format": "png",
                    "alt_text": "A screenshot",
                }
            ],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="openai")

        assert result["role"] == "tool"
        assert "[Image:" in result["content"]
        assert "A screenshot" in result["content"]
        assert "png" in result["content"]

    def test_format_audio_for_openai(self, formatter: ContentFormatter) -> None:
        """Форматирование audio content для OpenAI."""
        extracted = ExtractedContent(
            tool_call_id="tc5",
            content_items=[
                {
                    "type": "audio",
                    "data": "audiodata",
                    "format": "mp3",
                }
            ],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="openai")

        assert result["role"] == "tool"
        assert "[Audio file" in result["content"]
        assert "mp3" in result["content"]

    def test_format_resource_link_for_openai(self, formatter: ContentFormatter) -> None:
        """Форматирование resource_link content для OpenAI."""
        extracted = ExtractedContent(
            tool_call_id="tc6",
            content_items=[
                {
                    "type": "resource_link",
                    "uri": "https://example.com/resource",
                }
            ],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="openai")

        assert result["role"] == "tool"
        assert "[Resource:" in result["content"]
        assert "https://example.com/resource" in result["content"]

    def test_format_embedded_for_openai(self, formatter: ContentFormatter) -> None:
        """Форматирование embedded content для OpenAI."""
        extracted = ExtractedContent(
            tool_call_id="tc7",
            content_items=[
                {
                    "type": "embedded",
                    "content": [{"type": "text", "text": "Embedded text"}],
                }
            ],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="openai")

        assert result["role"] == "tool"
        assert "[Embedded content]" in result["content"]
        assert "Embedded text" in result["content"]

    # Anthropic Formatting Tests
    def test_format_text_for_anthropic(self, formatter: ContentFormatter) -> None:
        """Форматирование text content для Anthropic."""
        extracted = ExtractedContent(
            tool_call_id="tc1",
            content_items=[{"type": "text", "text": "Hello, Claude!"}],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="anthropic")

        assert result["role"] == "user"
        assert isinstance(result["content"], list)
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "tool_result"
        assert result["content"][0]["tool_use_id"] == "tc1"
        assert "Hello, Claude!" in result["content"][0]["content"]

    def test_format_multiple_text_for_anthropic(self, formatter: ContentFormatter) -> None:
        """Форматирование нескольких text items для Anthropic."""
        extracted = ExtractedContent(
            tool_call_id="tc2",
            content_items=[
                {"type": "text", "text": "First"},
                {"type": "text", "text": "Second"},
            ],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="anthropic")

        assert result["role"] == "user"
        assert isinstance(result["content"], list)
        assert result["content"][0]["type"] == "tool_result"
        content_text = result["content"][0]["content"]
        assert "First" in content_text
        assert "Second" in content_text

    def test_format_diff_for_anthropic(self, formatter: ContentFormatter) -> None:
        """Форматирование diff content для Anthropic."""
        extracted = ExtractedContent(
            tool_call_id="tc3",
            content_items=[
                {
                    "type": "diff",
                    "path": "main.py",
                    "diff": "-print('old')\n+print('new')",
                }
            ],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="anthropic")

        assert result["role"] == "user"
        content_text = result["content"][0]["content"]
        assert "main.py" in content_text
        assert "diff" in content_text.lower()

    def test_format_image_for_anthropic(self, formatter: ContentFormatter) -> None:
        """Форматирование image content для Anthropic."""
        extracted = ExtractedContent(
            tool_call_id="tc4",
            content_items=[
                {
                    "type": "image",
                    "data": "imagedata",
                    "format": "jpg",
                    "alt_text": "A photo",
                }
            ],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="anthropic")

        assert result["role"] == "user"
        content_text = result["content"][0]["content"]
        assert "[Image:" in content_text
        assert "A photo" in content_text

    def test_format_audio_for_anthropic(self, formatter: ContentFormatter) -> None:
        """Форматирование audio content для Anthropic."""
        extracted = ExtractedContent(
            tool_call_id="tc5",
            content_items=[
                {
                    "type": "audio",
                    "data": "audiodata",
                    "format": "wav",
                }
            ],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="anthropic")

        assert result["role"] == "user"
        content_text = result["content"][0]["content"]
        assert "[Audio file" in content_text

    def test_format_resource_link_for_anthropic(self, formatter: ContentFormatter) -> None:
        """Форматирование resource_link content для Anthropic."""
        extracted = ExtractedContent(
            tool_call_id="tc6",
            content_items=[
                {
                    "type": "resource_link",
                    "uri": "https://docs.example.com",
                }
            ],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="anthropic")

        assert result["role"] == "user"
        content_text = result["content"][0]["content"]
        assert "[Resource:" in content_text

    def test_format_embedded_for_anthropic(self, formatter: ContentFormatter) -> None:
        """Форматирование embedded content для Anthropic."""
        extracted = ExtractedContent(
            tool_call_id="tc7",
            content_items=[
                {
                    "type": "embedded",
                    "content": [{"type": "text", "text": "Nested content"}],
                }
            ],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="anthropic")

        assert result["role"] == "user"
        content_text = result["content"][0]["content"]
        assert "[Embedded content]" in content_text

    # Mixed Content Tests
    def test_format_mixed_content_for_openai(self, formatter: ContentFormatter) -> None:
        """Форматирование смешанного content для OpenAI."""
        extracted = ExtractedContent(
            tool_call_id="tc_mixed",
            content_items=[
                {"type": "text", "text": "Start"},
                {
                    "type": "diff",
                    "path": "file.txt",
                    "diff": "-old\n+new",
                },
                {"type": "text", "text": "End"},
            ],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="openai")

        assert result["role"] == "tool"
        content = result["content"]
        assert "Start" in content
        assert "End" in content
        assert "file.txt" in content

    def test_format_mixed_content_for_anthropic(self, formatter: ContentFormatter) -> None:
        """Форматирование смешанного content для Anthropic."""
        extracted = ExtractedContent(
            tool_call_id="tc_mixed",
            content_items=[
                {"type": "text", "text": "Description"},
                {
                    "type": "image",
                    "data": "data",
                    "format": "png",
                    "alt_text": "Screenshot",
                },
            ],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="anthropic")

        assert result["role"] == "user"
        content_text = result["content"][0]["content"]
        assert "Description" in content_text
        assert "Screenshot" in content_text

    # Batch Formatting Tests
    def test_format_batch_for_openai(self, formatter: ContentFormatter) -> None:
        """Форматирование batch content для OpenAI."""
        contents = [
            ExtractedContent(
                tool_call_id="tc1",
                content_items=[{"type": "text", "text": "Result 1"}],
                has_content=True,
            ),
            ExtractedContent(
                tool_call_id="tc2",
                content_items=[{"type": "text", "text": "Result 2"}],
                has_content=True,
            ),
        ]

        results = formatter.format_batch_for_llm(contents, provider="openai")

        assert len(results) == 2
        assert results[0]["tool_call_id"] == "tc1"
        assert results[1]["tool_call_id"] == "tc2"
        assert all(r["role"] == "tool" for r in results)

    def test_format_batch_for_anthropic(self, formatter: ContentFormatter) -> None:
        """Форматирование batch content для Anthropic."""
        contents = [
            ExtractedContent(
                tool_call_id="tc1",
                content_items=[{"type": "text", "text": "Response 1"}],
                has_content=True,
            ),
            ExtractedContent(
                tool_call_id="tc2",
                content_items=[{"type": "text", "text": "Response 2"}],
                has_content=True,
            ),
        ]

        results = formatter.format_batch_for_llm(contents, provider="anthropic")

        assert len(results) == 2
        assert all(r["role"] == "user" for r in results)
        assert results[0]["content"][0]["tool_use_id"] == "tc1"
        assert results[1]["content"][0]["tool_use_id"] == "tc2"

    def test_format_empty_batch(self, formatter: ContentFormatter) -> None:
        """Форматирование пустого batch."""
        results = formatter.format_batch_for_llm([], provider="openai")
        assert results == []

    # Error Tests
    def test_format_unsupported_provider(self, formatter: ContentFormatter) -> None:
        """Попытка форматирования для неподдерживаемого провайдера."""
        extracted = ExtractedContent(
            tool_call_id="tc1",
            content_items=[{"type": "text", "text": "Test"}],
            has_content=True,
        )

        with pytest.raises(ValueError, match="Unsupported provider"):
            formatter.format_for_llm(extracted, provider="invalid")  # type: ignore

    # Edge Cases
    def test_format_empty_text_content(self, formatter: ContentFormatter) -> None:
        """Форматирование пустого text content."""
        extracted = ExtractedContent(
            tool_call_id="tc1",
            content_items=[{"type": "text", "text": ""}],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="openai")

        assert result["role"] == "tool"
        assert result["content"] == ""

    def test_format_content_with_special_characters(
        self, formatter: ContentFormatter
    ) -> None:
        """Форматирование content со спецсимволами."""
        extracted = ExtractedContent(
            tool_call_id="tc1",
            content_items=[
                {"type": "text", "text": 'Text with "quotes" and \\backslashes\\'}
            ],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="openai")

        assert '"quotes"' in result["content"]
        assert "\\backslashes\\" in result["content"]

    def test_format_deeply_nested_embedded(self, formatter: ContentFormatter) -> None:
        """Форматирование глубоко вложенного embedded content."""
        extracted = ExtractedContent(
            tool_call_id="tc1",
            content_items=[
                {
                    "type": "embedded",
                    "content": [
                        {
                            "type": "embedded",
                            "content": [
                                {"type": "text", "text": "Deep content"}
                            ],
                        }
                    ],
                }
            ],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="openai")

        assert "Deep content" in result["content"]
        assert "[Embedded content]" in result["content"]

    def test_format_image_without_alt_text(self, formatter: ContentFormatter) -> None:
        """Форматирование image без alt_text."""
        extracted = ExtractedContent(
            tool_call_id="tc1",
            content_items=[
                {
                    "type": "image",
                    "data": "data",
                    "format": "png",
                }
            ],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="openai")

        assert "[Image:" in result["content"]
        assert "Image" in result["content"]

    def test_format_resource_link_without_uri(self, formatter: ContentFormatter) -> None:
        """Форматирование resource_link без uri."""
        extracted = ExtractedContent(
            tool_call_id="tc1",
            content_items=[
                {
                    "type": "resource_link",
                }
            ],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="openai")

        assert "[Resource:" in result["content"]

    def test_format_large_diff_content(self, formatter: ContentFormatter) -> None:
        """Форматирование большого diff."""
        large_diff = "\n".join([f"-line {i}\n+line {i+1}" for i in range(100)])

        extracted = ExtractedContent(
            tool_call_id="tc1",
            content_items=[
                {
                    "type": "diff",
                    "path": "large_file.py",
                    "diff": large_diff,
                }
            ],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="openai")

        assert "large_file.py" in result["content"]
        assert "line 0" in result["content"]
        assert "line 99" in result["content"]

    def test_default_provider_is_openai(self, formatter: ContentFormatter) -> None:
        """Проверка, что default провайдер - openai."""
        extracted = ExtractedContent(
            tool_call_id="tc1",
            content_items=[{"type": "text", "text": "Test"}],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted)

        assert result["role"] == "tool"

    def test_format_anthropic_structure_correctness(
        self, formatter: ContentFormatter
    ) -> None:
        """Проверка корректности структуры Anthropic response."""
        extracted = ExtractedContent(
            tool_call_id="my_tool_call",
            content_items=[{"type": "text", "text": "Anthropic test"}],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="anthropic")

        # Validate Anthropic structure
        assert "role" in result
        assert "content" in result
        assert result["role"] == "user"
        assert isinstance(result["content"], list)
        assert len(result["content"]) == 1

        tool_result = result["content"][0]
        assert tool_result["type"] == "tool_result"
        assert tool_result["tool_use_id"] == "my_tool_call"
        assert isinstance(tool_result["content"], str)

    def test_merge_content_items_separator(self, formatter: ContentFormatter) -> None:
        """Проверка разделителя при объединении content items."""
        extracted = ExtractedContent(
            tool_call_id="tc1",
            content_items=[
                {"type": "text", "text": "First"},
                {"type": "text", "text": "Second"},
                {"type": "text", "text": "Third"},
            ],
            has_content=True,
        )

        result = formatter.format_for_llm(extracted, provider="openai")

        # Проверить, что items объединены с двойным новой строкой
        content = result["content"]
        assert content == "First\n\nSecond\n\nThird"

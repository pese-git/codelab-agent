"""Тесты Anthropic провайдера с мультимодальным содержимым."""

from codelab.server.llm.content_parts import ContentPart
from codelab.server.llm.models import LLMMessage
from codelab.server.llm.providers.anthropic import AnthropicProvider


class TestAnthropicContentPartFormatting:
    """Тесты форматирования ContentPart для Anthropic."""

    def setup_method(self) -> None:
        self.provider = AnthropicProvider()

    def test_text_part_formatting(self) -> None:
        part = ContentPart.make_text("Hello")
        result = self.provider._content_part_to_anthropic(part)
        assert result == {"type": "text", "text": "Hello"}

    def test_image_part_formatting(self) -> None:
        part = ContentPart.make_image(data="abc", mime_type="image/png")
        result = self.provider._content_part_to_anthropic(part)
        assert result is not None
        assert result["type"] == "image"
        assert result["source"]["type"] == "base64"
        assert result["source"]["media_type"] == "image/png"
        assert result["source"]["data"] == "abc"

    def test_mixed_content_formatting(self) -> None:
        messages = [
            LLMMessage(
                role="user",
                content=[
                    ContentPart.make_text("Look:"),
                    ContentPart.make_image(data="abc", mime_type="image/png"),
                ],
            ),
        ]
        result = self.provider._convert_to_anthropic_format(messages)
        assert len(result) == 1
        content = result[0]["content"]
        assert isinstance(content, list)
        assert len(content) == 2
        assert content[0]["type"] == "text"
        assert content[1]["type"] == "image"

    def test_vision_capability(self) -> None:
        assert self.provider.capabilities.supports_vision is True

"""Тесты OpenAI провайдера с мультимодальным содержимым."""

from codelab.server.llm.content_parts import ContentPart
from codelab.server.llm.models import LLMMessage
from codelab.server.llm.providers.openai import OpenAIProvider


class TestOpenAIContentPartFormatting:
    """Тесты форматирования ContentPart для OpenAI."""

    def setup_method(self) -> None:
        self.provider = OpenAIProvider()

    def test_text_part_formatting(self) -> None:
        part = ContentPart.make_text("Hello")
        result = self.provider._content_part_to_openai(part)
        assert result == {"type": "text", "text": "Hello"}

    def test_image_part_formatting(self) -> None:
        part = ContentPart.make_image(data="abc", mime_type="image/png")
        result = self.provider._content_part_to_openai(part)
        assert result is not None
        assert result["type"] == "image_url"
        assert result["image_url"]["url"] == "data:image/png;base64,abc"

    def test_audio_part_formatting(self) -> None:
        part = ContentPart.make_audio(data="abc", mime_type="audio/wav")
        result = self.provider._content_part_to_openai(part)
        assert result is not None
        assert result["type"] == "input_audio"
        assert result["input_audio"]["data"] == "abc"
        assert result["input_audio"]["format"] == "wav"

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
        result = self.provider._convert_to_openai_format(messages)
        assert len(result) == 1
        content = result[0]["content"]
        assert isinstance(content, list)
        assert len(content) == 2
        assert content[0]["type"] == "text"
        assert content[1]["type"] == "image_url"

    def test_vision_capability(self) -> None:
        assert self.provider.capabilities.supports_vision is True

    def test_audio_capability(self) -> None:
        assert self.provider.capabilities.supports_audio is True

"""Тесты для LLMMessage с мультимодальным содержимым."""

from codelab.server.llm.content_parts import ContentPart
from codelab.server.llm.models import LLMMessage


class TestLLMMessageMultimodal:
    """Тесты LLMMessage с multimodal content."""

    def test_string_content(self) -> None:
        msg = LLMMessage(role="user", content="Hello")
        assert isinstance(msg.content, str)
        assert msg.content == "Hello"

    def test_multimodal_content(self) -> None:
        parts = [
            ContentPart.make_text("Look:"),
            ContentPart.make_image(data="abc", mime_type="image/png"),
        ]
        msg = LLMMessage(role="user", content=parts)
        assert isinstance(msg.content, list)
        assert len(msg.content) == 2
        assert msg.content[0].type == "text"
        assert msg.content[1].type == "image"

    def test_none_content(self) -> None:
        msg = LLMMessage(role="user")
        assert msg.content is None

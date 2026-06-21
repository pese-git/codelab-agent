"""Тесты vision fallback для провайдеров без поддержки vision."""

import logging

import pytest

from codelab.server.llm.base import LLMCapabilities
from codelab.server.llm.content_parts import ContentPart
from codelab.server.llm.providers.openai_compatible import OpenAICompatibleProvider


class NoVisionProvider(OpenAICompatibleProvider):
    """Тестовый провайдер без vision."""

    @property
    def name(self) -> str:
        return "no_vision"

    @property
    def capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(
            supports_tools=True,
            supports_streaming=True,
            supports_function_calling=True,
            supports_vision=False,
        )


class TestVisionFallback:
    """Тесты fallback при отсутствии vision support."""

    def test_no_vision_provider_skips_image(self, caplog: pytest.LogCaptureFixture) -> None:
        provider = NoVisionProvider()
        part = ContentPart.make_image(data="abc", mime_type="image/png")

        with caplog.at_level(logging.WARNING):
            result = provider._content_part_to_openai(part)

        assert result is None

    def test_no_vision_provider_keeps_text(self) -> None:
        provider = NoVisionProvider()
        part = ContentPart.make_text("Hello")
        result = provider._content_part_to_openai(part)
        assert result == {"type": "text", "text": "Hello"}

    def test_no_vision_provider_mixed_content(self) -> None:
        provider = NoVisionProvider()
        parts = [
            ContentPart.make_text("Look:"),
            ContentPart.make_image(data="abc", mime_type="image/png"),
        ]
        result = provider._convert_content_parts_to_openai(parts)
        assert len(result) == 1
        assert result[0]["type"] == "text"
        assert result[0]["text"] == "Look:"
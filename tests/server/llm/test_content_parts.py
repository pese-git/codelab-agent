"""Тесты для ContentPart — доменной модели multimodal содержимого."""

from dataclasses import FrozenInstanceError

import pytest

from codelab.server.llm.content_parts import ContentPart


class TestContentPartCreation:
    """Тесты создания ContentPart."""

    def test_text_factory(self) -> None:
        part = ContentPart.make_text("Hello")
        assert part.type == "text"
        assert part.text == "Hello"
        assert part.data is None
        assert part.mime_type is None

    def test_image_factory(self) -> None:
        part = ContentPart.make_image(data="abc123", mime_type="image/png")
        assert part.type == "image"
        assert part.text is None
        assert part.data == "abc123"
        assert part.mime_type == "image/png"

    def test_audio_factory(self) -> None:
        part = ContentPart.make_audio(data="abc123", mime_type="audio/wav")
        assert part.type == "audio"
        assert part.text is None
        assert part.data == "abc123"
        assert part.mime_type == "audio/wav"

    def test_direct_construction(self) -> None:
        part = ContentPart(type="text", text="hi")
        assert part.type == "text"
        assert part.text == "hi"


class TestContentPartImmutability:
    """Тесты неизменяемости ContentPart."""

    def test_frozen_text(self) -> None:
        part = ContentPart.make_text("Hello")
        with pytest.raises(FrozenInstanceError):
            part.text = "new value"  # type: ignore[misc]

    def test_frozen_image(self) -> None:
        part = ContentPart.make_image(data="abc", mime_type="image/png")
        with pytest.raises(FrozenInstanceError):
            part.data = "new"  # type: ignore[misc]

    def test_frozen_audio(self) -> None:
        part = ContentPart.make_audio(data="abc", mime_type="audio/wav")
        with pytest.raises(FrozenInstanceError):
            part.data = "new"  # type: ignore[misc]


class TestContentPartIsMultimodal:
    """Тесты свойства is_multimodal."""

    def test_text_not_multimodal(self) -> None:
        assert ContentPart.make_text("Hello").is_multimodal is False

    def test_image_is_multimodal(self) -> None:
        assert ContentPart.make_image(data="abc", mime_type="image/png").is_multimodal is True

    def test_audio_is_multimodal(self) -> None:
        assert ContentPart.make_audio(data="abc", mime_type="audio/wav").is_multimodal is True

"""Unit тесты для domain UserPrompt."""

from codelab.server.domain.conversation import Image, Resource
from codelab.server.domain.prompt import UserPrompt


class TestUserPrompt:
    def test_defaults(self) -> None:
        prompt = UserPrompt()
        assert prompt.text == ""
        assert prompt.resources == []
        assert prompt.images == []

    def test_with_text(self) -> None:
        prompt = UserPrompt(text="hello world")
        assert prompt.text == "hello world"

    def test_has_multimodal_false(self) -> None:
        prompt = UserPrompt(text="hello")
        assert prompt.has_multimodal is False

    def test_has_multimodal_with_resource(self) -> None:
        prompt = UserPrompt(
            text="check",
            resources=[Resource(uri="file:///tmp")],
        )
        assert prompt.has_multimodal is True

    def test_has_multimodal_with_image(self) -> None:
        prompt = UserPrompt(
            text="look",
            images=[Image(data="base64")],
        )
        assert prompt.has_multimodal is True

    def test_get_text_preview_short(self) -> None:
        prompt = UserPrompt(text="hello")
        assert prompt.get_text_preview() == "hello"

    def test_get_text_preview_truncated(self) -> None:
        prompt = UserPrompt(text="a" * 200)
        preview = prompt.get_text_preview(max_length=100)
        assert len(preview) == 103
        assert preview.endswith("...")

    def test_get_text_preview_exact(self) -> None:
        prompt = UserPrompt(text="a" * 100)
        preview = prompt.get_text_preview(max_length=100)
        assert preview == "a" * 100

    def test_frozen(self) -> None:
        import pytest

        prompt = UserPrompt(text="hello")
        with pytest.raises(AttributeError):
            prompt.text = "other"  # type: ignore[misc]

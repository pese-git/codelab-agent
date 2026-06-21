"""Тесты для domain моделей мультимодального контента.

Тестирует:
- ContentBlock и его наследники (TextContent, ImageContent и т.д.)
- PromptCapabilities
- ContentBuilder
"""

from __future__ import annotations

import pytest

from codelab.client.domain import (
    AudioContent,
    ContentBuilder,
    ImageContent,
    PromptCapabilities,
    ResourceContent,
    ResourceLinkContent,
    TextContent,
    UnsupportedContentError,
)


class TestTextContent:
    """Тесты для TextContent."""

    def test_to_dict(self) -> None:
        """TextContent корректно сериализуется."""
        content = TextContent(text="Hello, world!")
        result = content.to_dict()

        assert result == {
            "type": "text",
            "text": "Hello, world!",
        }

    def test_type_name(self) -> None:
        """TextContent имеет правильный type_name."""
        content = TextContent(text="test")
        assert content.type_name == "text"


class TestImageContent:
    """Тесты для ImageContent."""

    def test_to_dict_without_uri(self) -> None:
        """ImageContent без URI корректно сериализуется."""
        content = ImageContent(
            data="base64data",
            mime_type="image/png",
        )
        result = content.to_dict()

        assert result == {
            "type": "image",
            "data": "base64data",
            "mimeType": "image/png",
        }

    def test_to_dict_with_uri(self) -> None:
        """ImageContent с URI корректно сериализуется."""
        content = ImageContent(
            data="base64data",
            mime_type="image/jpeg",
            uri="https://example.com/image.jpg",
        )
        result = content.to_dict()

        assert result == {
            "type": "image",
            "data": "base64data",
            "mimeType": "image/jpeg",
            "uri": "https://example.com/image.jpg",
        }

    def test_type_name(self) -> None:
        """ImageContent имеет правильный type_name."""
        content = ImageContent(data="data", mime_type="image/png")
        assert content.type_name == "image"


class TestAudioContent:
    """Тесты для AudioContent."""

    def test_to_dict(self) -> None:
        """AudioContent корректно сериализуется."""
        content = AudioContent(
            data="base64audiodata",
            mime_type="audio/wav",
        )
        result = content.to_dict()

        assert result == {
            "type": "audio",
            "data": "base64audiodata",
            "mimeType": "audio/wav",
        }


class TestResourceContent:
    """Тесты для ResourceContent."""

    def test_to_dict_with_text(self) -> None:
        """ResourceContent с текстом корректно сериализуется."""
        content = ResourceContent(
            uri="file:///path/to/code.py",
            text="def hello(): pass",
            mime_type="text/x-python",
        )
        result = content.to_dict()

        assert result == {
            "type": "resource",
            "resource": {
                "uri": "file:///path/to/code.py",
                "text": "def hello(): pass",
                "mimeType": "text/x-python",
            },
        }

    def test_to_dict_with_blob(self) -> None:
        """ResourceContent с blob корректно сериализуется."""
        content = ResourceContent(
            uri="file:///path/to/binary",
            blob="base64blobdata",
            mime_type="application/octet-stream",
        )
        result = content.to_dict()

        assert result["resource"]["blob"] == "base64blobdata"


class TestResourceLinkContent:
    """Тесты для ResourceLinkContent."""

    def test_to_dict_minimal(self) -> None:
        """ResourceLinkContent с минимальными полями сериализуется."""
        content = ResourceLinkContent(
            uri="file:///path/to/doc.pdf",
            name="doc.pdf",
        )
        result = content.to_dict()

        assert result == {
            "type": "resource_link",
            "uri": "file:///path/to/doc.pdf",
            "name": "doc.pdf",
        }

    def test_to_dict_full(self) -> None:
        """ResourceLinkContent со всеми полями сериализуется."""
        content = ResourceLinkContent(
            uri="file:///path/to/doc.pdf",
            name="doc.pdf",
            mime_type="application/pdf",
            description="A PDF document",
            size=1024,
        )
        result = content.to_dict()

        assert result == {
            "type": "resource_link",
            "uri": "file:///path/to/doc.pdf",
            "name": "doc.pdf",
            "mimeType": "application/pdf",
            "description": "A PDF document",
            "size": 1024,
        }


class TestPromptCapabilities:
    """Тесты для PromptCapabilities."""

    def test_default_capabilities(self) -> None:
        """Default capabilities - все false."""
        caps = PromptCapabilities()
        assert caps.image is False
        assert caps.audio is False
        assert caps.embedded_context is False

    def test_from_dict(self) -> None:
        """from_dict корректно парсит capabilities."""
        caps = PromptCapabilities.from_dict({
            "image": True,
            "audio": True,
            "embeddedContext": True,
        })
        assert caps.image is True
        assert caps.audio is True
        assert caps.embedded_context is True

    def test_from_dict_partial(self) -> None:
        """from_dict обрабатывает частичные данные."""
        caps = PromptCapabilities.from_dict({"image": True})
        assert caps.image is True
        assert caps.audio is False
        assert caps.embedded_context is False

    def test_from_dict_none(self) -> None:
        """from_dict обрабатывает None."""
        caps = PromptCapabilities.from_dict(None)
        assert caps.image is False
        assert caps.audio is False
        assert caps.embedded_context is False

    def test_from_server_capabilities(self) -> None:
        """from_server_capabilities извлекает promptCapabilities."""
        caps = PromptCapabilities.from_server_capabilities({
            "promptCapabilities": {
                "image": True,
                "embeddedContext": True,
            },
        })
        assert caps.image is True
        assert caps.embedded_context is True

    def test_supports_methods(self) -> None:
        """Методы supports_* работают корректно."""
        caps = PromptCapabilities(image=True, audio=False, embedded_context=True)
        assert caps.supports_image() is True
        assert caps.supports_audio() is False
        assert caps.supports_embedded_context() is True
        assert caps.supports_multimodal() is True

    def test_to_dict(self) -> None:
        """to_dict корректно сериализует."""
        caps = PromptCapabilities(image=True, audio=True, embedded_context=False)
        result = caps.to_dict()
        assert result == {
            "image": True,
            "audio": True,
            "embeddedContext": False,
        }


class TestUnsupportedContentError:
    """Тесты для UnsupportedContentError."""

    def test_error_message(self) -> None:
        """Ошибка содержит понятное сообщение."""
        caps = PromptCapabilities(image=False)
        error = UnsupportedContentError("image", caps)
        assert "image" in str(error)
        assert "promptCapabilities.image" in str(error)

    def test_error_attributes(self) -> None:
        """Ошибка содержит атрибуты."""
        caps = PromptCapabilities(audio=False)
        error = UnsupportedContentError("audio", caps)
        assert error.content_type == "audio"
        assert error.capabilities is caps


class TestContentBuilder:
    """Тесты для ContentBuilder."""

    def test_build_text_only(self) -> None:
        """Построение только текстового контента."""
        builder = ContentBuilder()
        caps = PromptCapabilities()

        blocks = builder.build_prompt_content(
            text="Hello",
            capabilities=caps,
        )

        assert len(blocks) == 1
        assert isinstance(blocks[0], TextContent)
        assert blocks[0].text == "Hello"

    def test_build_with_images_supported(self) -> None:
        """Построение с изображениями когда поддерживается."""
        builder = ContentBuilder()
        caps = PromptCapabilities(image=True)

        blocks = builder.build_prompt_content(
            text="Look at this",
            capabilities=caps,
            images=[ImageContent(data="data", mime_type="image/png")],
        )

        assert len(blocks) == 2
        assert isinstance(blocks[0], TextContent)
        assert isinstance(blocks[1], ImageContent)

    def test_build_with_images_not_supported(self) -> None:
        """Построение с изображениями когда не поддерживается."""
        builder = ContentBuilder()
        caps = PromptCapabilities(image=False)

        with pytest.raises(UnsupportedContentError) as exc_info:
            builder.build_prompt_content(
                text="Look at this",
                capabilities=caps,
                images=[ImageContent(data="data", mime_type="image/png")],
            )

        assert exc_info.value.content_type == "image"

    def test_build_with_audio_supported(self) -> None:
        """Построение с аудио когда поддерживается."""
        builder = ContentBuilder()
        caps = PromptCapabilities(audio=True)

        blocks = builder.build_prompt_content(
            text="Listen",
            capabilities=caps,
            audio=[AudioContent(data="data", mime_type="audio/wav")],
        )

        assert len(blocks) == 2
        assert isinstance(blocks[1], AudioContent)

    def test_build_with_audio_not_supported(self) -> None:
        """Построение с аудио когда не поддерживается."""
        builder = ContentBuilder()
        caps = PromptCapabilities(audio=False)

        with pytest.raises(UnsupportedContentError) as exc_info:
            builder.build_prompt_content(
                text="Listen",
                capabilities=caps,
                audio=[AudioContent(data="data", mime_type="audio/wav")],
            )

        assert exc_info.value.content_type == "audio"

    def test_build_with_resources_supported(self) -> None:
        """Построение с resources когда поддерживается."""
        builder = ContentBuilder()
        caps = PromptCapabilities(embedded_context=True)

        blocks = builder.build_prompt_content(
            text="Analyze",
            capabilities=caps,
            resources=[ResourceContent(uri="file:///code.py", text="code")],
        )

        assert len(blocks) == 2
        assert isinstance(blocks[1], ResourceContent)

    def test_build_with_resources_not_supported(self) -> None:
        """Построение с resources когда не поддерживается."""
        builder = ContentBuilder()
        caps = PromptCapabilities(embedded_context=False)

        with pytest.raises(UnsupportedContentError) as exc_info:
            builder.build_prompt_content(
                text="Analyze",
                capabilities=caps,
                resources=[ResourceContent(uri="file:///code.py", text="code")],
            )

        assert exc_info.value.content_type == "resource"

    def test_build_with_resource_links_always_supported(self) -> None:
        """Resource links поддерживаются всегда."""
        builder = ContentBuilder()
        caps = PromptCapabilities()  # Все false

        blocks = builder.build_prompt_content(
            text="Look at this",
            capabilities=caps,
            resource_links=[ResourceLinkContent(uri="file:///doc.pdf", name="doc.pdf")],
        )

        assert len(blocks) == 2
        assert isinstance(blocks[1], ResourceLinkContent)

    def test_build_multimodal(self) -> None:
        """Построение мультимодального контента."""
        builder = ContentBuilder()
        caps = PromptCapabilities(image=True, audio=True, embedded_context=True)

        blocks = builder.build_prompt_content(
            text="Analyze all",
            capabilities=caps,
            images=[ImageContent(data="img", mime_type="image/png")],
            audio=[AudioContent(data="aud", mime_type="audio/wav")],
            resources=[ResourceContent(uri="file:///code.py", text="code")],
            resource_links=[ResourceLinkContent(uri="file:///doc.pdf", name="doc")],
        )

        assert len(blocks) == 5
        types = [b.type_name for b in blocks]
        assert "text" in types
        assert "image" in types
        assert "audio" in types
        assert "resource" in types
        assert "resource_link" in types

    def test_to_dicts(self) -> None:
        """to_dicts преобразует блоки в dict."""
        builder = ContentBuilder()
        blocks = [
            TextContent(text="Hello"),
            ImageContent(data="data", mime_type="image/png"),
        ]

        result = builder.to_dicts(blocks)

        assert len(result) == 2
        assert result[0] == {"type": "text", "text": "Hello"}
        assert result[1] == {"type": "image", "data": "data", "mimeType": "image/png"}

    def test_build_empty_text(self) -> None:
        """Пустой текст не добавляется."""
        builder = ContentBuilder()
        caps = PromptCapabilities()

        blocks = builder.build_prompt_content(
            text="",
            capabilities=caps,
        )

        assert len(blocks) == 0

    def test_build_none_text(self) -> None:
        """None текст не добавляется."""
        builder = ContentBuilder()
        caps = PromptCapabilities()

        blocks = builder.build_prompt_content(
            text=None,
            capabilities=caps,
        )

        assert len(blocks) == 0

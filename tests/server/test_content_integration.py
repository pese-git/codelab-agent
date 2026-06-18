"""Integration тесты для Content типов в codelab server.

Проверяет:
- Сериализацию Content типов в JSON и обратно
- Совместимость с существующими messages (ACPMessage)
- Передачу Content через session/prompt
- Валидацию Content в prompt turn
- Работу с разными типами Content в одном сообщении
"""

import base64
import json

import pytest
from pydantic import ValidationError

from codelab.server.messages import ACPMessage
from codelab.server.protocol.content import (
    AudioContent,
    EmbeddedResourceContent,
    ImageContent,
    ResourceLinkContent,
    TextContent,
    TextResource,
)


class TestTextContentIntegration:
    """Integration тесты для TextContent."""

    def test_text_content_in_acpmessage(self) -> None:
        """Проверка TextContent в ACPMessage."""
        # Создать TextContent
        content = TextContent(text="Hello, world!")

        # Упаковать в params
        params = {
            "messages": [
                {
                    "role": "user",
                    "content": [content.model_dump(exclude_none=True)],
                }
            ]
        }

        # Создать ACPMessage
        message = ACPMessage.request("session/prompt", params, request_id="test_1")

        # Сериализовать в JSON
        json_str = message.model_dump_json()
        assert isinstance(json_str, str)

        # Десериализовать обратно
        parsed = json.loads(json_str)
        assert parsed["method"] == "session/prompt"
        assert "messages" in parsed["params"]

    def test_text_content_json_roundtrip(self) -> None:
        """Проверка сериализации TextContent в JSON и обратно."""
        original = TextContent(text="Test message")

        # Сериализовать
        data = original.model_dump(exclude_none=True)
        json_str = json.dumps(data)

        # Десериализовать
        parsed_data = json.loads(json_str)
        restored = TextContent.model_validate(parsed_data)

        assert restored.type == original.type
        assert restored.text == original.text

    def test_text_content_with_annotations_roundtrip(self) -> None:
        """Проверка TextContent с аннотациями через JSON."""
        original = TextContent(
            text="Annotated text",
            annotations={"tag": "greeting", "priority": 1},
        )

        data = original.model_dump(exclude_none=True)
        json_str = json.dumps(data)
        parsed_data = json.loads(json_str)
        restored = TextContent.model_validate(parsed_data)

        assert restored.annotations == original.annotations
        assert restored.text == original.text


class TestImageContentIntegration:
    """Integration тесты для ImageContent."""

    def test_image_content_in_acpmessage(self) -> None:
        """Проверка ImageContent в ACPMessage."""
        png_data = base64.b64encode(b"PNG_DATA").decode()
        content = ImageContent(mimeType="image/png", data=png_data)

        params = {
            "messages": [
                {
                    "role": "user",
                    "content": [content.model_dump(exclude_none=True)],
                }
            ]
        }

        message = ACPMessage.request("session/prompt", params, request_id="test_2")
        json_str = message.model_dump_json()

        parsed = json.loads(json_str)
        assert parsed["method"] == "session/prompt"
        content_item = parsed["params"]["messages"][0]["content"][0]
        assert content_item["type"] == "image"
        assert content_item["mimeType"] == "image/png"

    def test_image_content_json_roundtrip(self) -> None:
        """Проверка сериализации ImageContent в JSON и обратно."""
        jpeg_data = base64.b64encode(b"JPEG_DATA").decode()
        original = ImageContent(
            mimeType="image/jpeg",
            data=jpeg_data,
            uri="file:///test.jpg",
        )

        data = original.model_dump(exclude_none=True)
        json_str = json.dumps(data)
        parsed_data = json.loads(json_str)
        restored = ImageContent.model_validate(parsed_data)

        assert restored.type == original.type
        assert restored.mimeType == original.mimeType
        assert restored.data == original.data
        assert restored.uri == original.uri

    def test_image_content_large_base64(self) -> None:
        """Проверка ImageContent с большими base64 данными."""
        # Создать большую base64 строку
        large_data = base64.b64encode(b"X" * 10000).decode()
        original = ImageContent(mimeType="image/png", data=large_data)

        data = original.model_dump(exclude_none=True)
        json_str = json.dumps(data)
        parsed_data = json.loads(json_str)
        restored = ImageContent.model_validate(parsed_data)

        assert len(restored.data) == len(original.data)
        assert restored.data == original.data


class TestAudioContentIntegration:
    """Integration тесты для AudioContent."""

    def test_audio_content_in_acpmessage(self) -> None:
        """Проверка AudioContent в ACPMessage."""
        audio_data = base64.b64encode(b"AUDIO_DATA").decode()
        content = AudioContent(mimeType="audio/mpeg", data=audio_data)

        params = {
            "messages": [
                {
                    "role": "assistant",
                    "content": [content.model_dump(exclude_none=True)],
                }
            ]
        }

        message = ACPMessage.request("session/prompt", params, request_id="test_3")
        json_str = message.model_dump_json()

        parsed = json.loads(json_str)
        content_item = parsed["params"]["messages"][0]["content"][0]
        assert content_item["type"] == "audio"
        assert content_item["mimeType"] == "audio/mpeg"

    def test_audio_content_json_roundtrip(self) -> None:
        """Проверка сериализации AudioContent в JSON и обратно."""
        audio_data = base64.b64encode(b"WAV_DATA").decode()
        original = AudioContent(
            mimeType="audio/wav",
            data=audio_data,
        )

        data = original.model_dump(exclude_none=True)
        json_str = json.dumps(data)
        parsed_data = json.loads(json_str)
        restored = AudioContent.model_validate(parsed_data)

        assert restored.type == original.type
        assert restored.mimeType == original.mimeType
        assert restored.data == original.data


class TestResourceLinkContentIntegration:
    """Integration тесты для ResourceLinkContent."""

    def test_resource_link_content_in_acpmessage(self) -> None:
        """Проверка ResourceLinkContent в ACPMessage."""
        content = ResourceLinkContent(
            uri="file:///document.pdf",
            name="document.pdf",
        )

        params = {
            "messages": [
                {
                    "role": "user",
                    "content": [content.model_dump(exclude_none=True)],
                }
            ]
        }

        message = ACPMessage.request("session/prompt", params, request_id="test_4")
        json_str = message.model_dump_json()

        parsed = json.loads(json_str)
        content_item = parsed["params"]["messages"][0]["content"][0]
        assert content_item["type"] == "resource_link"
        assert content_item["uri"] == "file:///document.pdf"

    def test_resource_link_content_json_roundtrip(self) -> None:
        """Проверка сериализации ResourceLinkContent в JSON и обратно."""
        original = ResourceLinkContent(
            uri="http://example.com/data.csv",
            name="data.csv",
            mimeType="text/csv",
        )

        data = original.model_dump(exclude_none=True)
        json_str = json.dumps(data)
        parsed_data = json.loads(json_str)
        restored = ResourceLinkContent.model_validate(parsed_data)

        assert restored.type == original.type
        assert restored.uri == original.uri
        assert restored.name == original.name
        assert restored.mimeType == original.mimeType


class TestEmbeddedResourceContentIntegration:
    """Integration тесты для EmbeddedResourceContent."""

    def test_embedded_text_resource_in_acpmessage(self) -> None:
        """Проверка EmbeddedResourceContent с текстовым ресурсом в ACPMessage."""
        resource = TextResource(
            uri="code:///example.py",
            name="example.py",
            mimeType="text/plain",
            text="print('Hello')",
        )

        content = EmbeddedResourceContent(resource=resource)

        params = {
            "messages": [
                {
                    "role": "user",
                    "content": [content.model_dump(exclude_none=True)],
                }
            ]
        }

        message = ACPMessage.request("session/prompt", params, request_id="test_5")
        json_str = message.model_dump_json()

        parsed = json.loads(json_str)
        content_item = parsed["params"]["messages"][0]["content"][0]
        assert content_item["type"] == "resource"
        assert content_item["resource"]["uri"] == "code:///example.py"

    def test_embedded_text_resource_json_roundtrip(self) -> None:
        """Проверка EmbeddedResourceContent с текстом через JSON."""
        resource = TextResource(
            uri="code:///test.js",
            name="test.js",
            mimeType="text/javascript",
            text="console.log('test');",
        )

        original = EmbeddedResourceContent(resource=resource)

        data = original.model_dump(exclude_none=True)
        json_str = json.dumps(data)
        parsed_data = json.loads(json_str)
        restored = EmbeddedResourceContent.model_validate(parsed_data)

        assert restored.type == original.type
        assert restored.resource.uri == resource.uri
        assert restored.resource.text == resource.text


class TestMixedContentTypes:
    """Integration тесты для смешанных типов Content."""

    def test_multiple_content_types_in_message(self) -> None:
        """Проверка нескольких типов Content в одном сообщении."""
        text_content = TextContent(text="Here is an image:")
        image_data = base64.b64encode(b"IMG_DATA").decode()
        image_content = ImageContent(mimeType="image/png", data=image_data)

        contents = [
            text_content.model_dump(exclude_none=True),
            image_content.model_dump(exclude_none=True),
        ]

        params = {
            "messages": [
                {
                    "role": "user",
                    "content": contents,
                }
            ]
        }

        message = ACPMessage.request("session/prompt", params, request_id="test_6")
        json_str = message.model_dump_json()

        parsed = json.loads(json_str)
        content_list = parsed["params"]["messages"][0]["content"]
        assert len(content_list) == 2
        assert content_list[0]["type"] == "text"
        assert content_list[1]["type"] == "image"

    def test_mixed_content_json_roundtrip(self) -> None:
        """Проверка сериализации смешанного контента через JSON."""
        text = TextContent(text="Check this out:")
        audio_data = base64.b64encode(b"AUDIO").decode()
        audio = AudioContent(mimeType="audio/mpeg", data=audio_data)
        resource = ResourceLinkContent(uri="file:///doc.txt", name="doc.txt")

        contents = [
            text.model_dump(exclude_none=True),
            audio.model_dump(exclude_none=True),
            resource.model_dump(exclude_none=True),
        ]

        json_str = json.dumps(contents)
        parsed_list = json.loads(json_str)

        # Восстановить каждый элемент
        restored_text = TextContent.model_validate(parsed_list[0])
        restored_audio = AudioContent.model_validate(parsed_list[1])
        restored_resource = ResourceLinkContent.model_validate(parsed_list[2])

        assert restored_text.text == text.text
        assert restored_audio.mimeType == audio.mimeType
        assert restored_resource.uri == resource.uri

    def test_content_type_detection_in_message(self) -> None:
        """Проверка определения типов контента в сообщении."""
        contents_data = [
            TextContent(text="Message").model_dump(exclude_none=True),
            ImageContent(
                mimeType="image/jpeg",
                data=base64.b64encode(b"JPEG").decode(),
            ).model_dump(exclude_none=True),
            ResourceLinkContent(
                uri="http://example.com",
                name="example",
            ).model_dump(exclude_none=True),
        ]

        # Проверить типы по типу контента
        types = [item["type"] for item in contents_data]
        assert types == ["text", "image", "resource_link"]


class TestContentValidationInMessage:
    """Integration тесты для валидации Content в сообщениях."""

    def test_invalid_content_type_fails(self) -> None:
        """Проверка что неправильный тип контента вызывает ошибку."""
        invalid_data = {"type": "invalid", "data": "something"}

        # Пытаемся создать TextContent с неправильными данными
        with pytest.raises(ValidationError):
            TextContent.model_validate(invalid_data)

    def test_content_with_missing_required_fields(self) -> None:
        """Проверка что отсутствие обязательных полей вызывает ошибку."""
        # ImageContent без data
        invalid_image = {"type": "image", "mimeType": "image/png"}

        with pytest.raises(ValidationError):
            ImageContent.model_validate(invalid_image)

    def test_empty_content_list_in_message(self) -> None:
        """Проверка сообщения с пустым списком контента."""
        params = {
            "messages": [
                {
                    "role": "user",
                    "content": [],
                }
            ]
        }

        # Должно быть валидно (пустой список)
        message = ACPMessage.request("session/prompt", params, request_id="test_7")
        assert message.params is not None


class TestContentExportImport:
    """Integration тесты для экспорта и импорта Content."""

    def test_export_import_all_content_types(self) -> None:
        """Проверка экспорта и импорта всех типов контента."""
        all_contents = [
            (
                "text",
                TextContent(text="Text message"),
                TextContent,
            ),
            (
                "image",
                ImageContent(mimeType="image/png", data=base64.b64encode(b"PNG").decode()),
                ImageContent,
            ),
            (
                "audio",
                AudioContent(mimeType="audio/wav", data=base64.b64encode(b"WAV").decode()),
                AudioContent,
            ),
            (
                "resource_link",
                ResourceLinkContent(uri="file:///test", name="test"),
                ResourceLinkContent,
            ),
        ]

        for content_type, original, content_class in all_contents:
            # Экспортировать
            exported = original.model_dump(exclude_none=True)
            assert exported["type"] == content_type

            # Импортировать
            json_str = json.dumps(exported)
            imported_data = json.loads(json_str)
            restored = content_class.model_validate(imported_data)

            # Проверить идентичность
            assert restored.type == original.type

    def test_content_round_trip_preserves_data(self) -> None:
        """Проверка что round-trip сохраняет все данные."""
        large_text = "A" * 1000
        original = TextContent(
            text=large_text,
            annotations={"meta": {"nested": True}, "count": 42},
        )

        # Несколько round-trips
        current = original
        for _ in range(5):
            data = current.model_dump(exclude_none=True)
            json_str = json.dumps(data)
            imported = json.loads(json_str)
            current = TextContent.model_validate(imported)

        # Проверить что данные не изменились
        assert current.text == original.text
        assert current.annotations == original.annotations

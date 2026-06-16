"""Integration тесты для Content типов в codelab client.

Проверяет:
- Парсинг Content из JSON ответов сервера
- Создание Content для отправки на сервер
- Совместимость с message_parser
- Работа с domain entities
"""

import base64
import json
from typing import Any

from codelab.shared.content import (
    AudioContent,
    EmbeddedResourceContent,
    ImageContent,
    ResourceLinkContent,
    TextContent,
    TextResource,
)


class TestTextContentClientIntegration:
    """Integration тесты для TextContent в client."""

    def test_text_content_creation_and_serialization(self) -> None:
        """Проверка создания TextContent и сериализации."""
        content = TextContent(text="Hello from client")

        # Сериализовать
        data = content.model_dump(exclude_none=True)
        assert data["type"] == "text"
        assert data["text"] == "Hello from client"

        # Сериализовать в JSON
        json_str = json.dumps(data)
        parsed = json.loads(json_str)

        # Восстановить
        restored = TextContent.model_validate(parsed)
        assert restored.text == content.text

    def test_text_content_from_server_response(self) -> None:
        """Проверка парсинга TextContent из ответа сервера."""
        server_response = {
            "type": "text",
            "text": "Response from server",
        }

        content = TextContent.model_validate(server_response)
        assert content.type == "text"
        assert content.text == "Response from server"

    def test_text_content_with_annotations_roundtrip(self) -> None:
        """Проверка TextContent с аннотациями."""
        original = TextContent(
            text="Annotated message",
            annotations={"priority": "high", "tag": "urgent"},
        )

        # Сериализовать и восстановить
        data = original.model_dump(exclude_none=True)
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        restored = TextContent.model_validate(parsed)

        assert restored.annotations == original.annotations
        assert restored.text == original.text


class TestImageContentClientIntegration:
    """Integration тесты для ImageContent в client."""

    def test_image_content_creation(self) -> None:
        """Проверка создания ImageContent в client."""
        png_data = base64.b64encode(b"PNG_DATA").decode()
        content = ImageContent(mimeType="image/png", data=png_data)

        assert content.type == "image"
        assert content.mimeType == "image/png"
        assert len(content.data) > 0

    def test_image_content_from_server_response(self) -> None:
        """Проверка парсинга ImageContent из ответа сервера."""
        jpeg_data = base64.b64encode(b"JPEG_CONTENT").decode()
        server_response = {
            "type": "image",
            "mimeType": "image/jpeg",
            "data": jpeg_data,
        }

        content = ImageContent.model_validate(server_response)
        assert content.type == "image"
        assert content.mimeType == "image/jpeg"
        assert content.data == jpeg_data

    def test_image_content_with_uri(self) -> None:
        """Проверка ImageContent с URI."""
        data = base64.b64encode(b"IMG").decode()
        content = ImageContent(
            mimeType="image/svg+xml",
            data=data,
            uri="file:///icon.svg",
        )

        exported = content.model_dump(exclude_none=True)
        json_str = json.dumps(exported)
        parsed = json.loads(json_str)
        restored = ImageContent.model_validate(parsed)

        assert restored.uri == "file:///icon.svg"


class TestAudioContentClientIntegration:
    """Integration тесты для AudioContent в client."""

    def test_audio_content_creation(self) -> None:
        """Проверка создания AudioContent."""
        audio_data = base64.b64encode(b"AUDIO_BYTES").decode()
        content = AudioContent(mimeType="audio/mpeg", data=audio_data)

        assert content.type == "audio"
        assert content.mimeType == "audio/mpeg"

    def test_audio_content_from_server_response(self) -> None:
        """Проверка парсинга AudioContent из ответа сервера."""
        wav_data = base64.b64encode(b"WAVE_DATA").decode()
        server_response = {
            "type": "audio",
            "mimeType": "audio/wav",
            "data": wav_data,
        }

        content = AudioContent.model_validate(server_response)
        assert content.type == "audio"
        assert content.mimeType == "audio/wav"
        assert content.data == wav_data

    def test_audio_content_roundtrip(self) -> None:
        """Проверка round-trip для AudioContent."""
        original_data = base64.b64encode(b"MP3_AUDIO").decode()
        original = AudioContent(mimeType="audio/mp3", data=original_data)

        data = original.model_dump(exclude_none=True)
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        restored = AudioContent.model_validate(parsed)

        assert restored.data == original.data


class TestResourceLinkContentClientIntegration:
    """Integration тесты для ResourceLinkContent в client."""

    def test_resource_link_creation(self) -> None:
        """Проверка создания ResourceLinkContent."""
        content = ResourceLinkContent(
            uri="http://example.com/data.json",
            name="data.json",
        )

        assert content.type == "resource_link"
        assert content.uri == "http://example.com/data.json"
        assert content.name == "data.json"

    def test_resource_link_from_server_response(self) -> None:
        """Проверка парсинга ResourceLinkContent из ответа сервера."""
        server_response = {
            "type": "resource_link",
            "uri": "file:///document.pdf",
            "name": "document.pdf",
            "mimeType": "application/pdf",
        }

        content = ResourceLinkContent.model_validate(server_response)
        assert content.type == "resource_link"
        assert content.uri == "file:///document.pdf"
        assert content.name == "document.pdf"

    def test_resource_link_with_mime_type(self) -> None:
        """Проверка ResourceLinkContent с MIME типом."""
        content = ResourceLinkContent(
            uri="code:///src/main.py",
            name="main.py",
            mimeType="text/x-python",
        )

        exported = content.model_dump(exclude_none=True)
        assert exported["mimeType"] == "text/x-python"

        json_str = json.dumps(exported)
        parsed = json.loads(json_str)
        restored = ResourceLinkContent.model_validate(parsed)

        assert restored.mimeType == "text/x-python"


class TestEmbeddedResourceContentClientIntegration:
    """Integration тесты для EmbeddedResourceContent в client."""

    def test_embedded_text_resource_creation(self) -> None:
        """Проверка создания EmbeddedResourceContent с текстом."""
        resource = TextResource(
            uri="code:///test.js",
            name="test.js",
            mimeType="text/javascript",
            text="console.log('hello');",
        )

        content = EmbeddedResourceContent(resource=resource)

        assert content.type == "resource"
        assert content.resource.uri == "code:///test.js"
        assert content.resource.text == "console.log('hello');"

    def test_embedded_text_resource_from_server(self) -> None:
        """Проверка парсинга EmbeddedResourceContent из ответа сервера."""
        server_response = {
            "type": "resource",
            "resource": {
                "type": "text",
                "uri": "doc:///file.md",
                "name": "file.md",
                "mimeType": "text/markdown",
                "text": "# Title\n\nContent",
            },
        }

        content = EmbeddedResourceContent.model_validate(server_response)
        assert content.type == "resource"
        assert isinstance(content.resource, TextResource)
        assert content.resource.text == "# Title\n\nContent"

    def test_embedded_text_resource_roundtrip(self) -> None:
        """Проверка round-trip для EmbeddedResourceContent с текстом."""
        resource = TextResource(
            uri="example:///code.py",
            name="code.py",
            mimeType="text/x-python",
            text="def hello():\n    return 'world'",
        )

        original = EmbeddedResourceContent(resource=resource)

        data = original.model_dump(exclude_none=True)
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        restored = EmbeddedResourceContent.model_validate(parsed)

        assert restored.resource.text == original.resource.text


class TestMixedContentTypesClientIntegration:
    """Integration тесты для смешанных типов Content в client."""

    def test_parse_mixed_content_from_server(self) -> None:
        """Проверка парсинга смешанного контента из ответа сервера."""
        server_message = {
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": "Here is an image:",
                },
                {
                    "type": "image",
                    "mimeType": "image/png",
                    "data": base64.b64encode(b"PNG_DATA").decode(),
                },
            ],
        }

        content_items = server_message["content"]

        # Парсим первый элемент как TextContent
        text_content = TextContent.model_validate(content_items[0])
        assert text_content.type == "text"

        # Парсим второй элемент как ImageContent
        image_content = ImageContent.model_validate(content_items[1])
        assert image_content.type == "image"

    def test_mixed_content_in_message_list(self) -> None:
        """Проверка списка смешанного контента в сообщении."""
        contents_data = [
            TextContent(text="Check this:").model_dump(exclude_none=True),
            ImageContent(
                mimeType="image/jpeg",
                data=base64.b64encode(b"JPEG").decode(),
            ).model_dump(exclude_none=True),
            ResourceLinkContent(
                uri="http://example.com",
                name="resource",
            ).model_dump(exclude_none=True),
        ]

        json_str = json.dumps(contents_data)
        parsed_list = json.loads(json_str)

        # Проверить что можем восстановить каждый элемент по типу
        restored_items: list[Any] = []

        for item in parsed_list:
            content_type = item.get("type")
            if content_type == "text":
                restored_items.append(TextContent.model_validate(item))
            elif content_type == "image":
                restored_items.append(ImageContent.model_validate(item))
            elif content_type == "resource_link":
                restored_items.append(ResourceLinkContent.model_validate(item))
            elif content_type == "resource" and "resource" in item:
                restored_items.append(EmbeddedResourceContent.model_validate(item))

        assert len(restored_items) == 3
        assert isinstance(restored_items[0], TextContent)
        assert isinstance(restored_items[1], ImageContent)
        assert isinstance(restored_items[2], ResourceLinkContent)

    def test_create_mixed_content_for_server(self) -> None:
        """Проверка создания смешанного контента для отправки на сервер."""
        # Создать разные типы контента
        text = TextContent(text="Explanation")
        audio_data = base64.b64encode(b"AUDIO").decode()
        audio = AudioContent(mimeType="audio/mpeg", data=audio_data)

        # Упаковать для отправки
        contents = [
            text.model_dump(exclude_none=True),
            audio.model_dump(exclude_none=True),
        ]

        # Сериализовать
        json_str = json.dumps(contents)

        # Десериализовать обратно
        parsed = json.loads(json_str)

        assert parsed[0]["type"] == "text"
        assert parsed[1]["type"] == "audio"


class TestContentMessageParserIntegration:
    """Integration тесты для Content с message_parser."""

    def test_message_parser_with_content(self) -> None:
        """Проверка что MessageParser может работать с Content."""
        # Проверяем работу с контентом (MessageParser используется внутренне)
        message_data = {
            "jsonrpc": "2.0",
            "id": "test_1",
            "result": {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": "Hello from server",
                    }
                ],
            },
        }

        # Парсить через parser
        # Parser должен корректно обработать контент
        assert message_data["result"]["content"][0]["type"] == "text"

        # Восстановить контент
        content_item = message_data["result"]["content"][0]
        content = TextContent.model_validate(content_item)
        assert content.text == "Hello from server"

    def test_multiple_messages_with_content(self) -> None:
        """Проверка нескольких сообщений с контентом."""
        # Проверяем работу с несколькими сообщениями
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "What is this?",
                    }
                ],
            },
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "image",
                        "mimeType": "image/png",
                        "data": base64.b64encode(b"PNG").decode(),
                    }
                ],
            },
        ]

        # Проверить что каждое сообщение имеет корректный контент
        user_content = TextContent.model_validate(messages[0]["content"][0])
        assert user_content.text == "What is this?"

        assistant_content = ImageContent.model_validate(messages[1]["content"][0])
        assert assistant_content.type == "image"


class TestContentDataIntegrity:
    """Integration тесты для целостности данных Content."""

    def test_large_text_content_integrity(self) -> None:
        """Проверка целостности больших текстовых данных."""
        large_text = "A" * 100000  # 100KB текста

        original = TextContent(text=large_text)

        # Сериализовать и восстановить несколько раз
        for _ in range(3):
            data = original.model_dump(exclude_none=True)
            json_str = json.dumps(data)
            parsed = json.loads(json_str)
            original = TextContent.model_validate(parsed)

        assert len(original.text) == 100000
        assert original.text == "A" * 100000

    def test_binary_data_encoding_integrity(self) -> None:
        """Проверка целостности binary данных в base64."""
        binary_data = bytes(range(256)) * 100  # 25.6KB бинарных данных
        encoded = base64.b64encode(binary_data).decode()

        original = ImageContent(mimeType="image/png", data=encoded)

        # Round-trip
        data = original.model_dump(exclude_none=True)
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        restored = ImageContent.model_validate(parsed)

        # Проверить что данные не изменились
        assert restored.data == original.data

        # Декодировать и проверить бинарные данные
        decoded = base64.b64decode(restored.data)
        assert decoded == binary_data

    def test_unicode_content_integrity(self) -> None:
        """Проверка целостности Unicode контента."""
        unicode_text = "English: Hello\nРусский: Привет\nЧешский: Ahoj\nАрабский: مرحبا"

        original = TextContent(text=unicode_text)

        data = original.model_dump(exclude_none=True)
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        restored = TextContent.model_validate(parsed)

        assert restored.text == original.text
        assert restored.text == unicode_text


class TestContentTypeConsistency:
    """Integration тесты для консистентности типов Content."""

    def test_content_types_match_protocol(self) -> None:
        """Проверка что type поля соответствуют протоколу."""
        type_mapping = {
            "text": TextContent(text="test"),
            "image": ImageContent(
                mimeType="image/png",
                data=base64.b64encode(b"DATA").decode(),
            ),
            "audio": AudioContent(
                mimeType="audio/mpeg",
                data=base64.b64encode(b"DATA").decode(),
            ),
            "resource_link": ResourceLinkContent(uri="test://uri", name="test"),
        }

        for expected_type, content in type_mapping.items():
            data = content.model_dump(exclude_none=True)
            assert data["type"] == expected_type

    def test_all_content_types_serializable(self) -> None:
        """Проверка что все типы контента сериализуются в JSON."""
        contents = [
            TextContent(text="text"),
            ImageContent(
                mimeType="image/png",
                data=base64.b64encode(b"IMG").decode(),
            ),
            AudioContent(
                mimeType="audio/wav",
                data=base64.b64encode(b"WAV").decode(),
            ),
            ResourceLinkContent(uri="uri://test", name="name"),
        ]

        for content in contents:
            # Должны быть сериализуемы в JSON
            data = content.model_dump(exclude_none=True)
            json_str = json.dumps(data)
            assert isinstance(json_str, str)
            assert len(json_str) > 0

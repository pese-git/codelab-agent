"""Тесты для MessageBubble с поддержкой multimodal контента."""

from codelab.client.tui.components.message_bubble import MessageBubble, MessageRole


class TestMessageBubbleMultimodal:
    """Тесты для MessageBubble с multimodal контентом."""

    def test_create_with_content_blocks(self) -> None:
        """Проверка создания MessageBubble с content_blocks."""
        blocks = [
            {"type": "text", "text": "Hello"},
            {"type": "image", "data": "base64data", "mimeType": "image/png"},
        ]
        bubble = MessageBubble(
            role=MessageRole.USER,
            content_blocks=blocks,
        )
        assert bubble._content_blocks == blocks
        assert bubble._content == ""

    def test_create_with_text_only(self) -> None:
        """Проверка создания MessageBubble с обычным текстом."""
        bubble = MessageBubble(
            role=MessageRole.ASSISTANT,
            content="Hello world",
        )
        assert bubble._content == "Hello world"
        assert bubble._content_blocks == []

    def test_update_content_blocks(self) -> None:
        """Проверка обновления content_blocks."""
        bubble = MessageBubble(role=MessageRole.USER)
        new_blocks = [
            {"type": "text", "text": "Updated"},
            {"type": "audio", "data": "audiodata", "mimeType": "audio/wav"},
        ]
        bubble.update_content_blocks(new_blocks)
        assert bubble._content_blocks == new_blocks

    def test_from_dict_with_content_blocks(self) -> None:
        """Проверка создания из словаря с content_blocks."""
        message = {
            "role": "user",
            "content_blocks": [
                {"type": "text", "text": "Look at this"},
                {"type": "image", "data": "base64data", "mimeType": "image/png"},
            ],
        }
        bubble = MessageBubble.from_dict(message)
        assert bubble.role == MessageRole.USER
        assert len(bubble._content_blocks) == 2
        assert bubble._content == ""

    def test_from_dict_with_text_only(self) -> None:
        """Проверка создания из словаря с обычным текстом."""
        message = {
            "role": "assistant",
            "content": "Hello",
        }
        bubble = MessageBubble.from_dict(message)
        assert bubble.role == MessageRole.ASSISTANT
        assert bubble._content == "Hello"
        assert bubble._content_blocks == []

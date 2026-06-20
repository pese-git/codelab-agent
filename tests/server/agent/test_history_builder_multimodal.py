"""Тесты HistoryBuilder с мультимодальным содержимым."""

from codelab.server.agent.history_builder import HistoryBuilder


class TestHistoryBuilderMultimodal:
    """Тесты конвертации мультимодальной истории."""

    def setup_method(self) -> None:
        self.builder = HistoryBuilder()

    def test_history_with_image_returns_content_parts(self) -> None:
        history = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Look:"},
                    {"type": "image", "data": "abc", "mimeType": "image/png"},
                ],
            },
        ]
        messages = self.builder.build(history)
        assert len(messages) == 1
        msg = messages[0]
        assert isinstance(msg.content, list)
        assert len(msg.content) == 2
        assert msg.content[0].type == "text"
        assert msg.content[1].type == "image"

    def test_history_with_text_only_returns_string(self) -> None:
        history = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Hello"},
                ],
            },
        ]
        messages = self.builder.build(history)
        assert len(messages) == 1
        msg = messages[0]
        assert isinstance(msg.content, str)
        assert msg.content == "Hello"

    def test_history_with_resource_returns_text_fallback(self) -> None:
        history = [
            {
                "role": "user",
                "content": [
                    {"type": "resource", "resource": {"uri": "file:///test", "text": "content"}},
                ],
            },
        ]
        messages = self.builder.build(history)
        assert len(messages) == 1
        msg = messages[0]
        assert isinstance(msg.content, str)
        assert "file:///test" in msg.content

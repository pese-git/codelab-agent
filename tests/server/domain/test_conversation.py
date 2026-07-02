"""Unit тесты для domain conversation models."""

from datetime import datetime

from codelab.server.domain.conversation import (
    ConversationMessage,
    Image,
    MessageContent,
    Resource,
)
from codelab.server.domain.tool_call import ToolCall
from codelab.server.domain.value_objects import MessageRole


class TestResource:
    def test_create(self) -> None:
        r = Resource(uri="file:///tmp/test.py", name="test.py")
        assert r.uri == "file:///tmp/test.py"
        assert r.name == "test.py"

    def test_from_acp(self) -> None:
        block = {
            "type": "resource",
            "resource": {
                "uri": "file:///tmp/test.py",
                "name": "test.py",
                "text": "content",
                "mimeType": "text/plain",
            },
        }
        r = Resource.from_acp(block)
        assert r.uri == "file:///tmp/test.py"
        assert r.name == "test.py"
        assert r.content == "content"
        assert r.mime_type == "text/plain"

    def test_to_acp(self) -> None:
        r = Resource(uri="file:///tmp/test.py", name="test.py", content="content")
        acp = r.to_acp()
        assert acp["type"] == "resource"
        assert acp["resource"]["uri"] == "file:///tmp/test.py"
        assert acp["resource"]["name"] == "test.py"
        assert acp["resource"]["text"] == "content"


class TestImage:
    def test_create(self) -> None:
        img = Image(data="base64data", mime_type="image/png")
        assert img.data == "base64data"
        assert img.mime_type == "image/png"

    def test_from_acp(self) -> None:
        block = {"type": "image", "data": "base64data", "mimeType": "image/jpeg"}
        img = Image.from_acp(block)
        assert img.data == "base64data"
        assert img.mime_type == "image/jpeg"

    def test_from_acp_backward_compat_format(self) -> None:
        """Backward compatibility: поддерживаем старое поле 'format'."""
        block = {"type": "image", "data": "base64data", "format": "jpeg"}
        img = Image.from_acp(block)
        assert img.data == "base64data"
        assert img.mime_type == "image/jpeg"

    def test_from_acp_backward_compat_format_full_mime(self) -> None:
        """Backward compatibility: 'format' с полным MIME-типом."""
        block = {"type": "image", "data": "base64data", "format": "image/webp"}
        img = Image.from_acp(block)
        assert img.mime_type == "image/webp"

    def test_to_acp(self) -> None:
        img = Image(data="base64data", mime_type="image/png")
        acp = img.to_acp()
        assert acp == {"type": "image", "data": "base64data", "mimeType": "image/png"}


class TestMessageContent:
    def test_defaults(self) -> None:
        mc = MessageContent()
        assert mc.text == ""
        assert mc.resources == []
        assert mc.images == []

    def test_with_data(self) -> None:
        mc = MessageContent(
            text="hello",
            resources=[Resource(uri="file:///tmp")],
            images=[Image(data="data")],
        )
        assert mc.text == "hello"
        assert len(mc.resources) == 1
        assert len(mc.images) == 1


class TestConversationMessage:
    def test_create(self) -> None:
        msg = ConversationMessage(
            role=MessageRole.USER,
            content=MessageContent(text="hello"),
        )
        assert msg.role == MessageRole.USER
        assert msg.content.text == "hello"
        assert msg.tool_calls == []
        assert msg.tool_call_id is None

    def test_with_tool_calls(self) -> None:
        tc = ToolCall(id="call_1", tool_name="read_file")
        msg = ConversationMessage(
            role=MessageRole.ASSISTANT,
            content=MessageContent(),
            tool_calls=[tc],
        )
        assert len(msg.tool_calls) == 1

    def test_tool_message(self) -> None:
        msg = ConversationMessage(
            role=MessageRole.TOOL,
            content=MessageContent(text="result"),
            tool_call_id="call_1",
        )
        assert msg.role == MessageRole.TOOL
        assert msg.tool_call_id == "call_1"

    def test_timestamp(self) -> None:
        now = datetime(2024, 1, 1, 12, 0, 0)
        msg = ConversationMessage(
            role=MessageRole.USER,
            content=MessageContent(),
            timestamp=now,
        )
        assert msg.timestamp == now

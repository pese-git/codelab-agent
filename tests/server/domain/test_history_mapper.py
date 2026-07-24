"""Unit тесты для HistoryMapper."""

from datetime import datetime

from codelab.server.domain.conversation import (
    ConversationMessage,
    Image,
    MessageContent,
    Resource,
)
from codelab.server.domain.tool_call import ToolCall
from codelab.server.domain.value_objects import MessageRole
from codelab.server.mapping.history_mapper import HistoryMapper
from codelab.server.models import HistoryMessage


class TestHistoryMapperToProtocol:
    def test_text_message(self) -> None:
        domain = ConversationMessage(
            role=MessageRole.USER,
            content=MessageContent(text="hello"),
        )
        protocol = HistoryMapper.to_protocol(domain)
        assert protocol.role == "user"
        assert protocol.content is not None
        assert len(protocol.content) == 1

    def test_with_resource(self) -> None:
        domain = ConversationMessage(
            role=MessageRole.USER,
            content=MessageContent(
                text="check this",
                resources=[Resource(uri="file:///tmp/test.py", name="test.py")],
            ),
        )
        protocol = HistoryMapper.to_protocol(domain)
        assert protocol.role == "user"
        assert protocol.content is not None
        assert len(protocol.content) == 2

    def test_with_image(self) -> None:
        domain = ConversationMessage(
            role=MessageRole.USER,
            content=MessageContent(
                images=[Image(data="base64data", mime_type="image/png")],
            ),
        )
        protocol = HistoryMapper.to_protocol(domain)
        assert len(protocol.content) == 1

    def test_tool_role_preserved(self) -> None:
        """Роль TOOL сохраняется, контент — плоская строка (write-фаза D2-b, ADR-006)."""
        domain = ConversationMessage(
            role=MessageRole.TOOL,
            content=MessageContent(text="result"),
            tool_call_id="call_1",
        )
        protocol = HistoryMapper.to_protocol(domain)
        assert protocol.role == "tool"
        assert protocol.content == "result"
        assert protocol.text is None
        assert protocol.tool_call_id == "call_1"

    def test_assistant_text_slot(self) -> None:
        """Assistant-текст едет в плоский `text`-слот, `content=null` (решение №2, ADR-006)."""
        domain = ConversationMessage(
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="thinking"),
        )
        protocol = HistoryMapper.to_protocol(domain)
        assert protocol.role == "assistant"
        assert protocol.content is None
        assert protocol.text == "thinking"

    def test_embedded_tool_calls_roundtrip(self) -> None:
        """Embedded LLM tool_calls переживают round-trip через доменное поле tool_calls."""
        original = ConversationMessage(
            role=MessageRole.ASSISTANT,
            content=MessageContent(text="calling"),
            tool_calls=[ToolCall(id="c1", tool_name="grep", arguments={"q": "x"})],
        )
        protocol = HistoryMapper.to_protocol(original)
        assert protocol.model_dump()["tool_calls"] == [
            {"id": "c1", "name": "grep", "arguments": {"q": "x"}}
        ]
        restored = HistoryMapper.to_domain(protocol)
        assert len(restored.tool_calls) == 1
        assert restored.tool_calls[0].id == "c1"
        assert restored.tool_calls[0].tool_name == "grep"
        assert restored.tool_calls[0].arguments == {"q": "x"}

    def test_timestamp_serialized(self) -> None:
        ts = datetime(2024, 1, 1, 12, 0, 0)
        domain = ConversationMessage(
            role=MessageRole.USER,
            content=MessageContent(text="hello"),
            timestamp=ts,
        )
        protocol = HistoryMapper.to_protocol(domain)
        assert protocol.timestamp == "2024-01-01T12:00:00"


class TestHistoryMapperToDomain:
    def test_string_content(self) -> None:
        protocol = HistoryMessage(role="user", content="hello")
        domain = HistoryMapper.to_domain(protocol)
        assert domain.role == MessageRole.USER
        assert domain.content.text == "hello"

    def test_list_content(self) -> None:
        protocol = HistoryMessage(
            role="user",
            content=[{"type": "text", "text": "hello"}],
        )
        domain = HistoryMapper.to_domain(protocol)
        assert domain.content.text == "hello"

    def test_with_resource(self) -> None:
        protocol = HistoryMessage.model_construct(
            role="user",
            content=[
                {"type": "text", "text": "check"},
                {"type": "resource", "resource": {"uri": "file:///tmp", "name": "test"}},
            ],
        )
        domain = HistoryMapper.to_domain(protocol)
        assert domain.content.text == "check"
        assert len(domain.content.resources) == 1
        assert domain.content.resources[0].uri == "file:///tmp"

    def test_with_image(self) -> None:
        protocol = HistoryMessage(
            role="user",
            content=[{"type": "image", "data": "base64", "mimeType": "image/png"}],
        )
        domain = HistoryMapper.to_domain(protocol)
        assert len(domain.content.images) == 1
        assert domain.content.images[0].data == "base64"

    def test_unknown_role_defaults_to_user(self) -> None:
        from codelab.server.mapping.history_mapper import _parse_role

        assert _parse_role("unknown") == MessageRole.USER
        assert _parse_role("user") == MessageRole.USER
        assert _parse_role("assistant") == MessageRole.ASSISTANT
        assert _parse_role("system") == MessageRole.SYSTEM

    def test_timestamp_parsed(self) -> None:
        protocol = HistoryMessage(role="user", content="hello", timestamp="2024-01-01T12:00:00")
        domain = HistoryMapper.to_domain(protocol)
        assert domain.timestamp == datetime(2024, 1, 1, 12, 0, 0)

    def test_none_content(self) -> None:
        protocol = HistoryMessage(role="user", content=None)
        domain = HistoryMapper.to_domain(protocol)
        assert domain.content.text == ""


class TestHistoryMapperRoundTrip:
    def test_round_trip_text(self) -> None:
        original = ConversationMessage(
            role=MessageRole.USER,
            content=MessageContent(text="hello world"),
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
        )
        protocol = HistoryMapper.to_protocol(original)
        restored = HistoryMapper.to_domain(protocol)
        assert restored.role == original.role
        assert restored.content.text == original.content.text
        assert restored.timestamp == original.timestamp

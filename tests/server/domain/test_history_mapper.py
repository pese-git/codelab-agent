"""Unit тесты для HistoryMapper."""

from datetime import datetime

from codelab.server.domain.conversation import (
    ConversationMessage,
    Image,
    MessageContent,
    Resource,
)
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
                images=[Image(data="base64data", format="png")],
            ),
        )
        protocol = HistoryMapper.to_protocol(domain)
        assert len(protocol.content) == 1

    def test_tool_role_maps_to_assistant(self) -> None:
        domain = ConversationMessage(
            role=MessageRole.TOOL,
            content=MessageContent(text="result"),
            tool_call_id="call_1",
        )
        protocol = HistoryMapper.to_protocol(domain)
        assert protocol.role == "assistant"
        assert protocol.tool_call_id == "call_1"

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
            content=[{"type": "image", "data": "base64", "format": "png"}],
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

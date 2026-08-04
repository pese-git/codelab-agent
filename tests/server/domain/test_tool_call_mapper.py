"""Unit тесты для ToolCallMapper."""

import pytest

from codelab.server.domain.tool_call import ToolCall, ToolResult
from codelab.server.domain.value_objects import FileLocation, ToolCallStatus
from codelab.server.mapping.tool_call_mapper import ToolCallMapper
from codelab.server.storage.document import ToolCallState


class TestToolCallMapperToProtocol:
    def test_basic(self) -> None:
        domain = ToolCall(id="call_1", tool_name="read_file", arguments={"path": "/tmp"})
        protocol = ToolCallMapper.to_protocol(domain)
        assert protocol.tool_call_id == "call_1"
        assert protocol.title == "read_file"
        assert protocol.raw_input == {"path": "/tmp"}
        assert protocol.tool_name == "read_file"
        assert protocol.tool_arguments == {"path": "/tmp"}

    def test_with_locations(self) -> None:
        loc = FileLocation(path="/tmp/test.py", line=10)
        domain = ToolCall(id="call_1", tool_name="read_file", locations=[loc])
        protocol = ToolCallMapper.to_protocol(domain)
        assert protocol.locations == [{"path": "/tmp/test.py", "line": 10}]

    def test_with_result_raw_output(self) -> None:
        result = ToolResult(raw_output={"content": "hello", "bytes_read": 5})
        domain = ToolCall(
            id="call_1",
            tool_name="read_file",
            status=ToolCallStatus.COMPLETED,
            result=result,
        )
        protocol = ToolCallMapper.to_protocol(domain)
        assert protocol.raw_output == {"content": "hello", "bytes_read": 5}

    def test_with_raw_output_no_result(self) -> None:
        domain = ToolCall(
            id="call_1",
            tool_name="read_file",
            raw_output={"content": "hello"},
        )
        protocol = ToolCallMapper.to_protocol(domain)
        assert protocol.raw_output == {"content": "hello"}

    def test_status_mapping(self) -> None:
        domain = ToolCall(id="call_1", tool_name="read_file", status=ToolCallStatus.IN_PROGRESS)
        protocol = ToolCallMapper.to_protocol(domain)
        assert protocol.status == "in_progress"


class TestToolCallMapperToDomain:
    def test_basic(self) -> None:
        protocol = ToolCallState(
            tool_call_id="call_1",
            title="read_file",
            kind="read",
            status="pending",
            raw_input={"path": "/tmp"},
        )
        domain = ToolCallMapper.to_domain(protocol)
        assert domain.id == "call_1"
        assert domain.tool_name == "read_file"
        assert domain.arguments == {"path": "/tmp"}
        assert domain.status is ToolCallStatus.PENDING

    def test_with_locations(self) -> None:
        protocol = ToolCallState(
            tool_call_id="call_1",
            title="read_file",
            kind="read",
            status="completed",
            locations=[{"path": "/tmp/test.py", "line": 10}],
        )
        domain = ToolCallMapper.to_domain(protocol)
        assert len(domain.locations) == 1
        assert domain.locations[0].path == "/tmp/test.py"
        assert domain.locations[0].line == 10

    def test_with_raw_output(self) -> None:
        protocol = ToolCallState(
            tool_call_id="call_1",
            title="read_file",
            kind="read",
            status="completed",
            raw_output={"content": "hello"},
        )
        domain = ToolCallMapper.to_domain(protocol)
        assert domain.raw_output == {"content": "hello"}
        assert domain.result is not None
        assert domain.result.raw_output == {"content": "hello"}

    def test_unknown_status_defaults_to_pending(self) -> None:
        protocol = ToolCallState(
            tool_call_id="call_1",
            title="read_file",
            kind="read",
            status="unknown_status",
        )
        domain = ToolCallMapper.to_domain(protocol)
        assert domain.status is ToolCallStatus.PENDING

    def test_fallback_to_tool_arguments(self) -> None:
        protocol = ToolCallState(
            tool_call_id="call_1",
            title="read_file",
            kind="read",
            status="pending",
            tool_arguments={"path": "/tmp"},
        )
        domain = ToolCallMapper.to_domain(protocol)
        assert domain.arguments == {"path": "/tmp"}


class TestToolCallMapperRoundTrip:
    def test_round_trip(self) -> None:
        loc = FileLocation(path="/tmp/test.py", line=10)
        result = ToolResult(locations=[loc], raw_output={"bytes_read": 100})
        original = ToolCall(
            id="call_1",
            tool_name="read_file",
            arguments={"path": "/tmp/test.py"},
            status=ToolCallStatus.COMPLETED,
            result=result,
            locations=[loc],
            raw_output={"bytes_read": 100},
        )
        protocol = ToolCallMapper.to_protocol(original)
        restored = ToolCallMapper.to_domain(protocol)
        assert restored.id == original.id
        assert restored.tool_name == original.tool_name
        assert restored.arguments == original.arguments
        assert restored.status == original.status
        assert len(restored.locations) == 1
        assert restored.locations[0].path == "/tmp/test.py"
        assert restored.locations[0].line == 10

    @pytest.mark.parametrize(
        "wire_status",
        ["pending", "in_progress", "completed", "cancelled", "failed"],
    )
    def test_wire_status_round_trip_is_lossless(self, wire_status: str) -> None:
        """Каждый ACP-статус выживает wire → domain → wire.

        Регрессия (фаза B ADR-006): доменный enum не имел in_progress и
        cancelled, поэтому _parse_status понижал их до pending — обе стороны
        расходились молча, а покрытия на это не было.
        """
        protocol = ToolCallState(
            tool_call_id="call_1",
            title="read_file",
            kind="read",
            status=wire_status,
        )

        restored = ToolCallMapper.to_protocol(ToolCallMapper.to_domain(protocol))

        assert restored.status == wire_status

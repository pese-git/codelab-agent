"""Unit тесты для domain ToolCall и ToolResult."""

import pytest

from codelab.server.domain.tool_call import ToolCall, ToolResult
from codelab.server.domain.value_objects import FileLocation, ToolCallStatus


class TestToolResult:
    def test_defaults(self) -> None:
        result = ToolResult()
        assert result.locations == []
        assert result.raw_output == {}

    def test_with_data(self) -> None:
        loc = FileLocation(path="/tmp/test.py", line=10)
        result = ToolResult(
            locations=[loc],
            raw_output={"content": "hello"},
        )
        assert result.locations == [loc]
        assert result.raw_output == {"content": "hello"}

    def test_frozen(self) -> None:
        result = ToolResult()
        with pytest.raises(AttributeError):
            result.locations = []  # type: ignore[misc]


class TestToolCall:
    def test_defaults(self) -> None:
        tc = ToolCall(id="call_1", tool_name="read_file")
        assert tc.id == "call_1"
        assert tc.tool_name == "read_file"
        assert tc.arguments == {}
        assert tc.status is ToolCallStatus.PENDING
        assert tc.result is None
        assert tc.locations == []
        assert tc.raw_output == {}

    def test_is_terminal_pending(self) -> None:
        tc = ToolCall(id="call_1", tool_name="read_file", status=ToolCallStatus.PENDING)
        assert tc.is_terminal is False

    def test_is_terminal_running(self) -> None:
        tc = ToolCall(id="call_1", tool_name="read_file", status=ToolCallStatus.RUNNING)
        assert tc.is_terminal is False

    def test_is_terminal_completed(self) -> None:
        tc = ToolCall(id="call_1", tool_name="read_file", status=ToolCallStatus.COMPLETED)
        assert tc.is_terminal is True

    def test_is_terminal_failed(self) -> None:
        tc = ToolCall(id="call_1", tool_name="read_file", status=ToolCallStatus.FAILED)
        assert tc.is_terminal is True

    def test_with_result(self) -> None:
        result = ToolResult(raw_output={"exit_code": 0})
        tc = ToolCall(
            id="call_1",
            tool_name="terminal",
            status=ToolCallStatus.COMPLETED,
            result=result,
        )
        assert tc.result is result
        assert tc.result.raw_output == {"exit_code": 0}

    def test_with_locations(self) -> None:
        loc = FileLocation(path="/tmp/test.py", line=42)
        tc = ToolCall(id="call_1", tool_name="read_file", locations=[loc])
        assert tc.locations == [loc]

    def test_frozen(self) -> None:
        tc = ToolCall(id="call_1", tool_name="read_file")
        with pytest.raises(AttributeError):
            tc.id = "other"  # type: ignore[misc]

    def test_equality(self) -> None:
        a = ToolCall(id="call_1", tool_name="read_file")
        b = ToolCall(id="call_1", tool_name="read_file")
        assert a == b

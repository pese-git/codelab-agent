"""Unit тесты для domain value objects."""

import pytest

from codelab.server.domain.value_objects import (
    FileLocation,
    MessageRole,
    PlanPriority,
    PlanStatus,
    SessionId,
    ToolCallStatus,
)


class TestSessionId:
    def test_create(self) -> None:
        sid = SessionId("sess_123")
        assert sid == "sess_123"

    def test_is_str(self) -> None:
        sid = SessionId("sess_123")
        assert isinstance(sid, str)


class TestFileLocation:
    def test_create_with_path_only(self) -> None:
        loc = FileLocation(path="/tmp/test.py")
        assert loc.path == "/tmp/test.py"
        assert loc.line is None

    def test_create_with_path_and_line(self) -> None:
        loc = FileLocation(path="/tmp/test.py", line=42)
        assert loc.path == "/tmp/test.py"
        assert loc.line == 42

    def test_frozen(self) -> None:
        loc = FileLocation(path="/tmp/test.py")
        with pytest.raises(AttributeError):
            loc.path = "/other"  # type: ignore[misc]

    def test_empty_path_raises(self) -> None:
        with pytest.raises(ValueError, match="path must not be empty"):
            FileLocation(path="")

    def test_equality(self) -> None:
        a = FileLocation(path="/tmp/test.py", line=10)
        b = FileLocation(path="/tmp/test.py", line=10)
        assert a == b

    def test_inequality(self) -> None:
        a = FileLocation(path="/tmp/test.py", line=10)
        b = FileLocation(path="/tmp/test.py", line=20)
        assert a != b


class TestToolCallStatus:
    def test_values(self) -> None:
        assert ToolCallStatus.PENDING == "pending"
        assert ToolCallStatus.RUNNING == "running"
        assert ToolCallStatus.COMPLETED == "completed"
        assert ToolCallStatus.FAILED == "failed"

    def test_from_string(self) -> None:
        assert ToolCallStatus("pending") is ToolCallStatus.PENDING

    def test_is_str(self) -> None:
        assert isinstance(ToolCallStatus.PENDING, str)


class TestMessageRole:
    def test_values(self) -> None:
        assert MessageRole.USER == "user"
        assert MessageRole.ASSISTANT == "assistant"
        assert MessageRole.SYSTEM == "system"
        assert MessageRole.TOOL == "tool"

    def test_from_string(self) -> None:
        assert MessageRole("user") is MessageRole.USER


class TestPlanPriority:
    def test_values(self) -> None:
        assert PlanPriority.HIGH == "high"
        assert PlanPriority.MEDIUM == "medium"
        assert PlanPriority.LOW == "low"


class TestPlanStatus:
    def test_values(self) -> None:
        assert PlanStatus.PENDING == "pending"
        assert PlanStatus.IN_PROGRESS == "in_progress"
        assert PlanStatus.COMPLETED == "completed"

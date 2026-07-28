"""Unit тесты для Session агрегата и value objects."""

import pytest

from codelab.client.domain.entities import ClientCapabilities
from codelab.server.domain.conversation import ConversationMessage, MessageContent
from codelab.server.domain.plan import PlanEntry
from codelab.server.domain.session import (
    AgentPlan,
    ConversationHistory,
    MultiAgentState,
    PermissionState,
    Session,
    SessionConfig,
    ToolCallRegistry,
)
from codelab.server.domain.value_objects import (
    FileLocation,
    MessageRole,
    PlanStatus,
    SessionId,
    ToolCallStatus,
)


class TestSessionConfig:
    def test_create(self) -> None:
        config = SessionConfig(cwd="/tmp")
        assert config.cwd == "/tmp"
        assert config.config_values == {}
        assert config.active_strategy == "single"
        assert config.runtime_capabilities is None

    def test_with_capabilities(self) -> None:
        caps = ClientCapabilities(fs_read=True)
        config = SessionConfig(cwd="/tmp", runtime_capabilities=caps)
        assert config.runtime_capabilities is caps

    def test_frozen(self) -> None:
        config = SessionConfig(cwd="/tmp")
        with pytest.raises(AttributeError):
            config.cwd = "/other"  # type: ignore[misc]


class TestConversationHistory:
    def test_empty(self) -> None:
        history = ConversationHistory()
        assert history.get_messages() == []
        assert history.get_recent(5) == []

    def test_add_message(self) -> None:
        history = ConversationHistory()
        msg = ConversationMessage(
            role=MessageRole.USER,
            content=MessageContent(text="hello"),
        )
        history.add(msg)
        assert len(history.get_messages()) == 1
        assert history.get_messages()[0] == msg

    def test_get_recent(self) -> None:
        history = ConversationHistory()
        for i in range(5):
            msg = ConversationMessage(
                role=MessageRole.USER,
                content=MessageContent(text=f"msg{i}"),
            )
            history.add(msg)
        recent = history.get_recent(2)
        assert len(recent) == 2
        assert recent[0].content.text == "msg3"
        assert recent[1].content.text == "msg4"

    def test_get_recent_more_than_available(self) -> None:
        history = ConversationHistory()
        msg = ConversationMessage(
            role=MessageRole.USER,
            content=MessageContent(text="hello"),
        )
        history.add(msg)
        recent = history.get_recent(10)
        assert len(recent) == 1


class TestToolCallRegistry:
    def test_empty(self) -> None:
        registry = ToolCallRegistry()
        assert registry.get_all() == []
        assert registry.get("call_001") is None

    def test_create(self) -> None:
        registry = ToolCallRegistry()
        tc = registry.create("read_file", {"path": "/tmp"})
        assert tc.id == "call_001"
        assert tc.tool_name == "read_file"
        assert tc.arguments == {"path": "/tmp"}
        assert tc.status is ToolCallStatus.PENDING

    def test_create_multiple(self) -> None:
        registry = ToolCallRegistry()
        tc1 = registry.create("read_file", {})
        tc2 = registry.create("write_file", {})
        assert tc1.id == "call_001"
        assert tc2.id == "call_002"
        assert len(registry.get_all()) == 2

    def test_get(self) -> None:
        registry = ToolCallRegistry()
        tc = registry.create("read_file", {})
        retrieved = registry.get(tc.id)
        assert retrieved is tc

    def test_create_with_turn_fields(self) -> None:
        """create принимает поверхность turn-пути (фаза B ADR-006)."""
        registry = ToolCallRegistry()
        loc = FileLocation(path="/tmp/a.py", line=3)

        tc = registry.create(
            "fs_read_text_file",
            {"path": "/tmp/a.py"},
            title="Read text file",
            kind="read",
            tool_call_id_from_llm="chatcmpl-tool-1",
            locations=[loc],
        )

        assert (tc.title, tc.kind) == ("Read text file", "read")
        assert tc.tool_call_id_from_llm == "chatcmpl-tool-1"
        assert tc.locations == [loc]

    def test_create_defaults_kind_to_other(self) -> None:
        registry = ToolCallRegistry()
        tc = registry.create("read_file", {})
        assert tc.kind == "other"
        assert tc.title is None
        assert tc.locations == []

    def test_update(self) -> None:
        registry = ToolCallRegistry()
        tc = registry.create("read_file", {})
        registry.update(tc.id, status=ToolCallStatus.COMPLETED)
        updated = registry.get(tc.id)
        assert updated is not None
        assert updated.status is ToolCallStatus.COMPLETED

    def test_update_preserves_unlisted_fields(self) -> None:
        """Смена статуса не теряет kind/title/tool_call_id_from_llm.

        Прежняя реализация пересобирала ToolCall и молча роняла все поля, не
        перечисленные в конструкторе копии.
        """
        registry = ToolCallRegistry()
        tc = registry.create(
            "fs_read_text_file",
            {"path": "/tmp/a.py"},
            title="Read text file",
            kind="read",
            tool_call_id_from_llm="chatcmpl-tool-1",
        )

        registry.update(tc.id, status=ToolCallStatus.IN_PROGRESS)
        registry.update(tc.id, status=ToolCallStatus.COMPLETED)

        updated = registry.get(tc.id)
        assert updated is not None
        assert updated.status is ToolCallStatus.COMPLETED
        assert (updated.title, updated.kind) == ("Read text file", "read")
        assert updated.tool_call_id_from_llm == "chatcmpl-tool-1"

    def test_update_unknown_field_raises(self) -> None:
        """Опечатка в имени поля — ошибка, а не тихий пропуск."""
        registry = ToolCallRegistry()
        tc = registry.create("read_file", {})

        with pytest.raises(AttributeError, match="no field 'statuss'"):
            registry.update(tc.id, statuss=ToolCallStatus.COMPLETED)

    def test_update_absent_tool_call_is_noop(self) -> None:
        registry = ToolCallRegistry()
        registry.update("call_404", status=ToolCallStatus.COMPLETED)
        assert registry.get_all() == []


class TestPermissionState:
    def test_empty(self) -> None:
        state = PermissionState()
        assert state.is_allowed("read") is False
        assert state.is_cancelled("req_1") is False

    def test_set_policy(self) -> None:
        state = PermissionState()
        state.set_policy("read", "allow")
        assert state.is_allowed("read") is True
        assert state.is_allowed("write") is False

    def test_get_policy(self) -> None:
        state = PermissionState()
        assert state.get_policy("read") is None
        state.set_policy("read", "allow_always")
        assert state.get_policy("read") == "allow_always"

    def test_cancel_request(self) -> None:
        state = PermissionState()
        state.cancel_request("req_1")
        assert state.is_cancelled("req_1") is True
        assert state.is_cancelled("req_2") is False

    def test_uncancel_request_idempotent(self) -> None:
        state = PermissionState()
        state.cancel_request("req_1")
        state.uncancel_request("req_1")
        assert state.is_cancelled("req_1") is False
        # Идемпотентно: снятие отсутствующего запроса не падает.
        state.uncancel_request("req_absent")
        assert state.is_cancelled("req_absent") is False


class TestAgentPlan:
    def test_empty(self) -> None:
        plan = AgentPlan()
        assert plan.get_steps() == []

    def test_add_step(self) -> None:
        plan = AgentPlan()
        step = PlanEntry(content="Do something")
        plan.add_step(step)
        assert len(plan.get_steps()) == 1
        assert plan.get_steps()[0] == step

    def test_update_step(self) -> None:
        plan = AgentPlan()
        step = PlanEntry(content="Do something", status=PlanStatus.PENDING)
        plan.add_step(step)
        plan.update_step(0, "in_progress")
        assert plan.get_steps()[0].status is PlanStatus.IN_PROGRESS

    def test_update_step_invalid_index(self) -> None:
        plan = AgentPlan()
        plan.update_step(99, "completed")  # Should not raise


class TestMultiAgentState:
    def test_defaults(self) -> None:
        state = MultiAgentState()
        assert state.active_strategy == "single"
        assert state.active_agents == []
        assert state.parent_session_id is None
        assert state.child_session_ids == []
        assert state.is_child_session is False


class TestSession:
    def test_create(self) -> None:
        config = SessionConfig(cwd="/tmp")
        session = Session(id=SessionId("sess_1"), config=config)
        assert session.id == "sess_1"
        assert session.config is config
        assert session.history.get_messages() == []
        assert session.tool_calls.get_all() == []

    def test_add_message(self) -> None:
        config = SessionConfig(cwd="/tmp")
        session = Session(id=SessionId("sess_1"), config=config)
        msg = ConversationMessage(
            role=MessageRole.USER,
            content=MessageContent(text="hello"),
        )
        session.add_message(msg)
        assert len(session.history.get_messages()) == 1

    def test_create_tool_call(self) -> None:
        config = SessionConfig(cwd="/tmp")
        session = Session(id=SessionId("sess_1"), config=config)
        tc = session.create_tool_call("read_file", {"path": "/tmp"})
        assert tc.id == "call_001"
        assert tc.tool_name == "read_file"

    def test_update_tool_call(self) -> None:
        config = SessionConfig(cwd="/tmp")
        session = Session(id=SessionId("sess_1"), config=config)
        tc = session.create_tool_call("read_file", {})
        session.update_tool_call(tc.id, status=ToolCallStatus.COMPLETED)
        updated = session.tool_calls.get(tc.id)
        assert updated is not None
        assert updated.status is ToolCallStatus.COMPLETED

    def test_set_permission_policy(self) -> None:
        config = SessionConfig(cwd="/tmp")
        session = Session(id=SessionId("sess_1"), config=config)
        session.set_permission_policy("read", "allow")
        assert session.permissions.is_allowed("read") is True

    def test_get_permission_policy(self) -> None:
        """Read-seam (фаза B): чтение permission-политики через агрегат."""
        config = SessionConfig(cwd="/tmp")
        session = Session(id=SessionId("sess_1"), config=config)
        assert session.get_permission_policy("read") is None
        session.set_permission_policy("read", "allow_always")
        assert session.get_permission_policy("read") == "allow_always"

    def test_cancel_uncancel_permission_request(self) -> None:
        """Seam-делегаторы (pre-step D4-d): cancel/uncancel permission-запроса."""
        config = SessionConfig(cwd="/tmp")
        session = Session(id=SessionId("sess_1"), config=config)
        session.cancel_permission_request("req_1")
        assert session.permissions.is_cancelled("req_1") is True
        session.uncancel_permission_request("req_1")
        assert session.permissions.is_cancelled("req_1") is False

    def test_set_and_extend_available_commands(self) -> None:
        """Seam-мутаторы available_commands (pre-step D4-d)."""
        config = SessionConfig(cwd="/tmp")
        session = Session(id=SessionId("sess_1"), config=config)
        session.set_available_commands([{"name": "plan"}])
        assert session.available_commands == [{"name": "plan"}]
        session.extend_available_commands([{"name": "mode"}])
        assert session.available_commands == [{"name": "plan"}, {"name": "mode"}]

    def test_set_config_value(self) -> None:
        """Seam-мутатор config_values (pre-step D4-d)."""
        config = SessionConfig(cwd="/tmp")
        session = Session(id=SessionId("sess_1"), config=config)
        session.set_config_value("mode", "plan")
        assert session.config.config_values["mode"] == "plan"

    def test_get_config_value(self) -> None:
        """Read-seam (фаза B): чтение config_values через агрегат, с default."""
        config = SessionConfig(cwd="/tmp")
        session = Session(id=SessionId("sess_1"), config=config)
        assert session.get_config_value("mode") is None
        assert session.get_config_value("mode", "standard") == "standard"
        session.set_config_value("mode", "plan")
        assert session.get_config_value("mode", "standard") == "plan"

    def test_set_title(self) -> None:
        """Seam-мутатор title (pre-step D4-d)."""
        config = SessionConfig(cwd="/tmp")
        session = Session(id=SessionId("sess_1"), config=config)
        assert session.title is None
        session.set_title("My session")
        assert session.title == "My session"

    def test_mark_updated(self) -> None:
        """Seam-мутатор updated_at: UTC ISO 8601, явная мутация (pre-step D4-d)."""
        from datetime import UTC, datetime

        config = SessionConfig(cwd="/tmp")
        session = Session(id=SessionId("sess_1"), config=config)
        assert session.updated_at is None
        session.mark_updated()
        assert session.updated_at is not None
        parsed = datetime.fromisoformat(session.updated_at)
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == UTC.utcoffset(None)

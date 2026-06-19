"""Unit тесты для SessionMapper."""

from codelab.client.domain.entities import ClientCapabilities
from codelab.server.domain.conversation import ConversationMessage, MessageContent
from codelab.server.domain.plan import PlanEntry
from codelab.server.domain.session import (
    Session,
    SessionConfig,
)
from codelab.server.domain.value_objects import (
    MessageRole,
    PlanPriority,
    PlanStatus,
    SessionId,
    ToolCallStatus,
)
from codelab.server.mapping.session_mapper import SessionMapper
from codelab.server.protocol.state import (
    ClientRuntimeCapabilities,
    SessionState,
    ToolCallState,
)


class TestSessionMapperToProtocol:
    def test_basic_session(self) -> None:
        """Тест конвертации базовой сессии."""
        config = SessionConfig(cwd="/tmp")
        session = Session(id=SessionId("sess_1"), config=config)

        state = SessionMapper.to_protocol(session)

        assert state.session_id == "sess_1"
        assert state.cwd == "/tmp"
        assert state.config_values == {}
        assert state.history == []
        assert state.tool_calls == {}
        assert state.tool_call_counter == 0

    def test_with_history(self) -> None:
        """Тест конвертации с историей сообщений."""
        config = SessionConfig(cwd="/tmp")
        session = Session(id=SessionId("sess_1"), config=config)

        msg = ConversationMessage(
            role=MessageRole.USER,
            content=MessageContent(text="hello"),
        )
        session.add_message(msg)

        state = SessionMapper.to_protocol(session)

        assert len(state.history) == 1
        # history содержит HistoryMessage объекты
        history_msg = state.history[0]
        assert hasattr(history_msg, "role")
        assert history_msg.role == "user"
        assert history_msg.content == "hello"

    def test_with_tool_calls(self) -> None:
        """Тест конвертации с tool calls."""
        config = SessionConfig(cwd="/tmp")
        session = Session(id=SessionId("sess_1"), config=config)

        tc = session.create_tool_call("read_file", {"path": "/tmp"})
        session.update_tool_call(tc.id, status=ToolCallStatus.COMPLETED)

        state = SessionMapper.to_protocol(session)

        assert len(state.tool_calls) == 1
        assert "call_001" in state.tool_calls
        tc_state = state.tool_calls["call_001"]
        assert tc_state.tool_call_id == "call_001"
        assert tc_state.tool_name == "read_file"
        assert tc_state.status == "completed"
        assert state.tool_call_counter == 1

    def test_with_permissions(self) -> None:
        """Тест конвертации с разрешениями."""
        config = SessionConfig(cwd="/tmp")
        session = Session(id=SessionId("sess_1"), config=config)

        session.set_permission_policy("read", "allow")
        session.permissions.cancel_request("req_1")

        state = SessionMapper.to_protocol(session)

        assert state.permission_policy == {"read": "allow"}
        assert "req_1" in state.cancelled_permission_requests

    def test_with_plan(self) -> None:
        """Тест конвертации с планом."""
        config = SessionConfig(cwd="/tmp")
        session = Session(id=SessionId("sess_1"), config=config)

        step = PlanEntry(content="Do something", priority=PlanPriority.HIGH)
        session.plan.add_step(step)

        state = SessionMapper.to_protocol(session)

        assert len(state.latest_plan) == 1
        assert state.latest_plan[0]["content"] == "Do something"
        assert state.latest_plan[0]["priority"] == "high"
        assert state.latest_plan[0]["status"] == "pending"

    def test_with_runtime_capabilities(self) -> None:
        """Тест конвертации с runtime capabilities."""
        caps = ClientCapabilities(fs_read=True, fs_write=False, terminal=True)
        config = SessionConfig(cwd="/tmp", runtime_capabilities=caps)
        session = Session(id=SessionId("sess_1"), config=config)

        state = SessionMapper.to_protocol(session)

        assert state.runtime_capabilities is not None
        assert state.runtime_capabilities.fs_read is True
        assert state.runtime_capabilities.fs_write is False
        assert state.runtime_capabilities.terminal is True

    def test_with_multi_agent(self) -> None:
        """Тест конвертации с multi-agent состоянием."""
        config = SessionConfig(cwd="/tmp")
        session = Session(id=SessionId("sess_1"), config=config)
        session.multi_agent.active_strategy = "hierarchical"
        session.multi_agent.active_agents = ["agent1", "agent2"]
        session.multi_agent.parent_session_id = "parent_sess"
        session.multi_agent.child_session_ids = ["child1"]
        session.multi_agent.is_child_session = False

        state = SessionMapper.to_protocol(session)

        assert state.active_strategy == "hierarchical"
        assert state.active_agents == ["agent1", "agent2"]
        assert state.parent_session_id == "parent_sess"
        assert state.child_session_ids == ["child1"]
        assert state.is_child_session is False


class TestSessionMapperToDomain:
    def test_basic_session(self) -> None:
        """Тест конвертации базовой сессии."""
        state = SessionState(
            session_id="sess_1",
            cwd="/tmp",
        )

        session = SessionMapper.to_domain(state)

        assert session.id == "sess_1"
        assert session.config.cwd == "/tmp"
        assert session.config.config_values == {}
        assert session.history.get_messages() == []
        assert session.tool_calls.get_all() == []

    def test_with_history(self) -> None:
        """Тест конвертации с историей сообщений."""
        state = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            history=[{"role": "user", "content": "hello"}],
        )

        session = SessionMapper.to_domain(state)

        messages = session.history.get_messages()
        assert len(messages) == 1
        assert messages[0].role == MessageRole.USER
        assert messages[0].content.text == "hello"

    def test_with_tool_calls(self) -> None:
        """Тест конвертации с tool calls."""
        state = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            tool_call_counter=1,
            tool_calls={
                "call_001": ToolCallState(
                    tool_call_id="call_001",
                    title="read_file",
                    kind="other",
                    status="completed",
                    tool_name="read_file",
                    tool_arguments={"path": "/tmp"},
                )
            },
        )

        session = SessionMapper.to_domain(state)

        assert session.tool_calls.counter == 1
        tc = session.tool_calls.get("call_001")
        assert tc is not None
        assert tc.id == "call_001"
        assert tc.tool_name == "read_file"
        assert tc.status == ToolCallStatus.COMPLETED
        assert tc.arguments == {"path": "/tmp"}

    def test_with_permissions(self) -> None:
        """Тест конвертации с разрешениями."""
        state = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            permission_policy={"read": "allow"},
            cancelled_permission_requests={"req_1"},
        )

        session = SessionMapper.to_domain(state)

        assert session.permissions.policy == {"read": "allow"}
        assert session.permissions.is_allowed("read") is True
        assert session.permissions.is_cancelled("req_1") is True

    def test_with_plan(self) -> None:
        """Тест конвертации с планом."""
        state = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            latest_plan=[
                {
                    "content": "Do something",
                    "priority": "high",
                    "status": "in_progress",
                }
            ],
        )

        session = SessionMapper.to_domain(state)

        steps = session.plan.get_steps()
        assert len(steps) == 1
        assert steps[0].content == "Do something"
        assert steps[0].priority == PlanPriority.HIGH
        assert steps[0].status == PlanStatus.IN_PROGRESS

    def test_with_runtime_capabilities(self) -> None:
        """Тест конвертации с runtime capabilities."""
        state = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            runtime_capabilities=ClientRuntimeCapabilities(
                fs_read=True,
                fs_write=False,
                terminal=True,
            ),
        )

        session = SessionMapper.to_domain(state)

        assert session.config.runtime_capabilities is not None
        assert session.config.runtime_capabilities.fs_read is True
        assert session.config.runtime_capabilities.fs_write is False
        assert session.config.runtime_capabilities.terminal is True

    def test_with_multi_agent(self) -> None:
        """Тест конвертации с multi-agent состоянием."""
        state = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            active_strategy="hierarchical",
            active_agents=["agent1", "agent2"],
            parent_session_id="parent_sess",
            child_session_ids=["child1"],
            is_child_session=False,
        )

        session = SessionMapper.to_domain(state)

        assert session.multi_agent.active_strategy == "hierarchical"
        assert session.multi_agent.active_agents == ["agent1", "agent2"]
        assert session.multi_agent.parent_session_id == "parent_sess"
        assert session.multi_agent.child_session_ids == ["child1"]
        assert session.multi_agent.is_child_session is False


class TestSessionMapperRoundTrip:
    def test_round_trip(self) -> None:
        """Тест обратимости конвертации."""
        # Создаем domain Session
        caps = ClientCapabilities(fs_read=True, terminal=True)
        config = SessionConfig(
            cwd="/tmp",
            config_values={"mode": "normal"},
            runtime_capabilities=caps,
        )
        session = Session(id=SessionId("sess_1"), config=config)

        # Добавляем данные
        msg = ConversationMessage(
            role=MessageRole.USER,
            content=MessageContent(text="hello"),
        )
        session.add_message(msg)

        tc = session.create_tool_call("read_file", {"path": "/tmp"})
        session.update_tool_call(tc.id, status=ToolCallStatus.COMPLETED)

        session.set_permission_policy("read", "allow")

        step = PlanEntry(content="Do something", priority=PlanPriority.HIGH)
        session.plan.add_step(step)

        session.multi_agent.active_strategy = "hierarchical"
        session.multi_agent.active_agents = ["agent1"]

        # Конвертируем в protocol
        state = SessionMapper.to_protocol(session)

        # Конвертируем обратно в domain
        restored = SessionMapper.to_domain(state)

        # Проверяем основные поля
        assert restored.id == session.id
        assert restored.config.cwd == session.config.cwd
        assert restored.config.config_values == session.config.config_values

        # Проверяем историю
        assert len(restored.history.get_messages()) == len(session.history.get_messages())

        # Проверяем tool calls
        assert restored.tool_calls.counter == session.tool_calls.counter
        assert len(restored.tool_calls.get_all()) == len(session.tool_calls.get_all())

        # Проверяем разрешения
        assert restored.permissions.policy == session.permissions.policy

        # Проверяем план
        assert len(restored.plan.get_steps()) == len(session.plan.get_steps())

        # Проверяем multi-agent
        assert restored.multi_agent.active_strategy == session.multi_agent.active_strategy
        assert restored.multi_agent.active_agents == session.multi_agent.active_agents

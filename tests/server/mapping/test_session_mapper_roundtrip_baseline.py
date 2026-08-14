"""Round-trip baseline `SessionMapper` (write-фаза, гейт D0.2).

Фиксирует ТЕКУЩЕЕ поведение round-trip `domain.Session → SessionDocument → domain.Session`
ДО доменной миграции (ADR-006), включая известные ПОТЕРИ. Это baseline: фаза D1
(SessionMapper без потерь) будет флипать помеченные `BASELINE LOSS` ассерты на
сохранение. Пока они документируют, что именно теряется.
"""

from codelab.server.domain.conversation import (
    ConversationMessage,
    MessageContent,
)
from codelab.server.domain.journal import (
    JournalEntry,
    RequestedToolCall,
    UserMessageRecorded,
)
from codelab.server.domain.plan import PlanEntry
from codelab.server.domain.session import (
    ConversationHistory,
    MultiAgentState,
    PendingExternalRequest,
    PermissionState,
    Session,
    SessionConfig,
    SessionRuntime,
    ToolCallRegistry,
    TurnState,
)
from codelab.server.domain.value_objects import (
    AwaitingPermission,
    MessageRole,
    PlanPriority,
    PlanStatus,
    SessionId,
)
from codelab.server.mapping.journal_mapper import JournalMapper
from codelab.server.mapping.session_mapper import SessionMapper
from codelab.server.protocol.handlers.event_history_writer import EventHistoryWriter
from codelab.server.storage.document import CURRENT_SCHEMA_VERSION


def _rich_session() -> Session:
    history = ConversationHistory()
    history.add(ConversationMessage(role=MessageRole.USER, content=MessageContent.from_text("hi")))
    history.add(
        ConversationMessage(role=MessageRole.ASSISTANT, content=MessageContent.from_text("hello"))
    )
    history.add(
        ConversationMessage(
            role=MessageRole.TOOL,
            content=MessageContent.from_text("tool result"),
            tool_call_id="call_001",
        )
    )

    tool_calls = ToolCallRegistry()
    tool_calls.create("grep", {"q": "x"})

    session = Session(
        id=SessionId("sess_rt"),
        config=SessionConfig(cwd="/tmp/proj", config_values={"model": "m", "_agent": "a"}),
        history=history,
        tool_calls=tool_calls,
    )

    # Журнал заполняется настоящим писателем, как в продакшене: с шага 4f ADR-008
    # разговор переживает хранилище **через журнал**, а не через коллекцию
    # `history` — она перестала персистироваться. Фикстура, писавшая только
    # историю, проверяла бы round-trip мимо источника.
    writer = EventHistoryWriter()
    writer.save_user_message(session, [{"type": "text", "text": "hi"}])
    writer.save_agent_message(session, {"type": "text", "text": "hello"})
    writer.save_tool_call_answer(session, "call_001", "tool result")
    session.plan.add_step(
        PlanEntry(content="step 1", priority=PlanPriority.HIGH, status=PlanStatus.PENDING)
    )
    return session


def _roundtrip(session: Session) -> Session:
    return SessionMapper.to_domain(SessionMapper.to_protocol(session))


class TestRoundtripPreserved:
    """Что сохраняется сейчас (не должно регрессировать в D1)."""

    def test_identity_and_config(self) -> None:
        rt = _roundtrip(_rich_session())
        assert str(rt.id) == "sess_rt"
        assert rt.config.cwd == "/tmp/proj"
        assert rt.config.config_values == {"model": "m", "_agent": "a"}

    def test_plan_preserved(self) -> None:
        rt = _roundtrip(_rich_session())
        steps = rt.plan.get_steps()
        assert len(steps) == 1
        assert steps[0].content == "step 1"
        assert steps[0].priority == PlanPriority.HIGH
        assert steps[0].status == PlanStatus.PENDING

    def test_tool_calls_preserved(self) -> None:
        rt = _roundtrip(_rich_session())
        calls = rt.tool_calls.get_all()
        assert len(calls) == 1
        assert calls[0].id == "call_001"
        assert calls[0].tool_name == "grep"
        assert calls[0].arguments == {"q": "x"}

    def test_user_assistant_text_preserved(self) -> None:
        rt = _roundtrip(_rich_session())
        msgs = rt.history.get_messages()
        assert msgs[0].role == MessageRole.USER
        assert msgs[0].content.text == "hi"
        assert msgs[1].role == MessageRole.ASSISTANT
        assert msgs[1].content.text == "hello"


class TestRoundtripLossless:
    """D1: round-trip без потерь — роль TOOL и tool_call_id сохраняются."""

    def test_tool_role_preserved(self) -> None:
        """Роль TOOL переживает round-trip (не схлопывается в ASSISTANT)."""
        rt = _roundtrip(_rich_session())
        tool_msg = rt.history.get_messages()[2]
        assert tool_msg.content.text == "tool result"
        assert tool_msg.role == MessageRole.TOOL

    def test_tool_call_id_preserved(self) -> None:
        """tool_call_id сообщения истории переживает round-trip."""
        rt = _roundtrip(_rich_session())
        tool_msg = rt.history.get_messages()[2]
        assert tool_msg.tool_call_id == "call_001"

    def test_permissions_preserved(self) -> None:
        session = _rich_session()
        session.permissions = PermissionState(
            policy={"fs/read": "allow"}, cancelled_requests={"r1"}
        )
        rt = _roundtrip(session)
        assert rt.permissions.policy == {"fs/read": "allow"}
        assert rt.permissions.cancelled_requests == {"r1"}

    def test_numeric_request_ids_keep_type(self) -> None:
        """JSON-RPC id может быть числом — тип не коэрцится в str (D4-d1, ADR-006).

        Коэрция ломала корреляцию tombstone'ов: поиск по int 7 не находил "7".
        """
        session = _rich_session()
        session.permissions = PermissionState(policy={}, cancelled_requests={7, "r1"})
        rt = _roundtrip(session)
        assert rt.permissions.cancelled_requests == {7, "r1"}
        assert rt.permissions.is_cancelled(7) is True

    def test_multi_agent_preserved(self) -> None:
        session = _rich_session()
        session.multi_agent = MultiAgentState(
            active_strategy="single",
            active_agents=["a"],
            parent_session_id="p",
            child_session_ids=["c"],
            is_child_session=True,
        )
        rt = _roundtrip(session)
        assert rt.multi_agent.active_agents == ["a"]
        assert rt.multi_agent.parent_session_id == "p"
        assert rt.multi_agent.child_session_ids == ["c"]
        assert rt.multi_agent.is_child_session is True


class TestRoundtripTurnAndRuntime:
    """D4-a: turn/runtime состояние как доменные VO — round-trip без потерь (ADR-006)."""

    def test_active_turn_preserved(self) -> None:
        session = _rich_session()
        session.active_turn = TurnState(
            session_id="sess_rt",
            prompt_request_id="req_1",
            cancel_requested=True,
            phase=AwaitingPermission.of(request_id=7, tool_call_id="call_001"),
            pending_external_request=PendingExternalRequest(
                request_id="rpc_1",
                kind="fs_read",
                tool_call_id="call_001",
                path="/tmp/README.md",
            ),
        )
        rt = _roundtrip(session)
        assert rt.active_turn is not None
        assert rt.active_turn.session_id == "sess_rt"
        assert rt.active_turn.prompt_request_id == "req_1"
        assert rt.active_turn.cancel_requested is True
        # Идентификаторы — выводимые из фазы (ADR-008, шаг 2), поэтому round-trip
        # обязан сохранить именно значение фазы, а не три плоских поля.
        assert rt.active_turn.permission_request_id == 7
        assert rt.active_turn.permission_tool_call_id == "call_001"
        assert rt.active_turn.phase == AwaitingPermission.of(request_id=7, tool_call_id="call_001")
        # Прежнее имя `waiting_permission` читается, но перезаписывается каноничным
        # `awaiting_permission`: одно состояние больше не имеет трёх написаний.
        assert rt.active_turn.phase.wire_name == "awaiting_permission"
        assert rt.active_turn.pending_external_request is not None
        assert rt.active_turn.pending_external_request.path == "/tmp/README.md"

    def test_pending_external_request_fully_preserved(self) -> None:
        """Все поля снимка ожидаемого запроса выживают round-trip.

        Фаза B: dict заменён типизированным PendingExternalRequest, поэтому
        сверяем объект целиком — иначе новое поле снова можно потерять молча.
        """
        session = _rich_session()
        pending = PendingExternalRequest(
            request_id=42,
            kind="terminal_create",
            tool_call_id="call_007",
            path="ls -la",
            expected_new_text="text",
            terminal_id="term_1",
            terminal_output="total 0",
            terminal_exit_code=0,
            terminal_signal="SIGTERM",
            terminal_truncated=False,
        )
        session.active_turn = TurnState(session_id="sess_rt", pending_external_request=pending)

        rt = _roundtrip(session)

        assert rt.active_turn is not None
        assert rt.active_turn.pending_external_request == pending

    def test_no_active_turn_preserved(self) -> None:
        rt = _roundtrip(_rich_session())
        assert rt.active_turn is None

    def test_runtime_preserved(self) -> None:
        session = _rich_session()
        session.runtime = SessionRuntime(
            events_history=[{"type": "session_update", "n": 1}],
            cancelled_client_rpc_requests={"rpc_1", 42},
            pending_prompt_response={"request_id": "p1"},
            correlation_id="corr_1",
        )
        rt = _roundtrip(session)
        assert rt.runtime.events_history == [{"type": "session_update", "n": 1}]
        assert rt.runtime.cancelled_client_rpc_requests == {"rpc_1", 42}
        assert rt.runtime.pending_prompt_response == {"request_id": "p1"}
        assert rt.runtime.correlation_id == "corr_1"


class TestRoundtripToolCallFields:
    """D4-b/b3: tool_call wire-поля (kind/title/content/...) — round-trip без потерь (ADR-006)."""

    def test_tool_call_rich_fields_preserved(self) -> None:
        from codelab.server.domain.tool_call import ToolCall, ToolResult
        from codelab.server.domain.value_objects import FileLocation, ToolCallStatus

        session = _rich_session()
        session.tool_calls.calls["call_001"] = ToolCall(
            id="call_001",
            tool_name="read_file",
            arguments={"path": "/a.py"},
            status=ToolCallStatus.COMPLETED,
            kind="read",
            title="Reading /a.py",
            tool_call_id_from_llm="chatcmpl-xyz",
            result=ToolResult(
                locations=[FileLocation(path="/a.py", line=10)],
                raw_output={"bytes": 42},
                content=[{"type": "text", "text": "file body"}],
            ),
        )
        rt = _roundtrip(session)
        tc = rt.tool_calls.get("call_001")
        assert tc is not None
        assert tc.kind == "read"
        assert tc.title == "Reading /a.py"
        assert tc.tool_call_id_from_llm == "chatcmpl-xyz"
        assert tc.status == ToolCallStatus.COMPLETED
        assert tc.arguments == {"path": "/a.py"}
        assert tc.result is not None
        assert tc.result.content == [{"type": "text", "text": "file body"}]
        assert tc.result.raw_output == {"bytes": 42}
        assert [(loc.path, loc.line) for loc in tc.result.locations] == [("/a.py", 10)]


class TestRoundtripPrepFields:
    """D4-prep: поля punch-list на домене — round-trip domain→SessionDocument→domain (ADR-006)."""

    def test_storage_meta_preserved(self) -> None:
        session = _rich_session()
        object.__setattr__(session, "title", "My session")
        object.__setattr__(session, "updated_at", "2026-07-24T09:22:50.227038+00:00")
        object.__setattr__(session, "schema_version", 9)
        rt = _roundtrip(session)
        assert rt.title == "My session"
        assert rt.updated_at == "2026-07-24T09:22:50.227038+00:00"
        assert rt.schema_version == CURRENT_SCHEMA_VERSION
        # Ревизия документа несётся round-trip как есть: её инкрементирует хранилище
        # при записи, маппер не должен её ни терять, ни менять (ADR-007)
        assert rt.revision == session.revision

    def test_older_schema_version_is_migrated_not_carried(self) -> None:
        """Версия схемы — не «мета как есть»: устаревшая поднимается миграцией.

        Отличие от `title`/`updated_at` намеренное: они несутся round-trip без правок,
        а `schema_version` описывает форму документа, и round-trip через
        `SessionDocument` эту форму приводит к текущей.
        """
        session = _rich_session()
        object.__setattr__(session, "schema_version", 8)

        assert _roundtrip(session).schema_version == CURRENT_SCHEMA_VERSION

    def test_updated_at_not_regenerated(self) -> None:
        """`updated_at` несётся как есть, не подменяется свежим временем."""
        session = _rich_session()
        object.__setattr__(session, "updated_at", "2020-01-01T00:00:00+00:00")
        rt = _roundtrip(session)
        assert rt.updated_at == "2020-01-01T00:00:00+00:00"

    def test_mcp_servers_preserved(self) -> None:
        session = _rich_session()
        object.__setattr__(
            session.config, "mcp_servers", [{"name": "fs", "command": "srv", "args": ["--x"]}]
        )
        rt = _roundtrip(session)
        assert rt.config.mcp_servers == [{"name": "fs", "command": "srv", "args": ["--x"]}]

    def test_available_commands_preserved(self) -> None:
        session = _rich_session()
        object.__setattr__(
            session, "available_commands", [{"name": "plan", "description": "d", "input": None}]
        )
        rt = _roundtrip(session)
        assert rt.available_commands == [{"name": "plan", "description": "d", "input": None}]

    def test_multi_agent_opaque_preserved(self) -> None:
        session = _rich_session()
        session.multi_agent = MultiAgentState(task_result="done", sliced_summary="summary")
        rt = _roundtrip(session)
        assert rt.multi_agent.task_result == "done"
        assert rt.multi_agent.sliced_summary == "summary"

    def test_history_timestamp_none_preserved(self) -> None:
        """`None` остаётся `None` и не синтезируется — ACP updatedAt-семантика.

        С шага 4f метку времени сообщения несёт **журнал**: история выводится из
        него, поэтому запись без метки обязана дать сообщение без метки. Прежде
        метка лежала в самой записи истории; инвариант тот же, источник другой.
        """
        session = Session(id=SessionId("s"), config=SessionConfig(cwd="/t"))
        record = JournalMapper.to_wire(
            JournalEntry(UserMessageRecorded(blocks=[{"type": "text", "text": "a"}]))
        )
        session.runtime.events_history.append(record)

        rt = _roundtrip(session)

        assert "at" not in record
        assert rt.history.get_messages()[0].timestamp is None


class TestProtocolRoundtripLossless:
    """Гейт D4-prep: `SessionDocument → domain → SessionDocument` без потерь по punch-list.

    Критичное для D4-d направление: SessionDocument пересобирается из домена на границе.
    Инвариант реальных данных: `raw_input == tool_arguments` (проверено на дампе сессии).
    """

    @staticmethod
    def _sample_state() -> "object":
        from codelab.server.models import HistoryMessage
        from codelab.server.storage.document import (
            SessionDocument,
            ToolCallState,
        )

        return SessionDocument(
            session_id="sess_rt",
            schema_version=8,
            cwd="/tmp/proj",
            mcp_servers=[{"name": "fs", "command": "srv"}],
            title="My session",
            updated_at="2026-07-24T09:22:50.227038+00:00",
            config_values={"model": "m"},
            history=[
                HistoryMessage(
                    role="user", content="hi", timestamp="2026-07-24T09:22:50.227038+00:00"
                ),
                HistoryMessage(role="assistant", content="ok", timestamp=None),
            ],
            tool_calls={
                "call_001": ToolCallState(
                    tool_call_id="call_001",
                    title="grep",
                    kind="execute",
                    status="completed",
                    tool_name="grep",
                    tool_arguments={"q": "x"},
                    raw_input={"q": "x"},
                )
            },
            tool_call_counter=1,
            available_commands=[{"name": "plan", "description": "d", "input": None}],
            task_result="done",
            sliced_summary="summary",
        )

    def test_protocol_roundtrip_lossless(self) -> None:
        state0 = self._sample_state()
        rt = SessionMapper.to_protocol(SessionMapper.to_domain(state0))

        d0 = state0.model_dump()
        d1 = rt.model_dump()
        for field_name in (
            "schema_version",
            "mcp_servers",
            "title",
            "updated_at",
            "available_commands",
            "task_result",
            "sliced_summary",
        ):
            assert d0[field_name] == d1[field_name], field_name

        assert [m["timestamp"] for m in d0["history"]] == [m["timestamp"] for m in d1["history"]]
        assert (
            d0["tool_calls"]["call_001"]["raw_input"] == (d1["tool_calls"]["call_001"]["raw_input"])
        )

    def test_history_body_roundtrip_lossless(self) -> None:
        """Гейт D2-c: тело history-сообщений байт-идентично после round-trip.

        Покрывает все реальные wire-формы: assistant (`text`-слот + embedded tool_calls),
        tool (строковый `content`), user (блочный `content`, в т.ч. image).
        """
        from codelab.server.models import HistoryMessage
        from codelab.server.storage.document import SessionDocument

        state0 = SessionDocument(
            session_id="sess_hist",
            schema_version=8,
            cwd="/t",
            history=[
                HistoryMessage(
                    role="user",
                    content=[{"type": "text", "text": "проанализируй"}],
                    timestamp="2026-07-24T10:18:06.840223+00:00",
                ),
                HistoryMessage(
                    role="assistant",
                    content=None,
                    text="Сначала план.",
                    timestamp="2026-07-24T10:18:17.495647+00:00",
                    tool_calls=[
                        {"id": "chatcmpl-tool-1", "name": "update_plan", "arguments": {"e": [1]}}
                    ],
                ),
                HistoryMessage(
                    role="tool",
                    content="tool output",
                    tool_call_id="chatcmpl-tool-1",
                    timestamp=None,
                ),
                HistoryMessage(
                    role="user",
                    content=[{"type": "image", "data": "B64", "mimeType": "image/png"}],
                ),
            ],
        )
        rt = SessionMapper.to_protocol(SessionMapper.to_domain(state0))
        assert rt.model_dump()["history"] == state0.model_dump()["history"]


class TestRoundtripHistoryBody:
    """D2-b: тело history-сообщения round-trip без потерь (делегирование HistoryMapper, ADR-006)."""

    def test_multimodal_history_preserved(self) -> None:
        """Мультимодальный контент истории (images) переживает round-trip."""
        session = Session(id=SessionId("s"), config=SessionConfig(cwd="/t"))
        EventHistoryWriter().save_user_message(
            session,
            [
                {"type": "text", "text": "see"},
                {"type": "image", "data": "B64", "mimeType": "image/png"},
            ],
        )

        rt = _roundtrip(session)
        msg = rt.history.get_messages()[0]
        assert msg.content.text == "see"
        assert len(msg.content.images) == 1
        assert msg.content.images[0].data == "B64"

    def test_assistant_text_and_tool_calls_preserved(self) -> None:
        """Плоский assistant-текст и embedded LLM tool_calls переживают round-trip."""
        session = Session(id=SessionId("s"), config=SessionConfig(cwd="/t"))
        EventHistoryWriter().save_agent_message(
            session,
            {"type": "text", "text": "plan"},
            tool_calls=[RequestedToolCall(id="c1", name="update_plan", arguments={"e": 1})],
        )

        rt = _roundtrip(session)
        msg = rt.history.get_messages()[0]
        assert msg.role == MessageRole.ASSISTANT
        assert msg.content.text == "plan"
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].tool_name == "update_plan"
        assert msg.tool_calls[0].arguments == {"e": 1}

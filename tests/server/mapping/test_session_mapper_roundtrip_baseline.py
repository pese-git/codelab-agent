"""Round-trip baseline `SessionMapper` (write-фаза, гейт D0.2).

Фиксирует ТЕКУЩЕЕ поведение round-trip `domain.Session → SessionState → domain.Session`
ДО доменной миграции (ADR-006), включая известные ПОТЕРИ. Это baseline: фаза D1
(SessionMapper без потерь) будет флипать помеченные `BASELINE LOSS` ассерты на
сохранение. Пока они документируют, что именно теряется.
"""

from codelab.server.domain.conversation import ConversationMessage, MessageContent
from codelab.server.domain.plan import PlanEntry
from codelab.server.domain.session import (
    ConversationHistory,
    Session,
    SessionConfig,
    ToolCallRegistry,
)
from codelab.server.domain.value_objects import (
    MessageRole,
    PlanPriority,
    PlanStatus,
    SessionId,
)
from codelab.server.mapping.session_mapper import SessionMapper


def _rich_session() -> Session:
    history = ConversationHistory()
    history.add(ConversationMessage(role=MessageRole.USER, content=MessageContent(text="hi")))
    history.add(
        ConversationMessage(role=MessageRole.ASSISTANT, content=MessageContent(text="hello"))
    )
    history.add(
        ConversationMessage(
            role=MessageRole.TOOL,
            content=MessageContent(text="tool result"),
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


class TestRoundtripBaselineLosses:
    """ПОТЕРИ текущего SessionMapper — цель фазы D1 (флипнуть на сохранение)."""

    def test_tool_role_collapses_to_assistant(self) -> None:
        """BASELINE LOSS: роль TOOL схлопывается в ASSISTANT (to_protocol)."""
        rt = _roundtrip(_rich_session())
        tool_msg = rt.history.get_messages()[2]
        # Текст сохраняется, но роль потеряна (стала assistant).
        assert tool_msg.content.text == "tool result"
        assert tool_msg.role == MessageRole.ASSISTANT  # D1: должно стать MessageRole.TOOL

    def test_tool_call_id_lost_on_history(self) -> None:
        """BASELINE LOSS: tool_call_id сообщения истории не переживает round-trip."""
        rt = _roundtrip(_rich_session())
        tool_msg = rt.history.get_messages()[2]
        assert tool_msg.tool_call_id is None  # D1: должно стать "call_001"

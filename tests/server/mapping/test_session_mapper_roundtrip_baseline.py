"""Round-trip baseline `SessionMapper` (write-фаза, гейт D0.2).

Фиксирует ТЕКУЩЕЕ поведение round-trip `domain.Session → SessionState → domain.Session`
ДО доменной миграции (ADR-006), включая известные ПОТЕРИ. Это baseline: фаза D1
(SessionMapper без потерь) будет флипать помеченные `BASELINE LOSS` ассерты на
сохранение. Пока они документируют, что именно теряется.
"""

import pytest

from codelab.server.domain.conversation import ConversationMessage, Image, MessageContent
from codelab.server.domain.plan import PlanEntry
from codelab.server.domain.session import (
    ConversationHistory,
    MultiAgentState,
    PermissionState,
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


class TestRoundtripKnownGaps:
    """Оставшиеся потери — фиксированы как xfail, чинятся в D2 (формат хранения)."""

    @pytest.mark.xfail(
        reason="Мультимодальный контент истории (images/resources) теряется: to_protocol "
        "маппит только .text. Фикс меняет форму сериализации content (строка→блоки) — "
        "относится к D2 (versioned schema + миграция).",
        strict=True,
    )
    def test_multimodal_history_preserved(self) -> None:
        history = ConversationHistory()
        history.add(
            ConversationMessage(
                role=MessageRole.USER,
                content=MessageContent(
                    text="see", images=[Image(data="B64", mime_type="image/png")]
                ),
            )
        )
        session = Session(id=SessionId("s"), config=SessionConfig(cwd="/t"), history=history)
        rt = _roundtrip(session)
        assert len(rt.history.get_messages()[0].content.images) == 1

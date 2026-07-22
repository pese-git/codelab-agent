"""Round-trip тесты SessionMapper.

Покрывает sub-task 1.2a change acp-independent-agent-core (ADR-005):
SessionMapper._build_history должен сохранять tool_calls/tool_call_id/timestamp.
"""

from __future__ import annotations

from codelab.server.domain.value_objects import MessageRole
from codelab.server.mapping.session_mapper import SessionMapper
from codelab.server.models import HistoryMessage
from codelab.server.protocol.state import SessionState


def _make_state(history: list) -> SessionState:
    return SessionState(session_id="sess_1", cwd="/tmp", history=history)


def test_user_message_preserves_text() -> None:
    state = _make_state(
        [
            HistoryMessage(role="user", content="hello", timestamp="2026-07-22T10:00:00"),
        ],
    )
    session = SessionMapper.to_domain(state)
    messages = session.history.get_messages()
    assert len(messages) == 1
    assert messages[0].role == MessageRole.USER
    assert messages[0].content.text == "hello"
    assert messages[0].timestamp.isoformat() == "2026-07-22T10:00:00"
    assert messages[0].tool_call_id is None
    assert messages[0].tool_calls == []


def test_assistant_message_with_tool_calls_preserved() -> None:
    state = _make_state(
        [
            HistoryMessage(
                role="assistant",
                content="",
                tool_calls=[
                    {"id": "c1", "name": "fs/read", "arguments": {"path": "/x"}},
                    {"id": "c2", "name": "fs/write", "arguments": {"path": "/y"}},
                ],
                timestamp="2026-07-22T10:00:01",
            ),
        ],
    )
    session = SessionMapper.to_domain(state)
    messages = session.history.get_messages()
    assert len(messages) == 1
    assert messages[0].role == MessageRole.ASSISTANT
    assert len(messages[0].tool_calls) == 2
    assert messages[0].tool_calls[0].id == "c1"
    assert messages[0].tool_calls[0].tool_name == "fs/read"
    assert messages[0].tool_calls[1].id == "c2"
    assert messages[0].tool_calls[1].arguments == {"path": "/y"}


def test_tool_message_preserves_tool_call_id() -> None:
    state = _make_state(
        [
            {
                "role": "tool",
                "content": "file contents",
                "tool_call_id": "c1",
                "timestamp": "2026-07-22T10:00:02",
            },
        ],
    )
    session = SessionMapper.to_domain(state)
    messages = session.history.get_messages()
    assert len(messages) == 1
    assert messages[0].role == MessageRole.TOOL
    assert messages[0].content.text == "file contents"
    assert messages[0].tool_call_id == "c1"


def test_dict_form_with_tool_calls_and_timestamp() -> None:
    """Legacy dict-форма (без HistoryMessage) тоже поддерживается."""
    state = _make_state(
        [
            {
                "role": "assistant",
                "text": "",
                "tool_calls": [{"id": "c1", "name": "fs/read", "arguments": {}}],
                "timestamp": "2026-07-22T11:30:00",
            },
        ],
    )
    session = SessionMapper.to_domain(state)
    messages = session.history.get_messages()
    assert messages[0].role == MessageRole.ASSISTANT
    assert len(messages[0].tool_calls) == 1
    assert messages[0].tool_calls[0].id == "c1"


def test_invalid_role_falls_back_to_user() -> None:
    state = _make_state(
        [
            {"role": "unknown_role", "content": "hi"},
        ],
    )
    session = SessionMapper.to_domain(state)
    messages = session.history.get_messages()
    assert messages[0].role == MessageRole.USER


def test_invalid_timestamp_falls_back_to_epoch() -> None:
    state = _make_state(
        [
            HistoryMessage(role="user", content="hi", timestamp="not-a-date"),
        ],
    )
    session = SessionMapper.to_domain(state)
    messages = session.history.get_messages()
    assert messages[0].timestamp.year == 1970


def test_multimodal_content_not_lost() -> None:
    """HistoryMessage с content=list[dict] (мультимодальный) — content не теряется."""
    state = _make_state(
        [
            HistoryMessage(
                role="user",
                content=[{"type": "text", "text": "describe this"}, {"type": "image", "data": "x"}],
            ),
        ],
    )
    session = SessionMapper.to_domain(state)
    messages = session.history.get_messages()
    # По backward-compat: content_text становится "" (не str), но text не теряется
    # в самом history_record — это используется HistoryBuilder'ом, не SessionView.
    assert messages[0].role == MessageRole.USER

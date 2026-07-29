"""Тесты для EventHistoryWriter (write-половина, фаза C ADR-006).

Проверяет форму записи `session/update` в `events_history` — то, что потом
реплеится на `session/load` (см. `test_session_replayer.py`).
"""

from __future__ import annotations

import pytest

from codelab.server.protocol.handlers.event_history_writer import EventHistoryWriter
from codelab.server.protocol.state import SessionState


@pytest.fixture
def session() -> SessionState:
    """Создает тестовую сессию."""
    return SessionState(
        session_id="sess_test_001",
        cwd="/tmp/test",
        mcp_servers=[],
    )


@pytest.fixture
def history_writer() -> EventHistoryWriter:
    """Создает экземпляр EventHistoryWriter."""
    return EventHistoryWriter()


class TestSaveAgentMessageChunk:
    """Тесты для save_agent_message_chunk."""

    def test_saves_agent_response(
        self,
        history_writer: EventHistoryWriter,
        session: SessionState,
    ) -> None:
        """Проверяет сохранение ответа агента."""
        content = {"type": "text", "text": "Agent response"}

        history_writer.save_agent_message_chunk(session, content)

        assert len(session.events_history) == 1
        event = session.events_history[0]
        assert event["update"]["sessionUpdate"] == "agent_message_chunk"
        assert event["update"]["content"] == content


class TestSaveToolCall:
    """Тесты для save_tool_call."""

    def test_saves_tool_call(
        self,
        history_writer: EventHistoryWriter,
        session: SessionState,
    ) -> None:
        """Проверяет сохранение tool_call события."""
        history_writer.save_tool_call(
            session=session,
            tool_call_id="call_001",
            title="fs/read_text_file",
            kind="read",
            status="pending",
        )

        assert len(session.events_history) == 1
        event = session.events_history[0]
        assert event["update"]["sessionUpdate"] == "tool_call"
        assert event["update"]["toolCallId"] == "call_001"
        assert event["update"]["title"] == "fs/read_text_file"
        assert event["update"]["kind"] == "read"
        assert event["update"]["status"] == "pending"

    def test_saves_tool_call_with_content(
        self,
        history_writer: EventHistoryWriter,
        session: SessionState,
    ) -> None:
        """Проверяет сохранение tool_call с контентом."""
        content = [{"type": "text", "text": "Initial content"}]

        history_writer.save_tool_call(
            session=session,
            tool_call_id="call_002",
            title="Test tool",
            kind="other",
            status="pending",
            content=content,
        )

        event = session.events_history[0]
        assert event["update"]["content"] == content


class TestSaveToolCallUpdate:
    """Тесты для save_tool_call_update."""

    def test_saves_in_progress_update(
        self,
        history_writer: EventHistoryWriter,
        session: SessionState,
    ) -> None:
        """Проверяет сохранение in_progress обновления."""
        history_writer.save_tool_call_update(
            session=session,
            tool_call_id="call_001",
            status="in_progress",
        )

        event = session.events_history[0]
        assert event["update"]["sessionUpdate"] == "tool_call_update"
        assert event["update"]["toolCallId"] == "call_001"
        assert event["update"]["status"] == "in_progress"

    def test_saves_completed_update_with_content(
        self,
        history_writer: EventHistoryWriter,
        session: SessionState,
    ) -> None:
        """Проверяет сохранение completed обновления с контентом."""
        content = [{"type": "content", "content": {"type": "text", "text": "Result"}}]

        history_writer.save_tool_call_update(
            session=session,
            tool_call_id="call_001",
            status="completed",
            content=content,
        )

        event = session.events_history[0]
        assert event["update"]["status"] == "completed"
        assert event["update"]["content"] == content


class TestSavePlan:
    """Тесты для save_plan."""

    def test_saves_plan_entries(
        self,
        history_writer: EventHistoryWriter,
        session: SessionState,
    ) -> None:
        """Проверяет сохранение плана."""
        entries = [
            {"title": "Step 1", "description": "First step"},
            {"title": "Step 2", "description": "Second step"},
        ]

        history_writer.save_plan(session, entries)

        event = session.events_history[0]
        assert event["update"]["sessionUpdate"] == "plan"
        assert event["update"]["entries"] == entries


class TestSaveUserMessageChunk:
    """Тесты сохранения user_message_chunk."""

    def test_saves_one_event_per_block(
        self,
        history_writer: EventHistoryWriter,
        session: SessionState,
    ) -> None:
        """Каждый блок промпта — отдельное событие в исходном порядке.

        Склейка недопустима: реплей отдаёт блоки клиенту в том же порядке
        (ср. упорядоченные блоки `MessageContent`, фаза B ADR-006).
        """
        prompt = [
            {"type": "resource", "resource": {"uri": "file:///a.md", "text": "doc"}},
            {"type": "text", "text": "инструкция"},
        ]

        for block in prompt:
            history_writer.save_user_message_chunk(session, block)

        assert [e["update"]["content"]["type"] for e in session.events_history] == [
            "resource",
            "text",
        ]
        assert all(
            e["update"]["sessionUpdate"] == "user_message_chunk" for e in session.events_history
        )
        assert all("timestamp" in e for e in session.events_history)


class TestSaveSessionInfoUpdate:
    """Тесты сохранения session_info_update."""

    def test_saves_acp_shape(
        self,
        history_writer: EventHistoryWriter,
        session: SessionState,
    ) -> None:
        """Форма ACP: title + updatedAt (camelCase, `04-Session List.md`)."""
        history_writer.save_session_info_update(
            session, title="Сессия", updated_at="2026-07-29T00:00:00Z"
        )

        update = session.events_history[0]["update"]
        assert update == {
            "sessionUpdate": "session_info_update",
            "title": "Сессия",
            "updatedAt": "2026-07-29T00:00:00Z",
        }

    def test_accepts_null_fields(
        self,
        history_writer: EventHistoryWriter,
        session: SessionState,
    ) -> None:
        """`null` — валидное значение по ACP (очистка поля)."""
        history_writer.save_session_info_update(session, title=None, updated_at=None)

        update = session.events_history[0]["update"]
        assert update["title"] is None
        assert update["updatedAt"] is None

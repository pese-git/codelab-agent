"""Тесты для EventHistoryWriter (write-половина, фаза C ADR-006).

Проверяет форму записи `session/update` в `events_history` — то, что потом
реплеится на `session/load` (см. `test_session_replayer.py`).
"""

from __future__ import annotations

import pytest

from codelab.server.mapping.journal_mapper import JournalMapper
from codelab.server.protocol.handlers.event_history_writer import EventHistoryWriter
from codelab.server.storage.document import SessionDocument
from tests.server._domain_sessions import make_domain_session


@pytest.fixture
def session() -> SessionDocument:
    """Создает тестовую сессию."""
    return SessionDocument(
        session_id="sess_test_001",
        cwd="/tmp/test",
        mcp_servers=[],
    )


@pytest.fixture
def history_writer() -> EventHistoryWriter:
    """Создает экземпляр EventHistoryWriter."""
    return EventHistoryWriter()


class TestSaveAgentMessageChunk:
    """Тесты для save_agent_message."""

    def test_saves_agent_response(
        self,
        history_writer: EventHistoryWriter,
        session: SessionDocument,
    ) -> None:
        """Проверяет сохранение ответа агента."""
        content = {"type": "text", "text": "Agent response"}

        history_writer.save_agent_message(session, content)

        assert len(session.events_history) == 1
        event = session.events_history[0]
        assert event["event"] == "agent_message_recorded"
        assert event["data"]["content"] == content


class TestSaveToolCall:
    """Тесты для save_tool_call."""

    def test_saves_tool_call(
        self,
        history_writer: EventHistoryWriter,
        session: SessionDocument,
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
        assert event["event"] == "tool_call_started"
        assert event["data"]["tool_call_id"] == "call_001"
        assert event["data"]["title"] == "fs/read_text_file"
        assert event["data"]["kind"] == "read"
        assert event["data"]["status"] == "pending"

    def test_saves_tool_call_with_content(
        self,
        history_writer: EventHistoryWriter,
        session: SessionDocument,
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
        assert event["data"]["content"] == content


class TestSaveToolCallUpdate:
    """Тесты для save_tool_call_update."""

    def test_saves_in_progress_update(
        self,
        history_writer: EventHistoryWriter,
        session: SessionDocument,
    ) -> None:
        """Проверяет сохранение in_progress обновления."""
        history_writer.save_tool_call_update(
            session=session,
            tool_call_id="call_001",
            status="in_progress",
        )

        event = session.events_history[0]
        assert event["event"] == "tool_call_status_changed"
        assert event["data"]["tool_call_id"] == "call_001"
        assert event["data"]["status"] == "in_progress"

    def test_saves_completed_update_with_content(
        self,
        history_writer: EventHistoryWriter,
        session: SessionDocument,
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
        assert event["data"]["status"] == "completed"
        assert event["data"]["content"] == content


class TestSavePlan:
    """Тесты для save_plan."""

    def test_saves_plan_entries(
        self,
        history_writer: EventHistoryWriter,
        session: SessionDocument,
    ) -> None:
        """Проверяет сохранение плана."""
        entries = [
            {"title": "Step 1", "description": "First step"},
            {"title": "Step 2", "description": "Second step"},
        ]

        history_writer.save_plan(session, entries)

        event = session.events_history[0]
        assert event["event"] == "plan_recorded"
        assert event["data"]["entries"] == entries


class TestSaveUserMessage:
    """Промпт пользователя — одно событие на сообщение (шаг 4e)."""

    def test_saves_one_event_per_message_with_blocks_inside(
        self,
        history_writer: EventHistoryWriter,
        session: SessionDocument,
    ) -> None:
        """Одно событие на промпт, блоки внутри и в исходном порядке.

        **Прежнее правило было обратным** — событие на блок, — и оно кодировалось
        этим же тестом. Замена осознанная: `add_user_message` кладёт в историю
        одно сообщение из всех блоков, поэтому событие на блок делало проекцию
        `history` невыводимой (N сообщений вместо одного). Порядок блоков остаётся
        частью содержимого: реплей отдаёт по чанку на блок, и это делает проекция.
        """
        prompt = [
            {"type": "resource", "resource": {"uri": "file:///a.md", "text": "doc"}},
            {"type": "text", "text": "инструкция"},
        ]

        history_writer.save_user_message(session, prompt)

        assert len(session.events_history) == 1
        record = session.events_history[0]
        assert record["event"] == "user_message_recorded"
        assert [block["type"] for block in record["data"]["blocks"]] == ["resource", "text"]
        assert "at" in record


class TestSaveToolCallAnswer:
    """Ответ модели на вызов — событие журнала (ADR-008, шаг 4)."""

    def test_saves_domain_shape(self, history_writer: EventHistoryWriter) -> None:
        session = make_domain_session(session_id="s", cwd="/tmp", mcp_servers=[])

        history_writer.save_tool_call_answer(
            session, "llm_7", "Вызов не выполнялся: turn отменён пользователем."
        )

        record = session.runtime.events_history[0]
        assert record["event"] == "tool_call_answered"
        assert record["data"] == {
            "tool_call_id": "llm_7",
            "text": "Вызов не выполнялся: turn отменён пользователем.",
        }

    def test_is_not_replayed(self, history_writer: EventHistoryWriter) -> None:
        """Адресат ответа — LLM-история; ACP tool-ответа модели не передаёт."""
        session = make_domain_session(session_id="s", cwd="/tmp", mcp_servers=[])
        history_writer.save_tool_call_answer(session, "llm_7", "текст")

        entry = JournalMapper.from_wire(session.runtime.events_history[0])
        assert entry is not None
        assert JournalMapper.to_replay_updates(entry.event) == []

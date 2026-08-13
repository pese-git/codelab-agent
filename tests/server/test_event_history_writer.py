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
    """Тесты для save_agent_message_chunk."""

    def test_saves_agent_response(
        self,
        history_writer: EventHistoryWriter,
        session: SessionDocument,
    ) -> None:
        """Проверяет сохранение ответа агента."""
        content = {"type": "text", "text": "Agent response"}

        history_writer.save_agent_message_chunk(session, content)

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


class TestSaveUserMessageChunk:
    """Тесты сохранения user_message_chunk."""

    def test_saves_one_event_per_block(
        self,
        history_writer: EventHistoryWriter,
        session: SessionDocument,
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

        assert [e["data"]["content"]["type"] for e in session.events_history] == [
            "resource",
            "text",
        ]
        assert all(
            e["event"] == "user_message_recorded" for e in session.events_history
        )
        assert all("at" in e for e in session.events_history)


class TestSaveSessionInfoUpdate:
    """Тесты сохранения session_info_update."""

    def test_saves_acp_shape(
        self,
        history_writer: EventHistoryWriter,
        session: SessionDocument,
    ) -> None:
        """Доменная форма записи: `title` + `updated_at` (v11, шаг 3b ADR-008).

        camelCase `updatedAt` остаётся в ACP-нотификации, но на диск больше не
        уезжает: формат хранения перестал задаваться внешним протоколом. Что
        нотификация сохранила прежнюю форму — гейт `JournalMapper.to_acp_update`.
        """
        history_writer.save_session_info_update(
            session, title="Сессия", updated_at="2026-07-29T00:00:00Z"
        )

        record = session.events_history[0]
        assert record["event"] == "session_info_recorded"
        assert record["data"] == {
            "title": "Сессия",
            "updated_at": "2026-07-29T00:00:00Z",
        }

    def test_accepts_null_fields(
        self,
        history_writer: EventHistoryWriter,
        session: SessionDocument,
    ) -> None:
        """`null` — валидное значение по ACP (очистка поля)."""
        history_writer.save_session_info_update(session, title=None, updated_at=None)

        data = session.events_history[0]["data"]
        assert data["title"] is None
        assert data["updated_at"] is None


class TestDomainJournalCarrier:
    """Журнал доступен и на доменном агрегате (транзакция `session/cancel`).

    Форма записи обязана совпадать байт-в-байт независимо от носителя: пишет её
    одна проекция, а `SessionDocument` и доменный агрегат несут один и тот же
    список. Развилка носителя временна и снимается вместе с последним
    wire-писателем (фаза D ADR-006).
    """

    def test_domain_and_wire_records_are_equivalent(
        self,
        history_writer: EventHistoryWriter,
        session: SessionDocument,
    ) -> None:
        from codelab.server.mapping.session_mapper import SessionMapper

        domain = SessionMapper.to_domain(session)

        history_writer.save_tool_call_update(session, tool_call_id="call_001", status="cancelled")
        history_writer.save_tool_call_update(domain, tool_call_id="call_001", status="cancelled")

        wire_entry = session.events_history[0]
        domain_entry = domain.runtime.events_history[0]
        assert domain_entry["data"] == wire_entry["data"]
        assert domain_entry["event"] == wire_entry["event"]

    def test_content_is_carried(
        self,
        history_writer: EventHistoryWriter,
        session: SessionDocument,
    ) -> None:
        from codelab.server.mapping.session_mapper import SessionMapper

        domain = SessionMapper.to_domain(session)
        content = [{"type": "content", "content": {"type": "text", "text": "готово"}}]

        history_writer.save_tool_call_update(
            domain, tool_call_id="call_001", status="completed", content=content
        )

        assert domain.runtime.events_history[0]["data"]["content"] == content


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
        assert JournalMapper.to_replay_update(entry.event) is None

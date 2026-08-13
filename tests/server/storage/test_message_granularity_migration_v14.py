"""Гейт v14: события диалога перешли на гранулярность сообщения (шаг 4e ADR-008).

Границу сообщения журнал прежде терял на **обеих** сторонах, и оба дефекта были
латентными — их не видно, пока в сообщении один блок и в батче один вызов:

* промпт писался событием на блок, хотя `add_user_message` кладёт в историю одно
  сообщение из всех блоков;
* assistant-запись несла `tool_calls`, которых в журнале не было вовсе, поэтому
  батч из десяти вызовов проекция восстановила бы как десять сообщений.

Поэтому гейт проверяет не форму записи саму по себе, а **обратимость границы**:
сколько сообщений было, столько и восстановилось.

Миграция записи не переписывает — границу в записанном документе восстановить
нечем, и догадка молча изменила бы историю диалога. Значит документ v14 может
содержать обе формы, и это тоже проверяется здесь.
"""

from __future__ import annotations

from typing import Any

from codelab.server.domain.journal import (
    AgentMessageRecorded,
    JournalEntry,
    RequestedToolCall,
    UserMessageRecorded,
)
from codelab.server.mapping.journal_mapper import JournalMapper
from codelab.server.storage.document import CURRENT_SCHEMA_VERSION, SessionDocument

_LEGACY_PER_BLOCK: list[dict[str, Any]] = [
    {
        "event": "user_message_recorded",
        "at": "2026-08-13T10:00:00+00:00",
        "data": {"content": {"type": "text", "text": "посмотри"}},
    },
    {
        "event": "user_message_recorded",
        "at": "2026-08-13T10:00:00+00:00",
        "data": {"content": {"type": "resource_link", "uri": "file:///a.py", "name": "a.py"}},
    },
]


def _document(events: list[dict[str, Any]], version: int) -> SessionDocument:
    return SessionDocument.model_validate(
        {
            "session_id": "sess_1",
            "cwd": "/tmp",
            "schema_version": version,
            "events_history": events,
        }
    )


class TestVersion:
    def test_document_is_migrated_to_current_version(self) -> None:
        assert _document(_LEGACY_PER_BLOCK, 13).schema_version == CURRENT_SCHEMA_VERSION

    def test_migration_is_idempotent(self) -> None:
        """Миграция срабатывает на каждой валидации, то есть на каждой загрузке."""
        once = _document(_LEGACY_PER_BLOCK, 13)
        twice = SessionDocument.model_validate(once.model_dump())

        assert twice.schema_version == CURRENT_SCHEMA_VERSION
        assert twice.events_history == once.events_history


class TestNothingIsLost:
    def test_legacy_records_survive_untouched(self) -> None:
        """Записи не переписываются: границу восстановить нечем, а терять нечего."""
        document = _document(_LEGACY_PER_BLOCK, 13)

        assert document.events_history == _LEGACY_PER_BLOCK

    def test_legacy_records_stay_readable(self) -> None:
        document = _document(_LEGACY_PER_BLOCK, 13)

        events = [JournalMapper.from_wire(record) for record in document.events_history]

        assert [entry.event for entry in events if entry] == [
            UserMessageRecorded(blocks=[{"type": "text", "text": "посмотри"}]),
            UserMessageRecorded(
                blocks=[{"type": "resource_link", "uri": "file:///a.py", "name": "a.py"}]
            ),
        ]

    def test_replay_stream_is_unchanged_for_legacy_records(self) -> None:
        """Клиент на `session/load` получает тот же поток чанков, что и до v14."""
        document = _document(_LEGACY_PER_BLOCK, 13)

        stream = [
            update
            for record in document.events_history
            if (entry := JournalMapper.from_wire(record))
            for update in JournalMapper.to_replay_updates(entry.event)
        ]

        assert stream == [
            {
                "sessionUpdate": "user_message_chunk",
                "content": {"type": "text", "text": "посмотри"},
            },
            {
                "sessionUpdate": "user_message_chunk",
                "content": {"type": "resource_link", "uri": "file:///a.py", "name": "a.py"},
            },
        ]


class TestBothFormsCoexist:
    """Документ v14 несёт и новую форму, и записанную прежней версией."""

    def test_mixed_document_reads_message_boundaries_as_recorded(self) -> None:
        new_form: dict[str, Any] = {
            "event": "user_message_recorded",
            "data": {
                "blocks": [
                    {"type": "text", "text": "посмотри"},
                    {"type": "resource_link", "uri": "file:///a.py", "name": "a.py"},
                ]
            },
        }
        document = _document([*_LEGACY_PER_BLOCK, new_form], 13)

        messages = [
            entry.event
            for record in document.events_history
            if (entry := JournalMapper.from_wire(record))
        ]

        # Два сообщения из одного блока (как записано прежней версией) и одно из
        # двух блоков (как пишет нынешняя). Склейка первых двух была бы догадкой.
        assert [
            len(message.blocks) for message in messages if isinstance(message, UserMessageRecorded)
        ] == [
            1,
            1,
            2,
        ]

    def test_agent_message_without_calls_keeps_its_shape(self) -> None:
        """Записи ответа модели формат не меняют: `tool_calls` в старых просто нет."""
        legacy = {
            "event": "agent_message_recorded",
            "data": {"content": {"type": "text", "text": "готово"}},
        }
        document = _document([legacy], 13)
        entry = JournalMapper.from_wire(document.events_history[0])

        assert entry is not None
        assert entry.event == AgentMessageRecorded(content={"type": "text", "text": "готово"})

    def test_batch_boundary_survives_the_round_trip(self) -> None:
        """Десять вызовов остаются одним сообщением после записи и чтения."""
        calls = [
            RequestedToolCall(id=f"chatcmpl-{index}", name="terminal_create", arguments={})
            for index in range(10)
        ]
        wire = JournalMapper.to_wire(JournalEntry(AgentMessageRecorded(tool_calls=calls)))
        document = _document([wire], 13)
        entry = JournalMapper.from_wire(document.events_history[0])

        assert entry is not None
        assert isinstance(entry.event, AgentMessageRecorded)
        assert len(entry.event.tool_calls) == 10

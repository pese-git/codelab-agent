"""Миграция журнала v10 → v11 (шаг 3b ADR-008).

До v11 элемент `events_history` был готовой ACP-нотификацией: формат хранения
задавал внешний протокол. v11 хранит доменное событие `{event, at, data}`.

Что здесь проверяется — и почему именно это:

* **ничего не теряется** — форма записи меняется, а восстановимый из неё
  ACP-поток обязан совпасть байт-в-байт, иначе клиент после обновления увидит
  другую историю;
* **идемпотентность** — миграция применяется при валидации документа, то есть
  на каждой загрузке; повторный проход не должен ничего менять;
* **терпимость** — запись, которую модель не описывает, переносится дословно, а
  не выбрасывается: журнал писали и прежние версии.

Набор записей фикстуры — это **наблюдавшиеся на живом документе** пять наборов
полей (замер `sess_2c4726e9007e`, 2026-08-06: 108 записей, шесть видов), а не
придуманные: миграция должна пережить то, что реально лежит на дисках.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from codelab.server.domain.journal import (
    AgentMessageRecorded,
    PlanRecorded,
    SessionInfoRecorded,
    ToolCallStarted,
    ToolCallStatusChanged,
    UnknownUpdateRecorded,
    UserMessageRecorded,
)
from codelab.server.mapping.journal_mapper import JournalMapper
from codelab.server.storage.document import CURRENT_SCHEMA_VERSION, SessionDocument

TS = "2026-08-06T14:45:09.814987+00:00"


def _v10_entry(update: dict[str, Any]) -> dict[str, Any]:
    return {"type": "session_update", "update": update, "timestamp": TS}


V10_JOURNAL: list[dict[str, Any]] = [
    _v10_entry({"sessionUpdate": "user_message_chunk", "content": {"type": "text", "text": "го"}}),
    _v10_entry({"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "ок"}}),
    _v10_entry(
        {
            "sessionUpdate": "tool_call",
            "toolCallId": "call_001",
            "title": "terminal/create",
            "kind": "execute",
            "status": "pending",
        }
    ),
    _v10_entry(
        {"sessionUpdate": "tool_call_update", "toolCallId": "call_001", "status": "in_progress"}
    ),
    _v10_entry(
        {
            "sessionUpdate": "tool_call_update",
            "toolCallId": "call_001",
            "status": "completed",
            "content": [{"type": "content", "content": {"type": "text", "text": "term_1"}}],
        }
    ),
    _v10_entry(
        {
            "sessionUpdate": "plan",
            "entries": [{"content": "шаг 1", "priority": "high", "status": "pending"}],
        }
    ),
    _v10_entry({"sessionUpdate": "session_info_update", "title": "го", "updatedAt": TS}),
]


def _v10_document(journal: list[Any] | None = None) -> dict[str, Any]:
    return {
        "schema_version": 10,
        "session_id": "sess_migrate_v11",
        "cwd": "/tmp/proj",
        "events_history": V10_JOURNAL if journal is None else journal,
    }


def _migrate(journal: list[Any] | None = None) -> SessionDocument:
    return SessionDocument.model_validate(_v10_document(journal))


class TestVersionAndForm:
    def test_version_is_raised(self) -> None:
        assert _migrate().schema_version == CURRENT_SCHEMA_VERSION

    def test_every_record_becomes_domain_envelope(self) -> None:
        for record in _migrate().events_history:
            assert set(record) == {"event", "at", "data"}
            assert not record["event"].startswith("session_update")

    def test_record_kinds_are_domain_names(self) -> None:
        assert [r["event"] for r in _migrate().events_history] == [
            "user_message_recorded",
            "agent_message_recorded",
            "tool_call_started",
            "tool_call_status_changed",
            "tool_call_status_changed",
            "plan_recorded",
            "session_info_recorded",
        ]

    def test_no_acp_names_left_in_storage(self) -> None:
        """Признак того, что носитель действительно перестал быть протокольным."""
        dumped = json.dumps([r for r in _migrate().events_history], ensure_ascii=False)
        for acp_name in ("sessionUpdate", "toolCallId", "updatedAt", "user_message_chunk"):
            assert acp_name not in dumped

    def test_timestamp_is_preserved_under_new_name(self) -> None:
        assert all(r["at"] == TS for r in _migrate().events_history)


class TestNothingIsLost:
    def test_acp_stream_is_byte_identical_after_migration(self) -> None:
        """Главный инвариант: восстановленный ACP-поток совпадает с исходным."""
        migrated = _migrate().events_history

        restored = []
        for record in migrated:
            entry = JournalMapper.from_wire(record)
            assert entry is not None
            restored.extend(JournalMapper.to_acp_updates(entry.event))

        assert restored == [e["update"] for e in V10_JOURNAL]

    def test_events_are_recognised_after_migration(self) -> None:
        kinds = []
        for record in _migrate().events_history:
            entry = JournalMapper.from_wire(record)
            assert entry is not None
            kinds.append(type(entry.event))

        assert kinds == [
            UserMessageRecorded,
            AgentMessageRecorded,
            ToolCallStarted,
            ToolCallStatusChanged,
            ToolCallStatusChanged,
            PlanRecorded,
            SessionInfoRecorded,
        ]

    def test_record_count_is_unchanged(self) -> None:
        assert len(_migrate().events_history) == len(V10_JOURNAL)


class TestIdempotency:
    """Миграция применяется на каждой загрузке — повтор обязан быть тождеством."""

    def test_second_pass_changes_nothing(self) -> None:
        once = _migrate().model_dump(mode="json")

        twice = SessionDocument.model_validate(once).model_dump(mode="json")

        assert twice["events_history"] == once["events_history"]
        assert twice["schema_version"] == CURRENT_SCHEMA_VERSION

    def test_already_v11_document_is_untouched(self) -> None:
        """Документ, записанный новым кодом, миграция не трогает вовсе."""
        v11 = [
            JournalMapper.to_wire(entry)
            for entry in (JournalMapper.from_wire(r) for r in V10_JOURNAL)
            if entry is not None
        ]
        data = _v10_document(v11)
        data["schema_version"] = 11

        assert SessionDocument.model_validate(data).events_history == v11


class TestTolerance:
    def test_unmodelled_update_is_carried_verbatim(self) -> None:
        """Знакомый вид с лишним полем: переносится целиком, а не пересобирается.

        Пересборка потеряла бы `locations` — поле, которое писала прежняя версия, а
        нынешняя модель не описывает.
        """
        update = {
            "sessionUpdate": "tool_call",
            "toolCallId": "call_009",
            "title": "t",
            "kind": "read",
            "status": "pending",
            "locations": [{"path": "/tmp/a"}],
        }

        migrated = _migrate([_v10_entry(update)]).events_history

        assert migrated[0]["event"] == "acp_update_verbatim"
        assert migrated[0]["data"]["update"] == update

    def test_foreign_record_stays_as_it_was(self) -> None:
        """Запись, которая журналом не является, остаётся как была.

        Журнал ею не владеет: реплей не отдавал её и до 3b, а выбросить чужие
        данные при миграции формата — не то же самое, что сменить формат.
        """
        foreign = {"type": "permission_request", "request_id": "req_1"}

        assert _migrate([foreign]).events_history == [foreign]

    @pytest.mark.parametrize(
        "record",
        [
            {"type": "session_update", "update": {}},
            {"type": "session_update"},
            {"type": "session_update", "update": "не словарь"},
        ],
        ids=["empty-update", "no-update", "update-not-dict"],
    )
    def test_broken_records_survive_migration(self, record: dict[str, Any]) -> None:
        """Битая запись не роняет загрузку сессии и не исчезает молча."""
        assert _migrate([record]).events_history == [record]

    def test_record_without_timestamp_gets_no_at(self) -> None:
        migrated = _migrate(
            [{"type": "session_update", "update": V10_JOURNAL[0]["update"]}]
        ).events_history

        assert "at" not in migrated[0]
        assert migrated[0]["event"] == "user_message_recorded"


class TestVerbatimReplay:
    """Дословная запись обязана и реплеиться дословно — иначе смысл её теряется."""

    def test_verbatim_record_replays_unchanged(self) -> None:
        update = {
            "sessionUpdate": "tool_call_update",
            "toolCallId": "call_009",
            "status": "completed",
            "content": [],
        }

        migrated = _migrate([_v10_entry(update)]).events_history
        entry = JournalMapper.from_wire(migrated[0])

        assert entry is not None
        assert isinstance(entry.event, UnknownUpdateRecorded)
        assert JournalMapper.to_replay_updates(entry.event) == [update]

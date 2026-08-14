"""Гейт проекции журнала (шаг 3a ADR-008).

Шаг 3a вводит доменное событие и проекцию, **не меняя формат документа**. Значит
проверять надо два инварианта, и оба — про обратимость:

1. `to_wire` даёт ту же запись, что писал прежний писатель (форма документа);
2. `from_wire → to_acp_update` — тождество на записи журнала (иначе поток
   `session/load` разъедется с тем, что клиент видел в turn-е).

Второй инвариант важнее первого: именно на нём стоит вся дешевизна шага 3b. Если
разбор не обратим, расхождение на живом прогоне после 3b нельзя будет отнести к
сериализации — а ровно для этого шаг и делился надвое.

Записи, которых модель не описывает, обязаны проходить **дословно**: журнал писали
и прежние версии, и пересборка потеряла бы их поля.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from codelab.server.domain.journal import (
    AgentMessageRecorded,
    JournalEntry,
    PlanRecorded,
    RequestedToolCall,
    SessionEvent,
    SessionInfoRecorded,
    ToolCallAnswered,
    ToolCallStarted,
    ToolCallStatusChanged,
    UnknownUpdateRecorded,
    UserMessageRecorded,
)
from codelab.server.mapping.journal_mapper import JournalMapper

TS = "2026-08-06T12:00:00+00:00"

# Все шесть видов записей, которые умеет писать `EventHistoryWriter`, в их
# нынешней форме на диске — вместе с двумя опциональными вариантами контента.
RECORDED_UPDATES: list[dict[str, Any]] = [
    {"sessionUpdate": "user_message_chunk", "content": {"type": "text", "text": "изучи проект"}},
    {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "готово"}},
    {
        "sessionUpdate": "tool_call",
        "toolCallId": "call_001",
        "title": "terminal/create",
        "kind": "execute",
        "status": "pending",
    },
    {
        "sessionUpdate": "tool_call",
        "toolCallId": "call_002",
        "title": "Read file",
        "kind": "read",
        "status": "pending",
        "content": [{"type": "content", "content": {"type": "text", "text": "src/main.py"}}],
    },
    {"sessionUpdate": "tool_call_update", "toolCallId": "call_001", "status": "in_progress"},
    {
        "sessionUpdate": "tool_call_update",
        "toolCallId": "call_001",
        "status": "completed",
        "content": [{"type": "content", "content": {"type": "text", "text": "term_1"}}],
    },
    {
        "sessionUpdate": "plan",
        "entries": [{"content": "шаг 1", "priority": "high", "status": "pending"}],
    },
    {"sessionUpdate": "session_info_update", "title": "изучи проект", "updatedAt": TS},
    {"sessionUpdate": "session_info_update", "title": None, "updatedAt": None},
]


class TestRoundTrip:
    """Разбор записи и обратная проекция — тождество."""

    @pytest.mark.parametrize("update", RECORDED_UPDATES, ids=lambda u: u["sessionUpdate"])
    def test_update_survives_round_trip(self, update: dict[str, Any]) -> None:
        entry = JournalMapper.from_wire(
            {"type": "session_update", "update": update, "timestamp": TS}
        )

        assert entry is not None
        assert JournalMapper.to_acp_updates(entry.event) == [update]

    @pytest.mark.parametrize("update", RECORDED_UPDATES, ids=lambda u: u["sessionUpdate"])
    def test_recorded_update_is_modelled(self, update: dict[str, Any]) -> None:
        """То, что пишем мы, модель описывает — дословный проход тут не нужен.

        Если этот тест падает, значит писатель начал писать форму, которой в модели
        нет: запись сохранится и отреплеится, но перестанет быть доменным событием,
        а шаг 3b тихо унесёт её в новый формат как непрозрачный `dict`.
        """
        entry = JournalMapper.from_wire(
            {"type": "session_update", "update": update, "timestamp": TS}
        )

        assert entry is not None
        assert not isinstance(entry.event, UnknownUpdateRecorded)

    def test_timestamp_survives_v10_read(self) -> None:
        entry = JournalMapper.from_wire(
            {"type": "session_update", "update": RECORDED_UPDATES[0], "timestamp": TS}
        )

        assert entry is not None
        assert entry.timestamp == datetime(2026, 8, 6, 12, 0, tzinfo=UTC)

    @pytest.mark.parametrize("update", RECORDED_UPDATES, ids=lambda u: u["sessionUpdate"])
    def test_v11_record_survives_round_trip(self, update: dict[str, Any]) -> None:
        """Запись v11 → событие → запись v11 — тождество.

        Это инвариант миграции: она читает запись и пишет её обратно, поэтому
        повторный проход по уже миграированному документу обязан ничего не менять.
        """
        v10 = {"type": "session_update", "update": update, "timestamp": TS}
        v11 = JournalMapper.to_wire(JournalMapper.from_wire(v10))

        again = JournalMapper.from_wire(v11)

        assert again is not None
        assert JournalMapper.to_wire(again) == v11
        assert JournalMapper.to_acp_updates(again.event) == [update]


class TestWireForm:
    """Форма записи документа v11: `{event, at, data}` (шаг 3b)."""

    def test_entry_shape_is_domain_envelope(self) -> None:
        entry = JournalEntry(
            event=UserMessageRecorded(blocks=[{"type": "text", "text": "привет"}]),
            timestamp=datetime(2026, 8, 6, 12, 0, tzinfo=UTC),
        )

        assert JournalMapper.to_wire(entry) == {
            "event": "user_message_recorded",
            "at": TS,
            "data": {"blocks": [{"type": "text", "text": "привет"}]},
        }

    def test_tool_call_kind_does_not_collide_with_record_kind(self) -> None:
        """Ровно то, из-за чего выбран конверт: `kind` вызова и вид записи — разные поля."""
        entry = JournalEntry(
            event=ToolCallStarted(
                tool_call_id="call_001", title="terminal/create", kind="execute", status="pending"
            )
        )

        wire = JournalMapper.to_wire(entry)

        assert wire["event"] == "tool_call_started"
        assert wire["data"]["kind"] == "execute"
        assert "at" not in wire

    def test_no_acp_names_leak_into_storage(self) -> None:
        """В записи v11 не должно остаться ни camelCase, ни имён ACP-обновлений."""
        for update in RECORDED_UPDATES:
            entry = JournalMapper.from_wire(
                {"type": "session_update", "update": update, "timestamp": TS}
            )
            assert entry is not None
            wire = JournalMapper.to_wire(entry)
            assert "sessionUpdate" not in wire["data"]
            assert "toolCallId" not in wire["data"]
            assert "updatedAt" not in wire["data"]

    @pytest.mark.parametrize(
        "event",
        [
            ToolCallStarted(
                tool_call_id="call_001", title="t", kind="read", status="pending", content=None
            ),
            ToolCallStatusChanged(tool_call_id="call_001", status="completed", content=None),
        ],
        ids=["tool_call", "tool_call_update"],
    )
    def test_empty_content_is_omitted_not_null(self, event: SessionEvent) -> None:
        """Прежний писатель опускал пустой контент; `null` изменил бы документ."""
        assert "content" not in JournalMapper.to_acp_updates(event)[0]


class TestToolCallIdentity:
    """Шаг 4g ADR-008: журнал несёт имя, аргументы и id вызова у модели.

    До 4g связки внутреннего `call_NNN` с идентификатором вызова у модели не
    нёс ни один вид записи, поэтому `tool_calls` из журнала не выводилась.
    """

    def _started(self, **kwargs: Any) -> ToolCallStarted:
        return ToolCallStarted(
            tool_call_id="call_001",
            title="fs/read_text_file",
            kind="read",
            status="pending",
            **kwargs,
        )

    def test_identity_survives_round_trip(self) -> None:
        event = self._started(
            tool_name="fs/read_text_file",
            arguments={"path": "lib/main.dart"},
            tool_call_id_from_llm="chatcmpl-tool-a898aba0",
        )

        again = JournalMapper.from_wire(JournalMapper.to_wire(JournalEntry(event=event)))

        assert again is not None
        assert again.event == event

    def test_client_rpc_call_writes_no_empty_fields(self) -> None:
        """У вызовов client-RPC имени и аргументов нет; `null` в документе — шум."""
        data = JournalMapper.to_wire(JournalEntry(event=self._started()))["data"]

        assert "tool_name" not in data
        assert "arguments" not in data
        assert "tool_call_id_from_llm" not in data

    def test_identity_does_not_leak_into_acp(self) -> None:
        """ACP-формы у этих полей нет: контракт `tool_call` не меняется."""
        event = self._started(
            tool_name="fs/read_text_file",
            arguments={"path": "lib/main.dart"},
            tool_call_id_from_llm="chatcmpl-tool-a898aba0",
        )

        update = JournalMapper.to_acp_updates(event)[0]

        assert set(update) == {"sessionUpdate", "toolCallId", "title", "kind", "status"}

    def test_pre_4g_record_reads_without_identity(self) -> None:
        """Записи до 4g этих полей не несут — читаются как отсутствие, а не отказ."""
        entry = JournalMapper.from_wire(
            {
                "event": "tool_call_started",
                "at": TS,
                "data": {
                    "tool_call_id": "call_001",
                    "title": "fs/read_text_file",
                    "kind": "read",
                    "status": "pending",
                },
            }
        )

        assert entry is not None
        assert isinstance(entry.event, ToolCallStarted)
        assert entry.event.tool_name is None
        assert entry.event.arguments is None
        assert entry.event.tool_call_id_from_llm is None

    def test_alien_field_shape_is_read_as_absent(self) -> None:
        """Чужая форма поля не роняет загрузку: потеря вызова дешевле потери сессии."""
        entry = JournalMapper.from_wire(
            {
                "event": "tool_call_started",
                "at": TS,
                "data": {
                    "tool_call_id": "call_001",
                    "title": "fs/read_text_file",
                    "kind": "read",
                    "status": "pending",
                    "tool_name": 42,
                    "arguments": ["path"],
                },
            }
        )

        assert entry is not None
        assert isinstance(entry.event, ToolCallStarted)
        assert entry.event.tool_name is None
        assert entry.event.arguments is None


class TestReplayProjection:
    """Реплеируемость определяется наличием формы, а не списком имён."""

    def test_session_info_has_no_replay_form(self) -> None:
        event = SessionInfoRecorded(title="изучи проект", updated_at=TS)

        assert JournalMapper.to_replay_updates(event) == []
        acp = JournalMapper.to_acp_updates(event)
        assert acp[0]["sessionUpdate"] == "session_info_update"

    def test_answer_has_no_acp_form_at_all(self) -> None:
        """Ответ модели на вызов адресован LLM-истории, а не клиенту."""
        event = ToolCallAnswered(tool_call_id="llm_7", text="Вызов не выполнялся: отмена.")

        assert JournalMapper.to_acp_updates(event) == []
        assert JournalMapper.to_replay_updates(event) == []

    def test_answer_survives_round_trip(self) -> None:
        """Событие обязано читаться с диска: из него выводится запись `role: tool`."""
        event = ToolCallAnswered(tool_call_id="llm_7", text="Вызов не выполнялся: отмена.")

        wire = JournalMapper.to_wire(JournalEntry(event, datetime.now(UTC)))
        assert wire["event"] == "tool_call_answered"
        assert wire["data"] == {
            "tool_call_id": "llm_7",
            "text": "Вызов не выполнялся: отмена.",
        }

        restored = JournalMapper.from_wire(wire)
        assert restored is not None
        assert restored.event == event

    def test_legacy_answer_vid_is_still_read(self) -> None:
        """Документы шага 4a лежат на диске с прежним именем вида — оно читается.

        Событий ответа было два, и различались они лишь тем, выполнялся ли вызов;
        обобщение в одно (шаг 4) миграции не требует — форма данных та же, — но
        терять записи уже записанных сессий не должно.
        """
        wire = {
            "event": "unexecuted_tool_call_answered",
            "data": {"tool_call_id": "llm_7", "text": "Вызов не выполнялся: отмена."},
        }

        restored = JournalMapper.from_wire(wire)

        assert restored is not None
        assert restored.event == ToolCallAnswered(
            tool_call_id="llm_7", text="Вызов не выполнялся: отмена."
        )

    @pytest.mark.parametrize(
        "event",
        [
            UserMessageRecorded(blocks=[{"type": "text", "text": "a"}]),
            AgentMessageRecorded(content={"type": "text", "text": "b"}),
            ToolCallStarted(tool_call_id="c", title="t", kind="read", status="pending"),
            ToolCallStatusChanged(tool_call_id="c", status="completed"),
            PlanRecorded(entries=[]),
        ],
    )
    def test_conversation_events_replay_as_written(self, event: SessionEvent) -> None:
        assert JournalMapper.to_replay_updates(event) == JournalMapper.to_acp_updates(event)


class TestToleranceToRecordedSessions:
    """Уже записанные сессии не должны терять ни события, ни поля."""

    def test_known_kind_with_extra_field_passes_through_verbatim(self) -> None:
        """Лишнее поле — признак чужой (более ранней) формы записи.

        Модель его не описывает, поэтому пересборка потеряла бы поле; вместо этого
        запись идёт в поток дословно.
        """
        update = {
            "sessionUpdate": "tool_call",
            "toolCallId": "call_001",
            "title": "t",
            "kind": "read",
            "status": "pending",
            "locations": [{"path": "/tmp/a"}],
        }

        entry = JournalMapper.from_wire({"type": "session_update", "update": update})

        assert entry is not None
        assert isinstance(entry.event, UnknownUpdateRecorded)
        assert JournalMapper.to_replay_updates(entry.event) == [update]

    def test_unknown_kind_is_not_replayed(self) -> None:
        update = {"sessionUpdate": "current_mode_update", "currentModeId": "ask"}

        entry = JournalMapper.from_wire({"type": "session_update", "update": update})

        assert entry is not None
        assert JournalMapper.to_replay_updates(entry.event) == []

    @pytest.mark.parametrize(
        "wire",
        [
            {"type": "other", "update": {"sessionUpdate": "plan", "entries": []}},
            {"update": {"sessionUpdate": "plan", "entries": []}},
            {"type": "session_update", "update": {}},
            {"type": "session_update"},
            {"type": "session_update", "update": "не словарь"},
        ],
        ids=["foreign-type", "no-type", "empty-update", "no-update", "update-not-dict"],
    )
    def test_non_journal_entries_are_skipped(self, wire: dict[str, Any]) -> None:
        assert JournalMapper.from_wire(wire) is None

    def test_broken_timestamp_does_not_lose_the_event(self) -> None:
        entry = JournalMapper.from_wire(
            {"type": "session_update", "update": RECORDED_UPDATES[0], "timestamp": "вчера"}
        )

        assert entry is not None
        assert entry.timestamp is None
        assert isinstance(entry.event, UserMessageRecorded)

    def test_verbatim_record_keeps_its_fields_through_v11(self) -> None:
        """Дословная запись переживает миграцию: вид `acp_update_verbatim` несёт исходник."""
        update = {
            "sessionUpdate": "tool_call",
            "toolCallId": "call_001",
            "title": "t",
            "kind": "read",
            "status": "pending",
            "locations": [{"path": "/tmp/a"}],
        }

        v11 = JournalMapper.to_wire(
            JournalMapper.from_wire({"type": "session_update", "update": update})
        )

        assert v11["event"] == "acp_update_verbatim"
        assert v11["data"]["update"] == update
        again = JournalMapper.from_wire(v11)
        assert again is not None
        assert JournalMapper.to_replay_updates(again.event) == [update]

    def test_unknown_v11_record_kind_is_skipped_not_fatal(self) -> None:
        """Документ мог записать более новая версия: теряем запись, а не сессию."""
        assert JournalMapper.from_wire({"event": "нечто_из_будущего", "data": {}}) is None

    def test_empty_content_list_is_not_modelled(self) -> None:
        """`"content": []` необратим: проекция пустой контент опускает.

        Такая запись проходит дословно — иначе реплей потерял бы ключ.
        """
        update = {
            "sessionUpdate": "tool_call_update",
            "toolCallId": "call_001",
            "status": "completed",
            "content": [],
        }

        entry = JournalMapper.from_wire({"type": "session_update", "update": update})

        assert entry is not None
        assert isinstance(entry.event, UnknownUpdateRecorded)
        assert JournalMapper.to_replay_updates(entry.event) == [update]


class TestMessageGranularity:
    """Граница сообщения — факт журнала, а не догадка проекции (шаг 4e).

    Оба дефекта, которые здесь закрыты, невидимы на однобочных сообщениях, и
    именно поэтому прожили до шага 4: во всех наблюдавшихся промптах был ровно
    один блок, а замер батчей дал `[1, 1, 4, 4, 10, …]` только на большой сессии.
    """

    def test_multiblock_prompt_is_one_event_and_many_chunks(self) -> None:
        blocks = [
            {"type": "text", "text": "посмотри"},
            {"type": "resource_link", "uri": "file:///tmp/a.py", "name": "a.py"},
        ]
        entry = JournalEntry(UserMessageRecorded(blocks=blocks))

        wire = JournalMapper.to_wire(entry)
        assert wire["data"] == {"blocks": blocks}

        restored = JournalMapper.from_wire(wire)
        assert restored is not None
        assert restored.event == UserMessageRecorded(blocks=blocks)

        # ACP передаёт сообщение чанками — по одному на блок, порядок сохранён.
        assert JournalMapper.to_acp_updates(restored.event) == [
            {"sessionUpdate": "user_message_chunk", "content": blocks[0]},
            {"sessionUpdate": "user_message_chunk", "content": blocks[1]},
        ]

    def test_batch_of_calls_stays_one_assistant_message(self) -> None:
        """Десять вызовов — один ход модели; склейка по вызову дала бы десять."""
        calls = [
            RequestedToolCall(id=f"chatcmpl-{i}", name="terminal_create", arguments={"n": i})
            for i in range(10)
        ]
        event = AgentMessageRecorded(content={"type": "text", "text": "сейчас"}, tool_calls=calls)

        wire = JournalMapper.to_wire(JournalEntry(event))
        restored = JournalMapper.from_wire(wire)

        assert restored is not None
        assert restored.event == event
        assert len(wire["data"]["tool_calls"]) == 10

    def test_requested_calls_carry_what_acp_does_not(self) -> None:
        """Имя для модели расходится с ACP-именем — вывести его из `title` нельзя."""
        event = AgentMessageRecorded(
            tool_calls=[
                RequestedToolCall(
                    id="chatcmpl-tool-813c", name="terminal_create", arguments={"command": "ls -la"}
                )
            ]
        )

        wire = JournalMapper.to_wire(JournalEntry(event))

        assert wire["data"] == {
            "tool_calls": [
                {
                    "id": "chatcmpl-tool-813c",
                    "name": "terminal_create",
                    "arguments": {"command": "ls -la"},
                }
            ]
        }
        # Текста нет — значит и ACP-чанка нет: клиент узнаёт о вызовах
        # нотификациями `tool_call`.
        assert JournalMapper.to_acp_updates(event) == []

    def test_legacy_per_block_prompt_is_still_read(self) -> None:
        """Запись v13 (событие на блок) читается как сообщение из одного блока.

        Склеивать соседние записи миграция не вправе: два события могут быть и
        одним промптом из двух блоков, и двумя промптами, а ошибка молча изменила
        бы историю диалога.
        """
        wire = {
            "event": "user_message_recorded",
            "data": {"content": {"type": "text", "text": "привет"}},
        }

        restored = JournalMapper.from_wire(wire)

        assert restored is not None
        assert restored.event == UserMessageRecorded(blocks=[{"type": "text", "text": "привет"}])

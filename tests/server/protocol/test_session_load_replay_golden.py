"""Golden-поток `session/load`: что именно клиент получает при загрузке сессии.

Предусловие шага 3 ADR-008 (журнал доменных событий, ACP — проекция). До шага 3a реплей был
**pass-through**: `SessionReplayer` отдавал элементы `events_history` в нотификацию дословно,
без конверсии. Шаг 3a заменил его проекцией из доменного журнала, и проекция обязана давать
байт-идентичный поток: иначе клиент после `session/load` увидит другую историю, чем видел в
turn-е, а у части клиентов это разъезжается с их собственным состоянием. **Шаг 3a этот гейт
прошёл без правок утверждений** — они и написаны про контракт, а не про реализацию.

Гейт снят **до** правки намеренно. Golden, написанный после, закрепляет новое поведение
вместо проверки совместимости — на этом проект уже обжигался (урок ADR-006: гейт D0.1
снимался до write-фазы, а не после).

Ломается этот тест → изменился клиентский контракт загрузки сессии, то есть цена шага вышла
за заявленную область.

Поток складывается из **трёх** источников, и все три зафиксированы порознь, потому что шаг 3
затрагивает их по-разному:

* `replay_history` — события журнала; здесь и жил pass-through, теперь проекция;
* `replay_latest_plan` — план хранится отдельно от журнала для быстрого доступа;
* `_replay_tool_calls_fallback` — совместимость с сессиями, записанными до того, как события
  `tool_call` стали попадать в журнал.

**Зафиксирована и известная асимметрия:** `session_info_update` писатель умеет, а в поток
загрузки событие не попадает — оно персистируется и не реплеится никогда. Шаг 3a решил судьбу
поля в пользу сохранения этого поведения, но выразил его конструкцией: у `SessionInfoRecorded`
нет реплей-формы, а прежний набор `_REPLAYABLE_UPDATE_TYPES` снят. Утверждения гейта от этого
не изменились.
"""

from __future__ import annotations

from typing import Any

import pytest

from codelab.server.domain.session import Session as DomainSession
from codelab.server.domain.value_objects import ToolCallStatus
from codelab.server.mapping.journal_mapper import JournalMapper
from codelab.server.protocol.handlers.session import _replay_tool_calls_fallback
from codelab.server.protocol.handlers.session_replayer import SessionReplayer
from tests.server._domain_sessions import make_domain_session

SESSION_ID = "sess_golden_load"
TS = "2026-08-06T12:00:00+00:00"


def _event(update: dict[str, Any]) -> dict[str, Any]:
    """Элемент журнала в его нынешней форме: готовая ACP-нотификация плюс метка времени."""
    return {"type": "session_update", "update": update, "timestamp": TS}


def _session_with_all_event_kinds() -> DomainSession:
    """Сессия со всеми шестью видами событий, которые умеет писать `EventHistoryWriter`.

    Порядок намеренно тот же, что даёт живой turn: сообщение пользователя → план →
    вызов → его обновления → сообщение агента → заголовок сессии.
    """
    return make_domain_session(
        session_id=SESSION_ID,
        cwd="/tmp",
        events_history=[
            _event(
                {
                    "sessionUpdate": "user_message_chunk",
                    "content": {"type": "text", "text": "изучи проект"},
                }
            ),
            _event(
                {
                    "sessionUpdate": "plan",
                    "entries": [{"content": "шаг 1", "priority": "high", "status": "pending"}],
                }
            ),
            _event(
                {
                    "sessionUpdate": "tool_call",
                    "toolCallId": "call_001",
                    "title": "terminal/create",
                    "kind": "execute",
                    "status": "pending",
                }
            ),
            _event(
                {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "call_001",
                    "status": "in_progress",
                }
            ),
            _event(
                {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "call_001",
                    "status": "completed",
                    "content": [
                        {"type": "content", "content": {"type": "text", "text": "term_1"}}
                    ],
                }
            ),
            _event(
                {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": "готово"},
                }
            ),
            _event(
                {
                    "sessionUpdate": "session_info_update",
                    "title": "изучи проект",
                    "updatedAt": TS,
                }
            ),
        ],
    )


@pytest.fixture
def replayer() -> SessionReplayer:
    return SessionReplayer()


class TestReplayHistoryGolden:
    """Поток из журнала — дословно, включая порядок."""

    def test_full_stream_is_byte_identical(self, replayer: SessionReplayer) -> None:
        session = _session_with_all_event_kinds()

        notifications = replayer.replay_history(session)

        assert [msg.method for msg in notifications] == ["session/update"] * 6
        assert [msg.params for msg in notifications] == [
            {
                "sessionId": SESSION_ID,
                "update": {
                    "sessionUpdate": "user_message_chunk",
                    "content": {"type": "text", "text": "изучи проект"},
                },
            },
            {
                "sessionId": SESSION_ID,
                "update": {
                    "sessionUpdate": "plan",
                    "entries": [{"content": "шаг 1", "priority": "high", "status": "pending"}],
                },
            },
            {
                "sessionId": SESSION_ID,
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": "call_001",
                    "title": "terminal/create",
                    "kind": "execute",
                    "status": "pending",
                },
            },
            {
                "sessionId": SESSION_ID,
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "call_001",
                    "status": "in_progress",
                },
            },
            {
                "sessionId": SESSION_ID,
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "call_001",
                    "status": "completed",
                    "content": [
                        {"type": "content", "content": {"type": "text", "text": "term_1"}}
                    ],
                },
            },
            {
                "sessionId": SESSION_ID,
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": "готово"},
                },
            },
        ]

    def test_session_info_update_is_not_replayed(self, replayer: SessionReplayer) -> None:
        """Событие пишется и персистируется, но в поток загрузки не попадает.

        Писатель умеет шесть видов событий, реплей отдаёт пять. Шаг 3a ADR-008 решил
        судьбу поля: поведение сохранено, но держится теперь на отсутствии реплей-формы
        у `SessionInfoRecorded`, а не на перечислении имён в читателе. Если решение
        когда-нибудь станет «реплеить», этот тест обязан поменяться осознанно.
        """
        session = _session_with_all_event_kinds()

        kinds = [msg.params["update"]["sessionUpdate"] for msg in replayer.replay_history(session)]

        assert "session_info_update" not in kinds
        assert len(session.runtime.events_history) == 7

    def test_timestamp_does_not_reach_wire(self, replayer: SessionReplayer) -> None:
        """Метка времени — поле журнала, а не нотификации: в wire её быть не должно."""
        session = _session_with_all_event_kinds()

        for msg in replayer.replay_history(session):
            assert "timestamp" not in msg.params
            assert "timestamp" not in msg.params["update"]

    def test_foreign_event_shapes_are_skipped(self, replayer: SessionReplayer) -> None:
        """Записи не своей формы пропускаются, а не роняют загрузку."""
        session = make_domain_session(
            session_id=SESSION_ID,
            cwd="/tmp",
            events_history=[
                {"type": "something_else", "update": {"sessionUpdate": "tool_call"}},
                {"type": "session_update", "update": {}},
                _event({"sessionUpdate": "agent_message_chunk", "content": {"type": "text"}}),
            ],
        )

        notifications = replayer.replay_history(session)

        assert len(notifications) == 1
        assert notifications[0].params["update"]["sessionUpdate"] == "agent_message_chunk"


class TestReplayHistoryFromV11Golden:
    """Тот же поток, но журнал хранится в доменной форме (v11, шаг 3b).

    Смысл гейта: смена формата хранения не должна менять ни один байт того, что
    видит клиент. Поток сравнивается не с константой, а с потоком из документа
    v10 — так проверяется именно эквивалентность носителей, и константу нельзя
    подогнать под новую реализацию.
    """

    def test_stream_is_identical_to_v10(self, replayer: SessionReplayer) -> None:
        v10_session = _session_with_all_event_kinds()
        v11_session = _session_with_all_event_kinds()
        v11_session.runtime.events_history = [
            JournalMapper.to_wire(JournalMapper.from_wire(record))
            for record in v11_session.runtime.events_history
        ]

        from_v10 = [msg.params for msg in replayer.replay_history(v10_session)]
        from_v11 = [msg.params for msg in replayer.replay_history(v11_session)]

        assert from_v11 == from_v10
        assert len(from_v11) == 6


class TestReplayLatestPlanGolden:
    """План живёт отдельно от журнала — значит и в проекции останется отдельным источником."""

    def test_absent_plan_gives_no_notification(self, replayer: SessionReplayer) -> None:
        session = make_domain_session(session_id=SESSION_ID, cwd="/tmp")

        assert replayer.replay_latest_plan(session) is None

    def test_plan_notification_is_byte_identical(self, replayer: SessionReplayer) -> None:
        entries = [
            {"content": "шаг 1", "priority": "high", "status": "completed"},
            {"content": "шаг 2", "priority": "low", "status": "pending"},
        ]
        session = make_domain_session(session_id=SESSION_ID, cwd="/tmp", latest_plan=entries)

        msg = replayer.replay_latest_plan(session)

        assert msg is not None
        assert msg.method == "session/update"
        assert msg.params == {
            "sessionId": SESSION_ID,
            "update": {"sessionUpdate": "plan", "entries": entries},
        }


class TestToolCallFallbackGolden:
    """Ветка совместимости с сессиями, у которых событий `tool_call` в журнале нет."""

    def test_silent_when_journal_has_tool_call_events(self) -> None:
        """Есть события — ветка не работает: иначе клиент получил бы вызовы дважды."""
        session = _session_with_all_event_kinds()

        assert _replay_tool_calls_fallback(session, SESSION_ID) == []

    def test_silent_for_v11_journal_too(self) -> None:
        """То же для документа v11, где строки `sessionUpdate` в журнале нет вовсе.

        Ветка решает «есть ли в журнале вызовы» и до шага 3b судила об этом по
        camelCase-строке записи. В v11 такой строки нет, поэтому проверка по ней
        молча решила бы, что вызовов не было, и досылала бы их **вдобавок** к
        обычному реплею — клиент увидел бы каждый вызов дважды. Случая v11 в гейте
        не было, поэтому поломку он бы не поймал; добавлен вместе с 3b.
        """
        session = _session_with_all_event_kinds()
        session.runtime.events_history = [
            JournalMapper.to_wire(JournalMapper.from_wire(record))
            for record in session.runtime.events_history
        ]
        assert all("event" in record for record in session.runtime.events_history)
        call = session.tool_calls.create(
            "terminal/create", {"command": "ls"}, title="terminal/create", kind="execute"
        )
        assert call is not None

        assert _replay_tool_calls_fallback(session, SESSION_ID) == []

    def test_replays_pending_status_regardless_of_real_one(self) -> None:
        """Известное расхождение (P2-42): вызов реплеится как `pending`.

        Настоящий статус досылается отдельным `tool_call_update`. Это второй источник
        расхождения wire↔состояние, и он закрепляется здесь как текущее поведение —
        выправляется шагом 3/4, а не этим гейтом.
        """
        session = make_domain_session(session_id=SESSION_ID, cwd="/tmp")
        call = session.tool_calls.create(
            "terminal/create", {"command": "ls"}, title="terminal/create", kind="execute"
        )
        session.tool_calls.update_status(call.id, ToolCallStatus.IN_PROGRESS)
        session.tool_calls.update_status(call.id, ToolCallStatus.COMPLETED)

        notifications = _replay_tool_calls_fallback(session, SESSION_ID)

        assert [msg.params["update"]["sessionUpdate"] for msg in notifications] == [
            "tool_call",
            "tool_call_update",
        ]
        assert notifications[0].params["update"]["status"] == "pending"
        assert notifications[1].params["update"]["status"] == "completed"

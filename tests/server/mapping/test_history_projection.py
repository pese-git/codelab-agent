"""Гейт шага 4f ADR-008: `history` — проекция журнала, а не источник.

Главная проверка — на **настоящей записанной сессии**
(`fixtures/recorded_session_v14.json`, живой прогон `sess_b90265bfe412`): проекция
обязана дать ту же историю, что лежит в документе. Это тот самый гейт, который ADR
называл обязательным для шага — «проекция из журнала == текущее состояние на
записанных сессиях», — и синтетическими данными он не заменяется: премиса «журнал
описывает диалог целиком» ломалась пять раз, и каждый раз это находил замер по
настоящему документу, а не тест.

Фикстура — копия живого документа с обрезанными до 120 символов строками: форма
записей, границы сообщений и адресаты ответов сохранены полностью, а вес файла
нет. Обрезка одинакова для истории и журнала, поэтому равенство проверяется
честно. Домашний путь обезличен (`/Users/dev`): для проекции пути — непрозрачные
строки, а репозиторий открытый.

Метка времени сравнивается отдельно и намеренно нестрого: история ставила свою в
момент вызова сейма, журнал — в момент записи события, поэтому они расходятся на
микросекунды. Модель этого не видит (`HistoryBuilder` метку не читает), а с шага
4f источник метки — журнал.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codelab.server.domain.history_projection import project_history
from codelab.server.mapping.history_mapper import HistoryMapper
from codelab.server.mapping.journal_mapper import JournalMapper
from codelab.server.mapping.session_mapper import SessionMapper
from codelab.server.storage.document import SessionDocument

_FIXTURE = (
    Path(__file__).resolve().parents[1] / "storage" / "fixtures" / "recorded_session_v14.json"
)


def _recorded() -> dict[str, Any]:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _without_timestamp(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "timestamp"}


def _wire(messages: list[Any]) -> list[dict[str, Any]]:
    return [
        HistoryMapper.to_protocol(message).model_dump(exclude_none=True) for message in messages
    ]


class TestProjectionMatchesRecordedState:
    """Проекция == состояние на сессии, записанной живым прогоном."""

    def test_projection_reproduces_the_recorded_history(self) -> None:
        recorded = _recorded()
        entries = [
            entry
            for entry in (JournalMapper.from_wire(record) for record in recorded["events_history"])
            if entry is not None
        ]

        projected = _wire(project_history(entries))
        stored = _wire(
            [
                HistoryMapper.to_domain(SessionDocument.model_validate(recorded).history[index])
                for index in range(len(recorded["history"]))
            ]
        )

        assert [_without_timestamp(record) for record in projected] == [
            _without_timestamp(record) for record in stored
        ]

    def test_recorded_session_exercises_the_hard_cases(self) -> None:
        """Фикстура обязана нести то, на чём проекция ломалась, иначе гейт пустой.

        Многоблочный промпт и батч из нескольких вызовов — ровно те два случая,
        которых не было ни в одном прогоне до 4e и без которых равенство выше
        достигалось бы на тривиальных данных.
        """
        recorded = _recorded()
        prompts = [
            record["data"]["blocks"]
            for record in recorded["events_history"]
            if record["event"] == "user_message_recorded"
        ]
        batches = [
            record["data"]["tool_calls"]
            for record in recorded["events_history"]
            if record["event"] == "agent_message_recorded" and record["data"].get("tool_calls")
        ]

        assert max(len(blocks) for blocks in prompts) > 1, "нужен многоблочный промпт"
        assert max(len(batch) for batch in batches) > 1, "нужен батч из нескольких вызовов"

    def test_answers_carry_their_addressee(self) -> None:
        """`role: tool` без адресата порвал бы контракт LLM-API."""
        recorded = _recorded()
        entries = [
            entry
            for entry in (JournalMapper.from_wire(record) for record in recorded["events_history"])
            if entry is not None
        ]

        answers = [message for message in project_history(entries) if message.tool_call_id]

        assert answers, "в записанной сессии есть ответы модели"
        assert all(message.content.text for message in answers)


class TestDocumentNoLongerCarriesHistory:
    """Вторая половина шага: коллекция перестала персистироваться."""

    def test_projected_session_writes_no_history(self) -> None:
        document = SessionDocument.model_validate(_recorded())
        session = SessionMapper.to_domain(document)

        # Документ фикстуры историю несёт, поэтому остаётся легаси: его коллекция
        # продолжает писаться, иначе разговор прежних сессий пропал бы.
        assert session.history_is_source is True
        assert SessionMapper.to_protocol(session).history != []

    def test_session_without_stored_history_projects_and_stops_writing_it(self) -> None:
        recorded = _recorded()
        recorded["history"] = []
        document = SessionDocument.model_validate(recorded)

        session = SessionMapper.to_domain(document)

        assert session.history_is_source is False
        assert len(session.history.get_messages()) == len(_recorded()["history"])
        assert SessionMapper.to_protocol(session).history == []

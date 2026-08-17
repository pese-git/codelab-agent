"""Построение доменного агрегата сессии для тестов.

Носитель состояния turn-пути — доменный `Session` (ADR-006, фаза D шаг 3),
поэтому тесты этого пути обязаны подавать агрегат, а не wire-DTO. Сборка идёт
через `SessionMapper.to_domain` от wire-формы намеренно: так тестовая сессия
получается ровно тем же путём, каким её получает прод (загрузка документа →
агрегат), и расхождение маппера немедленно видно тестам, а не только на диске.
"""

from __future__ import annotations

from typing import Any

from codelab.server.domain.session import Session
from codelab.server.mapping.history_mapper import HistoryMapper
from codelab.server.mapping.journal_mapper import JournalMapper
from codelab.server.mapping.session_mapper import SessionMapper
from codelab.server.protocol.session_commands import SessionCommands
from codelab.server.storage import InMemoryStorage, SessionRepository, SessionStorage
from codelab.server.storage.document import SessionDocument


def make_domain_session(
    session_id: str = "sess_1",
    cwd: str = "/tmp",
    **fields: Any,
) -> Session:
    """Доменный агрегат сессии с полями wire-формы.

    Пример использования:
        session = make_domain_session(config_values={"mode": "plan"})
    """
    fields.setdefault("mcp_servers", [])
    return SessionMapper.to_domain(
        SessionDocument(session_id=session_id, cwd=cwd, **fields),
    )


def preregister_terminal_aliases(
    executor: Any,
    session: Session,
    mapping: dict[str, str],
) -> None:
    """Посеять связки alias → client terminalId в реестре исполнителя.

    С ADR-007 (шаг A) связка живёт в процессном `TerminalAliasRegistry`, а не в
    документе сессии, поэтому тесты dispatch'а больше не могут подать её полем
    wire-формы (`terminals=...`) — этого поля нет.

    Посев идёт во внутренний словарь реестра сознательно: тождественные маппинги
    вида `term_001 → term_001` через `register` не выражаются (он сам выдаёт
    `term_<n>` по счётчику), а эти тесты проверяют именно dispatch и flow, а не
    выдачу alias'ов. Публичного метода «привязать конкретный alias» в проде нет и
    быть не должно — иначе появился бы путь выдать alias в обход счётчика.
    """
    from codelab.server.tools.executors.terminal_alias_registry import _TerminalRecord

    executor._aliases._by_session.setdefault(str(session.id), {}).update(
        {
            alias: _TerminalRecord(client_terminal_id=client_id)
            for alias, client_id in mapping.items()
        }
    )


class _SeededMemoryStorage(InMemoryStorage):
    """In-memory backend с уже посеянной сессией.

    Нужен, чтобы `make_commands` оставался синхронным и годился и в sync-, и в
    async-тестах: сама запись сессии асинхронна, а посев — это состояние «до
    теста». Дальше backend ведёт себя как обычный, включая compare-and-set.
    """

    def __init__(self, state: SessionDocument) -> None:
        super().__init__()
        self._sessions[state.session_id] = state


def make_commands(
    session: Session,
    *,
    storage: SessionStorage | None = None,
) -> SessionCommands:
    """Шов команд над сессией, посеянной в хранилище (ADR-006, фаза D шаг 4).

    Turn-путь пишет состояние только командами, а команда загружает сессию из
    хранилища в момент применения — поэтому агрегата мало, сессия обязана в
    хранилище быть. Backend настоящий, а не мок: на моке команда «применилась»
    бы к чему угодно, и потеря записи осталась бы невидимой (тот же класс, что
    P1-49).

    Пример использования:
        commands = make_commands(make_domain_session())
        await orchestrator.handle_prompt("req_1", {"prompt": prompt}, commands)
    """
    state = SessionMapper.to_protocol(session)
    backend = storage if storage is not None else _SeededMemoryStorage(state)
    return SessionCommands(SessionRepository(backend), session)


def wire_history(session: Session) -> list[dict[str, Any]]:
    """История агрегата в wire-форме — той, что уезжает модели и клиенту.

    Сверять запись turn'а с wire-формой, а не с доменными полями, — сознательно:
    расхождение «в памяти одно, на диске другое» и было корнем P1-45.

    **С шага 4f ADR-008 источник другой, а форма та же.** История перестала
    персистироваться: документ её не несёт, потому что она проекция журнала.
    Поэтому помощник рендерит сообщения агрегата тем же маппером, вместо чтения
    `SessionDocument.history`, — иначе он проверял бы отсутствие коллекции, а не
    содержание разговора. Что разговор доезжает до диска и обратно, проверяют
    гейты round-trip: там источником выступает журнал.
    """
    return [
        HistoryMapper.to_protocol(message).model_dump(exclude_none=True)
        for message in session.history.get_messages()
    ]


def wire_journal(session: Session) -> list[dict[str, Any]]:
    """Журнал агрегата в wire-форме — той, что уезжает на диск.

    Парный к `wire_history` и по той же причине. С шага 6a ADR-008 журнал —
    доменная коллекция `SessionJournal`, а не список wire-записей в
    `SessionRuntime`, поэтому тест, читавший журнал через прежнее поле рантайма,
    читал бы теперь несуществующее.

    Помощник рендерит записи тем же маппером, каким их пишет хранилище. Так
    тесты продолжают проверять **содержание** журнала — то, что уедет на диск и
    вернётся, — а не устройство контейнера, в котором он лежит в памяти.
    """
    return [JournalMapper.to_wire(entry) for entry in session.journal.entries()]

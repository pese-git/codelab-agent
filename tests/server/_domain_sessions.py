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
from codelab.server.mapping.session_mapper import SessionMapper
from codelab.server.protocol.session_commands import SessionCommands
from codelab.server.protocol.state import SessionState
from codelab.server.storage import InMemoryStorage, SessionRepository, SessionStorage


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
        SessionState(session_id=session_id, cwd=cwd, **fields),
    )


class _SeededMemoryStorage(InMemoryStorage):
    """In-memory backend с уже посеянной сессией.

    Нужен, чтобы `make_commands` оставался синхронным и годился и в sync-, и в
    async-тестах: сама запись сессии асинхронна, а посев — это состояние «до
    теста». Дальше backend ведёт себя как обычный, включая compare-and-set.
    """

    def __init__(self, state: SessionState) -> None:
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
    """История агрегата в том виде, в каком она уезжает на диск.

    Сверять запись turn'а с wire-формой, а не с доменными полями, — сознательно:
    расхождение «в памяти одно, на диске другое» и было корнем P1-45, поэтому
    тесты истории смотрят именно на то, что уедет в документ сессии.
    """
    protocol = SessionMapper.to_protocol(session)
    return [entry.model_dump(exclude_none=True) for entry in protocol.history]

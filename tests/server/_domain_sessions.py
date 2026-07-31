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
from codelab.server.protocol.state import SessionState


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


def wire_history(session: Session) -> list[dict[str, Any]]:
    """История агрегата в том виде, в каком она уезжает на диск.

    Сверять запись turn'а с wire-формой, а не с доменными полями, — сознательно:
    расхождение «в памяти одно, на диске другое» и было корнем P1-45, поэтому
    тесты истории смотрят именно на то, что уедет в документ сессии.
    """
    protocol = SessionMapper.to_protocol(session)
    return [
        entry if isinstance(entry, dict) else entry.model_dump(exclude_none=True)
        for entry in protocol.history
    ]

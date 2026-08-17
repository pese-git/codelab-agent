"""Дверь смены статуса пишет событие сама (шаг 4g ADR-008).

С 4g реестр вызовов — проекция журнала, поэтому переход и его событие обязаны
жить в одной команде. Раньше событие писал sink следующей командой, и между
ними агрегат перезагружался: статус терялся, а завершение упиралось в запрет
`pending → completed`.
"""

from __future__ import annotations

from typing import Any

from codelab.server.domain.journal import ToolCallStatusChanged
from codelab.server.domain.value_objects import ToolCallStatus
from codelab.server.mapping.journal_mapper import JournalMapper
from codelab.server.protocol.handlers.tool_call_handler import ToolCallHandler
from tests.server._domain_sessions import make_domain_session, wire_journal


def _events(session: Any) -> list[ToolCallStatusChanged]:
    entries = [JournalMapper.from_wire(record) for record in wire_journal(session)]
    return [
        entry.event
        for entry in entries
        if entry is not None and isinstance(entry.event, ToolCallStatusChanged)
    ]


def _session_with_call() -> Any:
    session = make_domain_session(session_id="sess_1", cwd="/tmp", mcp_servers=[])
    ToolCallHandler().create_tool_call(
        session, title="fs/read_text_file", kind="read", tool_name="fs/read_text_file"
    )
    return session


def test_accepted_transition_is_journalled() -> None:
    session = _session_with_call()

    ToolCallHandler().update_tool_call_status(session, "call_001", "in_progress")

    assert [event.status for event in _events(session)] == ["in_progress"]


def test_rejected_transition_is_not_journalled() -> None:
    """Запись об отклонённом переходе сделала бы проекцию описанием того, чего не было."""
    session = _session_with_call()

    # `pending → completed` матрица запрещает: вызов не начинал работу.
    ToolCallHandler().update_tool_call_status(session, "call_001", "completed")

    assert _events(session) == []
    assert session.tool_calls.get("call_001").status is ToolCallStatus.PENDING


def test_journal_carries_what_the_client_saw_not_the_model_summary() -> None:
    """Содержимое состояния и журнала различаются намеренно.

    Замер 14.08.2026 на живой сессии: состояние несёт сводку для модели
    (`{"type": "content", ...}`), а клиенту уходят извлечённые блоки
    (`{"type": "text", ...}`; у терминала — ещё и вложение). Журнал читает
    реплей, поэтому в нём обязано лежать клиентское. Свести их к одному можно
    только вместе с решением, что именно видит клиент, — это не задача 4g.
    """
    session = _session_with_call()
    handler = ToolCallHandler()
    handler.update_tool_call_status(session, "call_001", "in_progress")

    for_model = [{"type": "content", "content": {"type": "text", "text": "Success"}}]
    for_client = [{"type": "text", "text": "содержимое файла"}]
    handler.update_tool_call_status(
        session,
        "call_001",
        "completed",
        content=for_model,
        journal_content=for_client,
    )

    assert session.tool_calls.get("call_001").result.content == for_model
    assert _events(session)[-1].content == for_client

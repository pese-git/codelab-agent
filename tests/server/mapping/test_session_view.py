"""Проекция домена на read-порт ядра (`DomainSessionView`, шаг 2 фазы D ADR-006).

Главный гейт — не «поля читаются», а «читается ровно то, что уезжает на диск»:
ядро и хранилище обязаны видеть одну сессию, иначе флип носителя в шаге 3 молча
поменяет вход модели.
"""

from __future__ import annotations

import pytest

from codelab.server.agent.contracts.ports import SessionView
from codelab.server.domain.session import Session, SessionConfig
from codelab.server.domain.tool_call import ToolCall
from codelab.server.domain.value_objects import SessionId
from codelab.server.mapping.session_mapper import SessionMapper
from codelab.server.mapping.session_view import DomainSessionView
from codelab.shared.capabilities import ClientCapabilities


def _domain_session() -> Session:
    return Session(
        id=SessionId("sess_1"),
        config=SessionConfig(
            cwd="/tmp/project",
            config_values={"model": "gpt-4o", "_agent": "coder"},
            runtime_capabilities=ClientCapabilities(fs_read=True, fs_write=False, terminal=True),
        ),
    )


def _accepts_port(session: SessionView) -> str:
    """Приёмник, типизированный портом: проверяет соответствие статически (`ty`)."""
    return session.session_id


def test_projection_satisfies_the_port() -> None:
    """Проекция подставляется туда, где объявлен `SessionView`."""
    session = _domain_session()

    assert _accepts_port(DomainSessionView(session)) == "sess_1"


def test_core_sees_the_conversation_that_the_document_no_longer_carries() -> None:
    """Ядро читает историю сессии, а документ её больше не несёт (шаг 4f ADR-008).

    Прежде тест требовал равенства `view.history` и `state.history` — и это
    равенство было формой той самой второй копии, которую шаг убрал: история
    стала проекцией журнала и на диск не уезжает. Инвариант остался прежним по
    смыслу — ядро видит разговор целиком, — но источник у него теперь один.
    """
    session = _domain_session()
    session.add_user_message([{"type": "text", "text": "привет"}])
    session.add_assistant_tool_call_message(
        "смотрю", [ToolCall(id="call_1", tool_name="fs/read", arguments={"path": "/a.py"})]
    )
    session.add_tool_result("call_1", "содержимое файла")

    view = DomainSessionView(session)
    state = SessionMapper.to_protocol(session)

    assert view.session_id == state.session_id
    assert view.cwd == state.cwd
    assert view.config_values == state.config_values
    assert [message.role for message in view.history] == ["user", "assistant", "tool"]
    assert state.history == []


def test_capabilities_satisfy_the_port_without_conversion() -> None:
    """Доменные возможности отдаются как есть — порт структурный."""
    session = _domain_session()

    caps = DomainSessionView(session).runtime_capabilities

    assert caps is not None
    assert (caps.fs_read, caps.fs_write, caps.terminal) == (True, False, True)


def test_capabilities_absent_stay_none() -> None:
    """Отсутствие возможностей не подменяется пустым объектом."""
    session = Session(id=SessionId("sess_2"), config=SessionConfig(cwd="/tmp"))

    assert DomainSessionView(session).runtime_capabilities is None


def test_history_is_read_through_not_snapshot() -> None:
    """Запись, добавленная в агрегат после создания проекции, видна сразу.

    Порт это обещает («чтение сквозь сессию, не снимок»): без этого продолжение
    turn'а не увидело бы результаты инструментов текущего turn'а.
    """
    session = _domain_session()
    view = DomainSessionView(session)
    assert len(view.history) == 0

    session.add_user_message([{"type": "text", "text": "первый"}])
    assert len(view.history) == 1

    session.add_assistant_message("ответ")
    assert [entry.role for entry in view.history] == ["user", "assistant"]


def test_config_values_are_read_through() -> None:
    """Конфиг тоже читается сквозь агрегат: `/mode` меняет его посреди turn'а."""
    session = _domain_session()
    view = DomainSessionView(session)

    session.set_config_value("mode", "yolo")

    assert view.config_values["mode"] == "yolo"


def test_projection_does_not_accept_writes() -> None:
    """Проекция не носитель состояния: записать через неё нельзя."""
    view = DomainSessionView(_domain_session())

    with pytest.raises(AttributeError):
        view.cwd = "/other"  # type: ignore[misc]

    with pytest.raises(AttributeError):
        view.unexpected = 1  # type: ignore[attr-defined]

"""Пути отмены отвечают модели на отменённые вызовы (P2-38, источник 2).

Найдено на живых прогонах `sess_ba92d6fb021f` и `sess_daac2d9d9ee8`: вызов,
приостановленный на запросе разрешения, после `session/cancel` помечался
`cancelled`, но `role: tool` для него не появлялся никогда. Фикс прерванного
батча (источник 1) здесь не работает по построению — отмена происходит вне
`process_batch`, остатка батча нет.

Инвариант тот же: контракт LLM-API требует `role: tool` на каждый `tool_call_id`
из assistant-сообщения, а шаг 6 ACP `05-Prompt Turn` — отправлять результаты
обратно в модель.
"""

from __future__ import annotations

import pytest

from codelab.server.domain.conversation import ConversationMessage
from codelab.server.domain.session import Session as DomainSession
from codelab.server.domain.session import TurnState
from codelab.server.domain.value_objects import MessageRole
from codelab.server.mapping.session_mapper import SessionMapper
from codelab.server.models import HistoryMessage
from codelab.server.protocol.handlers.session import _cleanup_session_state
from codelab.server.protocol.handlers.tool_call_handler import ToolCallHandler
from codelab.server.storage.document import ActiveTurnState, SessionDocument, ToolCallState
from tests.server._domain_sessions import make_domain_session


def _session_with_pending_call(status: str = "pending") -> SessionDocument:
    session = SessionDocument(session_id="s", cwd="/tmp", mcp_servers=[])
    session.tool_calls["call_001"] = ToolCallState(
        tool_call_id="call_001",
        title="terminal/create",
        kind="execute",
        status=status,
        tool_call_id_from_llm="chatcmpl-tool-abc",
    )
    session.history.append(
        HistoryMessage(
            role="assistant",
            text="",
            tool_calls=[{"id": "chatcmpl-tool-abc", "name": "terminal_create", "arguments": {}}],
        )
    )
    return session


def _answers(session: DomainSession) -> list[ConversationMessage]:
    """Ответы `role: tool` доменной сессии — путь переключения теперь на агрегате."""
    return [m for m in session.history.get_messages() if m.role == MessageRole.TOOL]


def _domain_session_with_pending_call(status: str = "pending") -> DomainSession:
    """Тот же сценарий доменным агрегатом — через настоящий маппер.

    `cancel_active_tools` переведён на агрегат вместе с транзакцией
    `session/cancel` (фаза D ADR-006), поэтому проверять его на wire-DTO больше
    нельзя.
    """
    return SessionMapper.to_domain(_session_with_pending_call(status))


def _domain_answers(session: DomainSession) -> list[ConversationMessage]:
    return [m for m in session.history.get_messages() if m.role == MessageRole.TOOL]


class TestTurnCancelAnswersToolCalls:
    def test_cancel_active_tools_answers_with_llm_id(self) -> None:
        """Ответ адресуется id, который прислал LLM, иначе он не сматчится."""
        session = _domain_session_with_pending_call()

        notifications = ToolCallHandler().cancel_active_tools(session, "s")

        assert len(notifications) == 1
        answers = _domain_answers(session)
        assert len(answers) == 1
        assert answers[0].tool_call_id == "chatcmpl-tool-abc"
        assert "отменён" in answers[0].content.text

    def test_cancel_active_tools_answers_in_progress_call(self) -> None:
        session = _domain_session_with_pending_call(status="in_progress")

        ToolCallHandler().cancel_active_tools(session, "s")

        assert len(_domain_answers(session)) == 1

    def test_terminal_call_is_not_answered_twice(self) -> None:
        """Уже завершённый вызов не отменяется и второго ответа не получает."""
        session = _domain_session_with_pending_call(status="completed")

        notifications = ToolCallHandler().cancel_active_tools(session, "s")

        assert notifications == []
        assert _domain_answers(session) == []

    def test_answer_falls_back_to_acp_id(self) -> None:
        session = _domain_session_with_pending_call()
        session.tool_calls.update("call_001", tool_call_id_from_llm=None)

        ToolCallHandler().cancel_active_tools(session, "s")

        assert _domain_answers(session)[0].tool_call_id == "call_001"


class TestSessionSwitchAnswersToolCalls:
    def test_cleanup_answers_pending_call(self) -> None:
        """Переключение сессии тоже не оставляет вызов без ответа."""
        session = _domain_session_with_pending_call()
        session.active_turn = TurnState(prompt_request_id="req_1", session_id="s")

        _cleanup_session_state(session)

        answers = _answers(session)
        assert len(answers) == 1
        assert answers[0].tool_call_id == "chatcmpl-tool-abc"
        assert "переключена" in answers[0].content.text
        assert session.tool_calls.get("call_001").status.value == "cancelled"

    def test_cleanup_keeps_history_consistent_with_events(self) -> None:
        """Отмена уходит и в реплей клиенту, и в историю модели — в одной копии."""
        session = _domain_session_with_pending_call()

        _cleanup_session_state(session)

        replayed = [
            e
            for e in session.runtime.events_history
            if e.get("event") == "tool_call_status_changed"
        ]
        assert len(replayed) == 1
        assert replayed[0]["data"]["status"] == "cancelled"
        assert len(_answers(session)) == 1


class TestHistorySeamParityForToolResult:
    """Сейм `add_tool_result` парен на wire и в домене (фаза B ADR-006)."""

    def test_wire_and_domain_records_are_equivalent(self) -> None:
        from codelab.server.domain.session import Session, SessionConfig
        from codelab.server.domain.value_objects import SessionId
        from codelab.server.mapping.history_mapper import HistoryMapper

        wire = SessionDocument(session_id="s", cwd="/tmp", mcp_servers=[])
        wire.add_tool_result("llm_1", "результат")

        domain = Session(id=SessionId("s"), config=SessionConfig(cwd="/tmp"))
        domain.add_tool_result("llm_1", "результат")

        mapped = HistoryMapper.to_protocol(domain.history.get_messages()[0])

        # Формы больше не две: wire-сейм кладёт ту же модель, что отдаёт маппер
        # от доменного сейма (ADR-006, фаза D шаг 4 — снятие союза).
        assert (wire.history[0].role, wire.history[0].tool_call_id, wire.history[0].content) == (
            "tool",
            "llm_1",
            "результат",
        )
        assert (mapped.role, mapped.tool_call_id, mapped.content) == (
            "tool",
            "llm_1",
            "результат",
        )

    @pytest.mark.parametrize("content", ["", "многострочный\nтекст"])
    def test_domain_roundtrip_preserves_content(self, content: str) -> None:
        from codelab.server.domain.session import Session, SessionConfig
        from codelab.server.domain.value_objects import SessionId
        from codelab.server.mapping.history_mapper import HistoryMapper

        domain = Session(id=SessionId("s"), config=SessionConfig(cwd="/tmp"))
        domain.add_tool_result("llm_1", content)
        message = domain.history.get_messages()[0]

        restored = HistoryMapper.to_domain(HistoryMapper.to_protocol(message))

        assert restored.content.text == content
        assert restored.tool_call_id == "llm_1"


class TestDeferredBatchIsAnsweredWhenTurnEnds:
    """Отложенный хвост батча не теряется при обрыве turn'а (P2-40 → P2-38).

    Найдено на живом прогоне `sess_a98dab30f7c3`: 9 вызовов, 8 ответов. Отмена
    пришла, когда в `pending_batch` лежал вызов `analysis_options.yaml`; turn был
    очищен вместе с хвостом, и вызов остался без `role: tool` навсегда. Шов внесён
    правкой P2-40: до неё хвост отвечался сразу, теперь он живёт в состоянии и
    требует явного ответа на каждом пути обрыва.
    """

    def _session_with_deferred_batch(self) -> DomainSession:
        session = make_domain_session(session_id="s", cwd="/tmp", mcp_servers=[])
        session.active_turn = TurnState(prompt_request_id="req_1", session_id="s")
        session.active_turn.pending_batch = [
            {"id": "llm_2", "name": "fs_read_text_file", "arguments": {"path": "B.md"}},
            {"id": "llm_3", "name": "fs_read_text_file", "arguments": {"path": "C.md"}},
        ]
        return session

    def test_cancel_answers_deferred_batch(self) -> None:
        session = self._session_with_deferred_batch()

        answered = session.answer_deferred_batch(reason="turn отменён пользователем")

        assert answered == 2
        ids = {m.tool_call_id for m in _answers(session)}
        assert ids == {"llm_2", "llm_3"}
        assert all("отменён" in m.content.text for m in _answers(session))
        # Хвост снят: иначе он всплыл бы при следующем resume
        assert session.active_turn.pending_batch == []

    def test_permission_reject_answers_deferred_batch(self) -> None:

        session = self._session_with_deferred_batch()

        session.answer_deferred_batch(reason="в разрешении отказано")

        assert len(_answers(session)) == 2
        assert all("отказано" in m.content.text for m in _answers(session))

    def test_session_switch_answers_deferred_batch(self) -> None:
        session = self._session_with_deferred_batch()

        _cleanup_session_state(session)

        ids = {m.tool_call_id for m in _answers(session)}
        assert ids == {"llm_2", "llm_3"}
        assert session.active_turn is None

    def test_empty_batch_writes_nothing(self) -> None:

        session = make_domain_session(session_id="s", cwd="/tmp", mcp_servers=[])
        session.active_turn = TurnState(prompt_request_id="req_1", session_id="s")

        assert session.answer_deferred_batch(reason="неважно") == 0
        assert _answers(session) == []

    def test_call_without_id_is_skipped_not_crashed(self) -> None:
        """Битая запись в хвосте не должна ронять путь отмены."""

        session = self._session_with_deferred_batch()
        session.active_turn.pending_batch.append({"name": "fs_read_text_file"})

        assert session.answer_deferred_batch(reason="turn отменён пользователем") == 2


class TestRealPathsAnswerDeferredBatch:
    """Проверка, что настоящие пути обрыва зовут ответ на хвост, а не только хелпер."""

    def _session_with_deferred_batch(self, tool_call_id: str = "call_001") -> SessionDocument:
        session = SessionDocument(session_id="s", cwd="/tmp", mcp_servers=[])
        session.set_config_value("mode", "standard")
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="s",
            permission_request_id="perm_1",
            permission_tool_call_id=tool_call_id,
        )
        session.active_turn.pending_batch = [
            {"id": "llm_2", "name": "fs_read_text_file", "arguments": {"path": "B.md"}}
        ]
        session.tool_calls[tool_call_id] = ToolCallState(
            tool_call_id=tool_call_id,
            title="fs/read_text_file",
            kind="read",
            status="pending",
            tool_call_id_from_llm="llm_1",
        )
        return session

    def test_permission_reject_path_answers_tail(self) -> None:
        """Отказ в разрешении обрывает turn — хвост обязан быть отвечен."""
        from codelab.server.protocol.handlers.prompt.permission_response import (
            resolve_permission_response_impl,
        )

        # Путь переведён на доменный агрегат вместе с транзакцией
        # permission-response (фаза D ADR-006)
        session = SessionMapper.to_domain(self._session_with_deferred_batch())

        outcome = resolve_permission_response_impl(
            session=session,
            permission_request_id="perm_1",
            result={"outcome": {"outcome": "selected", "optionId": "reject_once"}},
        )

        assert outcome is not None
        tail = [m for m in _domain_answers(session) if m.tool_call_id == "llm_2"]
        assert len(tail) == 1
        assert "отказано" in tail[0].content.text

    def test_permission_allow_path_keeps_tail_for_resume(self) -> None:
        """Разрешение НЕ должно отвечать на хвост: он будет выполнен."""
        from codelab.server.protocol.handlers.prompt.permission_response import (
            resolve_permission_response_impl,
        )

        session = SessionMapper.to_domain(self._session_with_deferred_batch())

        resolve_permission_response_impl(
            session=session,
            permission_request_id="perm_1",
            result={"outcome": {"outcome": "selected", "optionId": "allow_once"}},
        )

        assert _domain_answers(session) == []
        assert session.active_turn is not None
        assert [c["id"] for c in session.active_turn.pending_batch] == ["llm_2"]

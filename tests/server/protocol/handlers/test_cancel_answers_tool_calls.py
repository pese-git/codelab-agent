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
from tests.server._domain_sessions import make_domain_session, wire_journal


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

    def test_in_flight_call_is_answered_by_its_executor_not_by_cancel(self) -> None:
        """Вызов в полёте метёлка не отвечает — за него ответит исполнитель (P2-63).

        Тест кодировал прежнее правило («отмена отвечает и за `in_progress`») и
        заменён осознанно: на живом прогоне 2026-08-10 это правило давало **два**
        `role: tool` на один `answer_id` — обобщённый текст метёлки и правдивый
        текст исполнителя, который разворачивается штатно (отмена RPC
        кооперативная). Побеждает первый ответ, поэтому промолчать здесь —
        единственный способ пропустить вперёд правдивый.
        """
        session = _domain_session_with_pending_call(status="in_progress")

        notifications = ToolCallHandler().cancel_active_tools(session, "s")

        assert _domain_answers(session) == []
        # Нотификация обязана остаться: пропускается только ответ модели, иначе
        # клиент не узнал бы об отмене из ответа на `session/cancel`.
        assert len(notifications) == 1
        assert session.tool_calls.get("call_001").status.value == "cancelled"

    def test_pending_call_is_still_answered_by_cancel(self) -> None:
        """Приостановленный вызов отвечает метёлка: исполнителя у него нет.

        Граница правила владения. Именно этот случай — вызов, вставший на запросе
        разрешения, — и был дефектом P2-38, ради которого путь написан; он несёт
        статус `pending`, а не `in_progress`, поэтому сужение предиката его не
        задевает.
        """
        session = _domain_session_with_pending_call(status="pending")

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
            for e in wire_journal(session)
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

        answered = ToolCallHandler().answer_unexecuted_tool_calls(
            session, session.take_deferred_batch_ids(), reason="turn отменён пользователем"
        )

        assert answered == 2
        ids = {m.tool_call_id for m in _answers(session)}
        assert ids == {"llm_2", "llm_3"}
        assert all("отменён" in m.content.text for m in _answers(session))
        # Хвост снят: иначе он всплыл бы при следующем resume
        assert session.active_turn.pending_batch == []

    def test_permission_reject_answers_deferred_batch(self) -> None:

        session = self._session_with_deferred_batch()

        ToolCallHandler().answer_unexecuted_tool_calls(
            session, session.take_deferred_batch_ids(), reason="в разрешении отказано"
        )

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

        assert (
            ToolCallHandler().answer_unexecuted_tool_calls(
                session, session.take_deferred_batch_ids(), reason="неважно"
            )
            == 0
        )
        assert _answers(session) == []

    def test_call_without_id_is_skipped_not_crashed(self) -> None:
        """Битая запись в хвосте не должна ронять путь отмены."""

        session = self._session_with_deferred_batch()
        session.active_turn.pending_batch.append({"name": "fs_read_text_file"})

        assert (
            ToolCallHandler().answer_unexecuted_tool_calls(
                session, session.take_deferred_batch_ids(), reason="turn отменён пользователем"
            )
            == 2
        )


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


class TestSingleAnswerPerToolCall:
    """Контракт LLM-API: ровно один `role: tool` на `tool_call_id` (P2-63).

    Найдено живьём (`sess_8dd8e1a96105`, 2026-08-10): вызов `terminal/wait_for_exit`
    получил два ответа при одном объявлении в assistant-сообщении — метёлка отмены
    ответила за вызов, который в этот момент исполнялся, а следом исполнитель
    ответил за него сам. История с дублем ушла в модель следующим промптом.

    Гарантия живёт в домене, а не в дисциплине шести писателей: сейм идемпотентен
    по `tool_call_id`. Она работает потому, что писатели сериализованы —
    `SessionCommands.apply` применяет команду к свежему агрегату под блокировкой
    сессии, — а не потому, что они договорились.
    """

    def test_second_answer_to_same_call_is_suppressed(self) -> None:
        session = _domain_session_with_pending_call()

        session.add_tool_result("chatcmpl-tool-abc", "первый ответ")
        session.add_tool_result("chatcmpl-tool-abc", "второй ответ")

        answers = _domain_answers(session)
        assert len(answers) == 1
        # Побеждает первый: он уже мог уехать клиенту и в prompt cache.
        assert answers[0].content.text == "первый ответ"

    def test_different_calls_are_not_confused(self) -> None:
        """Идемпотентность по id, а не «один ответ на сессию»."""
        session = _domain_session_with_pending_call()

        session.add_tool_result("chatcmpl-tool-abc", "ответ A")
        session.add_tool_result("chatcmpl-tool-xyz", "ответ B")

        assert [m.tool_call_id for m in _domain_answers(session)] == [
            "chatcmpl-tool-abc",
            "chatcmpl-tool-xyz",
        ]

    def test_cancel_then_executor_answer_yields_one_record(self) -> None:
        """Сценарий прогона целиком: отмена вызова в полёте + ответ исполнителя.

        Две меры проверяются вместе, потому что живьём они и встретились: метёлка
        молчит (выбор текста), а идемпотентность страхует на случай, когда вызов
        в полёте статуса `in_progress` не несёт — сегодня его выставляет только
        `terminal/wait_for_exit`.
        """
        session = _domain_session_with_pending_call(status="in_progress")

        ToolCallHandler().cancel_active_tools(session, "s")
        # Исполнитель разворачивает своё ожидание и пишет правдивый текст.
        session.add_tool_result(
            "chatcmpl-tool-abc",
            "Ожидание завершения терминала отменено пользователем: term_1",
        )

        answers = _domain_answers(session)
        assert len(answers) == 1
        assert "терминала" in answers[0].content.text


class TestOrphanedInFlightCallIsAnsweredOnLoad:
    """Вызов в полёте, чей исполнитель умер, обязан получить ответ при загрузке.

    Найдено живым прогоном `sess_5fee83e9bc32` (2026-08-13): `call_034`
    (`terminal/wait_for_exit`) ушёл в `in_progress` за 3 мс до смерти процесса,
    следующий `session/cancel` пометил его `cancelled` и промолчал — предикат
    `is_in_flight` пропускает ответ вперёд исполнителю (P2-63), а исполнителя уже
    нет. Итог: 41 заявленный вызов против 40 ответов, дефект лежал на диске и
    переживал рестарт. Оборотная сторона правки P2-63.
    """

    def test_in_flight_call_is_cancelled_and_answered(self) -> None:
        session = SessionMapper.to_domain(_session_with_pending_call("in_progress"))

        _cleanup_session_state(session)

        call = session.tool_calls.get("call_001")
        assert call is not None
        # Вечный `in_progress` в документе сессии без процесса — второй след той же
        # причины, и он снимается здесь же.
        assert call.is_terminal
        answers = _answers(session)
        assert [m.tool_call_id for m in answers] == ["chatcmpl-tool-abc"]
        assert "прервано" in answers[0].content.text

    def test_answer_is_journalled(self) -> None:
        """Текст ответа обязан попасть в журнал: статус метёлка пишет без контента."""
        session = SessionMapper.to_domain(_session_with_pending_call("in_progress"))

        _cleanup_session_state(session)

        events = [
            e
            for e in wire_journal(session)
            if e["event"] == "tool_call_answered"
        ]
        assert len(events) == 1
        assert events[0]["data"]["tool_call_id"] == "chatcmpl-tool-abc"
        assert events[0]["data"]["text"] == _answers(session)[0].content.text

    def test_pending_call_keeps_its_reason(self) -> None:
        """«Не начинался» и «прервано» — разные факты, текст их различает."""
        session = SessionMapper.to_domain(_session_with_pending_call("pending"))

        _cleanup_session_state(session)

        assert "переключена" in _answers(session)[0].content.text


class TestCancelAnswerIsJournalled:
    """Ответ метёлки `session/cancel` тоже обязан быть событием журнала.

    Измерено на `sess_8fa73fe08f55` (2026-08-13): 25 вызовов, 25 ответов, дублей 0 —
    но текст двух ответов (`call_003`, `call_009`) журналом не описан: статус метёлка
    выставляет без контента, а ответ писала напрямую. Последняя дыра выводимости
    `history` перед шагом 4 ADR-008.
    """

    def test_answer_text_is_derivable_from_journal(self) -> None:
        session = _domain_session_with_pending_call()

        ToolCallHandler().cancel_active_tools(session, "s")

        events = [
            e
            for e in wire_journal(session)
            if e["event"] == "tool_call_answered"
        ]
        assert len(events) == 1
        assert events[0]["data"]["tool_call_id"] == "chatcmpl-tool-abc"
        assert events[0]["data"]["text"] == _domain_answers(session)[0].content.text

    def test_in_flight_call_is_still_left_to_its_executor(self) -> None:
        """Правка P2-63 не тронута: за вызов в полёте метёлка по-прежнему молчит."""
        session = _domain_session_with_pending_call("in_progress")

        ToolCallHandler().cancel_active_tools(session, "s")

        assert _domain_answers(session) == []
        assert not [
            e
            for e in wire_journal(session)
            if e["event"] == "tool_call_answered"
        ]

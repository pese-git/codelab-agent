"""Ответ на agent->client RPC доживает до диска (транзакция 7 фазы D, ADR-006).

До этой транзакции путь вёл себя как permission-response до P1-49: роутер находил
сессию, применял ответ и возвращал outcome — записи не было. Терялись статус
вызова, снятый `pending_external_request` и финал turn'а. Бил этот дефект реже,
потому что путь директивный (`pending_client_request` заводит только директива
`/tool` и цепочка terminal-followup'ов), но класс тот же.

Проверка на `JsonFileStorage`: на `InMemoryStorage` backend отдаёт сам хранимый
объект, поэтому «забыли записать» невидимо по построению.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from codelab.server.messages import ACPMessage
from codelab.server.protocol.pending_registry import PendingRequestRegistry
from codelab.server.protocol.response_router import ResponseRouter
from codelab.server.storage import JsonFileStorage, SessionRepository
from codelab.server.storage.document import (
    ActiveTurnState,
    ClientRuntimeCapabilities,
    PendingClientRequestState,
    SessionDocument,
    ToolCallState,
)


def _session_awaiting(
    kind: str, *, prompt_request_id: str | None = "req_1", **pending: Any
) -> SessionDocument:
    session = SessionDocument(session_id="sess_x", cwd="/w", mcp_servers=[])
    session.tool_calls["call_001"] = ToolCallState(
        tool_call_id="call_001",
        title="fs/read_text_file",
        kind="read",
        status="in_progress",
        tool_call_id_from_llm="llm_1",
    )
    session.tool_call_counter = 1
    session.active_turn = ActiveTurnState(
        prompt_request_id=prompt_request_id,
        session_id="sess_x",
        pending_client_request=PendingClientRequestState(
            request_id="rpc_1",
            kind=kind,
            tool_call_id="call_001",
            path="file.txt",
            **pending,
        ),
    )
    return session


async def _respond(storage: JsonFileStorage, result: Any, error: Any = None) -> Any:
    router = ResponseRouter(
        storage=storage,
        repository=SessionRepository(backend=storage),
        pending_registry=PendingRequestRegistry(),
    )
    message = (
        ACPMessage.error_response("rpc_1", code=-32000, message=error)
        if error is not None
        else ACPMessage.response("rpc_1", result)
    )
    return await router.handle_client_response(message)


@pytest.mark.asyncio
class TestClientRpcResponseReachesDisk:
    async def test_fs_read_completion_is_persisted(self, tmp_path: Path) -> None:
        """Завершение вызова и снятие turn'а обязаны оказаться на диске."""
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session_awaiting("fs_read"))

        outcome = await _respond(storage, {"content": "содержимое файла"})

        stored = await storage.load_session("sess_x")
        assert stored is not None
        assert stored.tool_calls["call_001"].status == "completed"
        assert stored.active_turn is None, "turn завершён — active_turn не должен остаться"
        assert [m.id for m in outcome.followup_responses] == ["req_1"]

    async def test_turn_without_request_id_is_cleared_too(self, tmp_path: Path) -> None:
        """Turn без идентификатора исходного запроса снимается тоже (P2-54).

        Прежде guard в `_finalize_turn` выходил раньше снятия, и на диске оставался
        `active_turn` с фазой `waiting_client_rpc` у turn'а, чей запрос уже разрешён.
        Отвечать некому — followup пуст, но turn обязан быть снят.
        """
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session_awaiting("fs_read", prompt_request_id=None))

        outcome = await _respond(storage, {"content": "содержимое файла"})

        stored = await storage.load_session("sess_x")
        assert stored is not None
        assert stored.tool_calls["call_001"].status == "completed"
        assert stored.active_turn is None, "turn без request_id обязан сниматься тоже"
        assert outcome.followup_responses == []

    async def test_terminal_chain_persists_next_pending(self, tmp_path: Path) -> None:
        """Цепочка terminal: следующий ожидаемый запрос переживает ответ.

        Ответ на `terminal/output` приходит отдельным запросом и загружает сессию
        заново, поэтому следующий `pending` обязан быть на диске — иначе цепочка
        обрывается и turn висит.
        """
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session_awaiting("terminal_output", terminal_id="term_1"))

        outcome = await _respond(storage, {"output": "готово", "truncated": False})

        stored = await storage.load_session("sess_x")
        assert stored is not None
        assert stored.active_turn is not None
        pending = stored.active_turn.pending_client_request
        assert pending is not None
        assert pending.kind == "terminal_wait_for_exit"
        assert pending.terminal_output == "готово"
        # Клиенту отправлен следующий запрос цепочки
        assert [m.method for m in outcome.notifications] == ["terminal/wait_for_exit"]

    async def test_error_response_persists_failure(self, tmp_path: Path) -> None:
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session_awaiting("fs_read"))

        await _respond(storage, None, error="not found")

        stored = await storage.load_session("sess_x")
        assert stored is not None
        assert stored.tool_calls["call_001"].status == "failed"
        assert stored.active_turn is None

    async def test_single_write_per_response(self, tmp_path: Path) -> None:
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session_awaiting("fs_read"))
        before = await storage.load_session("sess_x")
        assert before is not None

        await _respond(storage, {"content": "ok"})

        stored = await storage.load_session("sess_x")
        assert stored is not None
        assert stored.revision == before.revision + 1

    async def test_unknown_request_does_not_write(self, tmp_path: Path) -> None:
        """Чужой id не должен трогать сессию (и её `updated_at`)."""
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session_awaiting("fs_read"))
        before = await storage.load_session("sess_x")
        assert before is not None

        router = ResponseRouter(
            storage=storage,
            repository=SessionRepository(backend=storage),
            pending_registry=PendingRequestRegistry(),
        )
        await router.handle_client_response(ACPMessage.response("rpc_другой", {"content": "ok"}))

        stored = await storage.load_session("sess_x")
        assert stored is not None
        assert stored.revision == before.revision
        assert stored.updated_at == before.updated_at


def _session_via_production_builder(kind: str) -> tuple[SessionDocument, list[Any]]:
    """Состояние готовит тот же код, что в проде, а не фикстура «как надо».

    Подготовка идёт доменным агрегатом — носителем turn-пути (ADR-006, фаза D шаг
    3), а возвращается wire-документ: именно он уезжает на диск, и дальше тест
    сверяет диск с тем, что ушло клиенту.
    """
    from codelab.server.domain.session import TurnState
    from codelab.server.mapping.session_mapper import SessionMapper
    from codelab.server.protocol.handlers.prompt import build_fs_client_request
    from codelab.server.protocol.state import PromptDirectives

    state = SessionDocument(session_id="sess_x", cwd="/w", mcp_servers=[])
    state.runtime_capabilities = ClientRuntimeCapabilities(
        fs_read=True, fs_write=True, terminal=True
    )
    session = SessionMapper.to_domain(state)
    session.active_turn = TurnState(prompt_request_id="req_1", session_id="sess_x")
    directives = (
        PromptDirectives(fs_read_path="/w/file.txt")
        if kind == "fs_read"
        else PromptDirectives(fs_write_path="/w/file.txt", fs_write_content="новое")
    )
    prepared = build_fs_client_request(session=session, session_id="sess_x", directives=directives)
    assert prepared is not None
    session.active_turn.pending_external_request = prepared.pending_request
    return SessionMapper.to_protocol(session), prepared.messages


class TestClientRpcCallStartsInProgress:
    """Вызов работает с момента отправки RPC — `pending` для него не бывает (P2-55)."""

    @pytest.mark.parametrize("kind", ["fs_read", "fs_write"])
    def test_call_starts_in_progress_not_pending(self, kind: str) -> None:
        session, messages = _session_via_production_builder(kind)

        assert session.tool_calls["call_001"].status == "in_progress"
        created = messages[0].params["update"]
        assert created["sessionUpdate"] == "tool_call"
        assert created["status"] == "in_progress", "wire и состояние обязаны совпадать сразу"


@pytest.mark.asyncio
class TestStatusOnDiskMatchesWhatClientWasTold:
    """Статус на диске совпадает с тем, что ушло клиенту (P2-55).

    Гейт выше был зелёным, потому что фикстура сама ставила `in_progress`. Прод
    создавал вызов `pending`, завершение упиралось в запрет `pending → completed`,
    и на диске оставался `pending` при `completed` у клиента.
    """

    async def test_fs_read_status_on_disk_equals_status_sent_to_client(
        self, tmp_path: Path
    ) -> None:
        """Сквозной гейт: что сказали клиенту, то и на диске."""
        session, _ = _session_via_production_builder("fs_read")
        storage = JsonFileStorage(tmp_path)
        session.active_turn.pending_client_request.request_id = "rpc_1"  # type: ignore[union-attr]
        await storage.save_session(session)

        outcome = await _respond(storage, {"content": "содержимое"})

        sent = [
            m.params["update"]["status"]
            for m in outcome.notifications
            if m.params and m.params.get("update", {}).get("sessionUpdate") == "tool_call_update"
        ]
        stored = await storage.load_session("sess_x")
        assert stored is not None
        assert sent == ["completed"]
        assert stored.tool_calls["call_001"].status == "completed"
        assert stored.active_turn is None

    async def test_rejected_transition_does_not_lie_to_client(self, tmp_path: Path) -> None:
        """Отклонённый переход — молчание, а не `completed` при своём статусе на диске."""
        session = _session_awaiting("fs_read")
        session.tool_calls["call_001"].status = "cancelled"
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(session)

        outcome = await _respond(storage, {"content": "содержимое"})

        statuses = [
            m.params["update"]["status"]
            for m in outcome.notifications
            if m.params and m.params.get("update", {}).get("sessionUpdate") == "tool_call_update"
        ]
        stored = await storage.load_session("sess_x")
        assert stored is not None
        assert statuses == [], "перехода не было — нотификации быть не должно"
        assert stored.tool_calls["call_001"].status == "cancelled"

    async def test_unknown_call_still_notifies(self, tmp_path: Path) -> None:
        """Вызова нет в состоянии — путь отказа обязан уведомить клиента (не менялось)."""
        session = _session_awaiting("fs_read")
        del session.tool_calls["call_001"]
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(session)

        outcome = await _respond(storage, "невалидный ответ")

        statuses = [
            m.params["update"]["status"]
            for m in outcome.notifications
            if m.params and m.params.get("update", {}).get("sessionUpdate") == "tool_call_update"
        ]
        assert statuses == ["failed"]

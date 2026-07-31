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
from codelab.server.protocol.state import (
    ActiveTurnState,
    PendingClientRequestState,
    SessionState,
    ToolCallState,
)
from codelab.server.storage import JsonFileStorage, SessionRepository


def _session_awaiting(kind: str, **pending: Any) -> SessionState:
    session = SessionState(session_id="sess_x", cwd="/w", mcp_servers=[])
    session.tool_calls["call_001"] = ToolCallState(
        tool_call_id="call_001",
        title="fs/read_text_file",
        kind="read",
        status="in_progress",
        tool_call_id_from_llm="llm_1",
    )
    session.tool_call_counter = 1
    session.active_turn = ActiveTurnState(
        prompt_request_id="req_1",
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

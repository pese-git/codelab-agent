"""Решение по permission-request доживает до диска (P1-49, фаза D ADR-006).

До этой транзакции путь ответа на `session/request_permission` мутировал копию,
которую **никто не сохранял**: `ResponseRouter` находил сессию, применял решение и
возвращал outcome, а записи не было ни в роутере, ни дальше. Терялось три вещи:
запомненная политика (`allow_always`/`reject_always`), снятые permission-идентификаторы
в `active_turn` и статус вызова. Последнее и давало
`session_loaded_with_orphaned_permission_request` при каждом перезапуске (P2-46).

Проверка идёт на `JsonFileStorage`, а не на `InMemoryStorage`, — и это не деталь:
in-memory backend отдаёт сам хранимый объект, поэтому мутации копии там выглядят
сохранёнными, и дефект класса «забыли записать» на нём невидим (та же оговорка, что
у сверки ревизий в ADR-007).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from codelab.server.messages import ACPMessage
from codelab.server.models import HistoryMessage
from codelab.server.protocol.pending_registry import PendingRequestRegistry
from codelab.server.protocol.response_router import ResponseRouter
from codelab.server.storage import JsonFileStorage, SessionRepository
from codelab.server.storage.document import ActiveTurnState, SessionDocument, ToolCallState


def _session_awaiting_permission() -> SessionDocument:
    session = SessionDocument(session_id="sess_x", cwd="/w", mcp_servers=[])
    session.tool_calls["call_001"] = ToolCallState(
        tool_call_id="call_001",
        title="fs/read_text_file",
        kind="read",
        status="pending",
        tool_call_id_from_llm="llm_1",
    )
    session.tool_call_counter = 1
    session.history.append(
        HistoryMessage(
            role="assistant",
            text="",
            tool_calls=[
                {"id": "llm_1", "name": "fs_read_text_file", "arguments": {}},
                {"id": "llm_2", "name": "fs_read_text_file", "arguments": {}},
            ],
        )
    )
    session.active_turn = ActiveTurnState(
        prompt_request_id="req_1",
        session_id="sess_x",
        permission_request_id="perm_1",
        permission_tool_call_id="call_001",
        phase="awaiting_permission",
        pending_batch=[{"id": "llm_2", "name": "fs_read_text_file", "arguments": {}}],
    )
    return session


async def _respond(storage: JsonFileStorage, option: str) -> Any:
    router = ResponseRouter(
        storage=storage,
        repository=SessionRepository(backend=storage),
        pending_registry=PendingRequestRegistry(),
    )
    return await router.handle_client_response(
        ACPMessage.response("perm_1", {"outcome": {"outcome": "selected", "optionId": option}})
    )


@pytest.mark.asyncio
class TestPermissionDecisionReachesDisk:
    async def test_remembered_policy_is_persisted(self, tmp_path: Path) -> None:
        """`allow_always` обязан пережить запрос: иначе следующий вызов снова спросит.

        Именно это наблюдалось живьём: 41 запрос разрешения за сессию при пустом
        `permission_policy` на диске.
        """
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session_awaiting_permission())

        await _respond(storage, "allow_always")

        stored = await storage.load_session("sess_x")
        assert stored is not None
        assert stored.permission_policy == {"read": "allow_always"}

    async def test_permission_ids_are_cleared_on_disk(self, tmp_path: Path) -> None:
        """Причина P2-46: снятые идентификаторы не доживали до диска."""
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session_awaiting_permission())

        await _respond(storage, "allow_once")

        stored = await storage.load_session("sess_x")
        assert stored is not None
        assert stored.active_turn is not None
        assert stored.active_turn.permission_request_id is None
        assert stored.active_turn.permission_tool_call_id is None
        # Turn продолжается: вызов исполнит фоновая задача
        assert stored.tool_calls["call_001"].status == "in_progress"

    async def test_allowed_call_status_matches_notification(self, tmp_path: Path) -> None:
        """Статус на диске совпадает с тем, что отправлено клиенту."""
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session_awaiting_permission())

        outcome = await _respond(storage, "allow_once")

        statuses = [
            (m.params or {}).get("update", {}).get("status")
            for m in outcome.notifications
            if (m.params or {}).get("update", {}).get("sessionUpdate") == "tool_call_update"
        ]
        stored = await storage.load_session("sess_x")
        assert stored is not None
        assert statuses == ["in_progress"]
        assert stored.tool_calls["call_001"].status == "in_progress"
        assert outcome.pending_tool_execution is not None
        assert outcome.pending_tool_execution.tool_call_id == "call_001"

    async def test_denial_persists_cancel_and_answers_deferred_tail(self, tmp_path: Path) -> None:
        """Отказ обрывает turn: всё, что при этом решено, обязано быть на диске."""
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session_awaiting_permission())

        outcome = await _respond(storage, "reject_always")

        stored = await storage.load_session("sess_x")
        assert stored is not None
        assert stored.active_turn is None, "turn оборван — active_turn не должен остаться"
        assert stored.tool_calls["call_001"].status == "cancelled"
        assert stored.permission_policy == {"read": "reject_always"}
        # Хвост батча (P2-40) отвечен, иначе вызов остался бы без `role: tool` (P2-38)
        answered = [
            m.tool_call_id
            for m in stored.history
            if not isinstance(m, dict) and m.role == "tool"
        ]
        assert answered == ["llm_2"]
        assert [m.id for m in outcome.followup_responses] == ["req_1"]

    async def test_single_write_per_response(self, tmp_path: Path) -> None:
        """Область транзакции пишет один раз — ревизия растёт на единицу."""
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session_awaiting_permission())
        before = await storage.load_session("sess_x")
        assert before is not None

        await _respond(storage, "allow_once")

        stored = await storage.load_session("sess_x")
        assert stored is not None
        assert stored.revision == before.revision + 1

    async def test_unknown_request_does_not_write(self, tmp_path: Path) -> None:
        """Чужой permission-id не должен трогать сессию (и её `updated_at`)."""
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session_awaiting_permission())
        before = await storage.load_session("sess_x")
        assert before is not None

        router = ResponseRouter(
            storage=storage,
            repository=SessionRepository(backend=storage),
            pending_registry=PendingRequestRegistry(),
        )
        outcome = await router.handle_client_response(
            ACPMessage.response("perm_другой", {"outcome": {"outcome": "cancelled"}})
        )

        stored = await storage.load_session("sess_x")
        assert stored is not None
        assert outcome.notifications == []
        assert stored.revision == before.revision
        assert stored.updated_at == before.updated_at

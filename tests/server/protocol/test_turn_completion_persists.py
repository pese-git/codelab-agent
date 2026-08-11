"""Снятие turn'а при штатном завершении доезжает до диска (P2-54).

Дефект был измерим, а не выводим: `turn_finished cause=completed` в логе — и
`active_turn` с `phase: running` в документе (живой прогон 2026-08-11,
`sess_1fb7b8156367`, ревизия 336). Сессия грузилась read-only и не сохранялась,
поэтому решение о снятии жило только в памяти; симптом гасил следующий промпт,
снимавший turn как устаревший, а до него враньё переживало и перезапуск процесса,
превращаясь там в «осиротевшее разрешение».

**Хранилище файловое, и это не деталь.** На `InMemoryStorage` тест прошёл бы и до
исправления: бэкенд отдаёт тот же объект, который мутировали, поэтому «мутировали
и не сохранили» на нём невыразимо. Так уже проходил тест ответа отложенному хвосту,
хотя в проде ветка эффекта не давала (P2-42).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codelab.server.protocol.background_executor import BackgroundExecutor
from codelab.server.protocol.session_runtime import SessionRuntimeRegistry
from codelab.server.storage import JsonFileStorage, SessionRepository
from codelab.server.storage.document import ActiveTurnState, SessionDocument


def _executor(storage: JsonFileStorage) -> BackgroundExecutor:
    async def orchestrator_provider() -> None:
        return None

    async def mcp_provider(_session: SessionDocument) -> None:
        return None

    return BackgroundExecutor(
        storage=storage,
        repository=SessionRepository(backend=storage),
        orchestrator_provider=orchestrator_provider,
        mcp_provider=mcp_provider,
        runtime_registry=SessionRuntimeRegistry(),
    )


async def _session_with_open_turn(storage: JsonFileStorage) -> SessionDocument:
    session = SessionDocument(session_id="sess_t", cwd="/work", mcp_servers=[])
    session.active_turn = ActiveTurnState(prompt_request_id="req_1", session_id="sess_t")
    await storage.save_session(session)
    return session


class TestTurnCompletionReachesDisk:
    @pytest.mark.asyncio
    async def test_active_turn_is_gone_from_disk(self, tmp_path: Path) -> None:
        """После штатного завершения документ не хранит закрытый turn."""
        storage = JsonFileStorage(tmp_path)
        await _session_with_open_turn(storage)

        response = await _executor(storage).complete_active_turn("sess_t")

        assert response is not None
        assert response.result == {"stopReason": "end_turn"}

        stored = await JsonFileStorage(tmp_path).load_session("sess_t")
        assert stored is not None
        assert stored.active_turn is None, "снятие turn'а обязано доехать до диска"

    @pytest.mark.asyncio
    async def test_idle_call_writes_nothing(self, tmp_path: Path) -> None:
        """Холостой вызов ревизию не штампует: его делают все три транспорта.

        Транзакция сохраняет безусловно — dirty-трекинга у неё нет по замыслу,
        поэтому «не открывать транзакцию зря» проверяется отдельно.
        """
        storage = JsonFileStorage(tmp_path)
        session = SessionDocument(session_id="sess_t", cwd="/work", mcp_servers=[])
        await storage.save_session(session)
        before = (await JsonFileStorage(tmp_path).load_session("sess_t")).revision

        assert await _executor(storage).complete_active_turn("sess_t") is None

        after = (await JsonFileStorage(tmp_path).load_session("sess_t")).revision
        assert after == before

    @pytest.mark.asyncio
    async def test_missing_session_is_not_resurrected(self, tmp_path: Path) -> None:
        """Удалённую сессию завершение turn'а не воскрешает."""
        storage = JsonFileStorage(tmp_path)

        assert await _executor(storage).complete_active_turn("sess_missing") is None
        assert await JsonFileStorage(tmp_path).load_session("sess_missing") is None

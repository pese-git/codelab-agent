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
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.client_rpc.service import ClientRPCService
from codelab.server.mapping.session_mapper import SessionMapper
from codelab.server.protocol.background_executor import BackgroundExecutor
from codelab.server.protocol.session_runtime import SessionRuntimeRegistry
from codelab.server.protocol.turn_terminals import TurnTerminalReleaser
from codelab.server.rpc_holder import ClientRPCServiceHolder
from codelab.server.storage import JsonFileStorage, SessionRepository
from codelab.server.storage.document import ActiveTurnState, SessionDocument
from codelab.server.tools.executors.terminal_alias_registry import TerminalAliasRegistry


def _executor(
    storage: JsonFileStorage,
    terminal_releaser: TurnTerminalReleaser | None = None,
) -> BackgroundExecutor:
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
        terminal_releaser=terminal_releaser,
    )


async def _session_with_open_turn(storage: JsonFileStorage) -> SessionDocument:
    session = SessionDocument(session_id="sess_t", cwd="/work", mcp_servers=[])
    session.active_turn = ActiveTurnState(prompt_request_id="req_1", session_id="sess_t")
    await storage.save_session(session)
    return session


class TestTurnWithoutRequestIdIsCleared:
    """Turn без идентификатора исходного запроса снимается тоже (P2-54).

    Прежде guard в `finalize_active_turn` выходил раньше снятия, и на диске оставался
    `active_turn` с фазой паузы — ровно симптом, ради которого заведён P2-54. Асимметрия
    была отложена шагом 5.2 ADR-008 как «вопрос для 5.3» и там не закрыта.

    Случай латентный: с Zed промпт всегда приходит запросом с id (`answered=True` в
    `turn_finished`). Но правдивость состояния на диске не может зависеть от того,
    наблюдается ли ложь у сегодняшнего клиента, — и гейта на это поведение не было
    вовсе: снятие guard'а не сломало ни одного теста из 786.
    """

    @pytest.mark.asyncio
    async def test_turn_without_request_id_leaves_no_active_turn(self, tmp_path: Path) -> None:
        storage = JsonFileStorage(tmp_path)
        session = SessionDocument(session_id="sess_t", cwd="/work", mcp_servers=[])
        session.active_turn = ActiveTurnState(prompt_request_id=None, session_id="sess_t")
        await storage.save_session(session)

        # Отвечать некому, поэтому ответа нет — но turn обязан быть снят.
        assert await _executor(storage).complete_active_turn("sess_t") is None

        stored = await JsonFileStorage(tmp_path).load_session("sess_t")
        assert stored is not None
        assert stored.active_turn is None, "turn без request_id обязан сниматься тоже"


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
    async def test_terminal_remainder_is_released_after_the_write(self, tmp_path: Path) -> None:
        """Штатное завершение доводит освобождение остатка до клиента (ADR-008, шаг 5.3).

        Порядок проверяется явно: RPC обязан идти **после** записи снятия turn'а, иначе
        сетевой обмен держал бы блокировку сессии. Остаток с незавершённым ожиданием
        остаётся висеть — освобождение убило бы идущую команду.
        """
        storage = JsonFileStorage(tmp_path)
        session = await _session_with_open_turn(storage)
        domain = SessionMapper.to_domain(session)

        aliases = TerminalAliasRegistry(epoch="7")
        waited = aliases.register(domain, "client-waited")
        unwaited = aliases.register(domain, "client-unwaited")
        aliases.mark_waited(domain, waited)

        service = MagicMock(spec=ClientRPCService)
        released_at_revision: list[int | None] = []

        async def _release(**kwargs: Any) -> bool:
            stored = await JsonFileStorage(tmp_path).load_session("sess_t")
            released_at_revision.append(stored.active_turn is None if stored else None)
            return True

        service.release_terminal = AsyncMock(side_effect=_release)
        holder = ClientRPCServiceHolder()
        holder.service = service
        releaser = TurnTerminalReleaser(aliases=aliases, client_rpc_service_holder=holder)

        response = await _executor(storage, releaser).complete_active_turn("sess_t")

        assert response is not None
        assert released_at_revision == [True], "освобождение обязано идти после записи снятия"
        assert aliases.known_aliases(domain) == [unwaited]

    @pytest.mark.asyncio
    async def test_missing_session_is_not_resurrected(self, tmp_path: Path) -> None:
        """Удалённую сессию завершение turn'а не воскрешает."""
        storage = JsonFileStorage(tmp_path)

        assert await _executor(storage).complete_active_turn("sess_missing") is None
        assert await JsonFileStorage(tmp_path).load_session("sess_missing") is None

"""Терминалы из прошлого процесса не переживают загрузку сессии (P2-44).

Живьём (`sess_b959781bd8bf`): три ошибки уровня `error` подряд по одному терминалу
— `output`, `wait_for_exit`, `release`, все с `RPC Error -32603` от клиента. Терминал
был создан предыдущим процессом; сервер перезапустили, сессия загрузилась вместе с
реестром alias'ов, и модель по восстановленной истории обратилась к дескриптору,
которого уже нет.

Реестр персистится (схема v5), а сами терминалы живут у клиента. Отметка владельца
отличает «загрузил тот же процесс» от «загрузил другой».
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codelab.server.messages import ACPMessage
from codelab.server.process_identity import PROCESS_TOKEN
from codelab.server.protocol.commands.session_load import SessionLoadCommandHandler
from codelab.server.protocol.state import SessionState
from codelab.server.storage import JsonFileStorage, SessionRepository
from codelab.server.tools.executors.terminal_alias_registry import TerminalAliasRegistry


def _handler(storage: JsonFileStorage) -> SessionLoadCommandHandler:
    return SessionLoadCommandHandler(
        repository=SessionRepository(backend=storage),
        config_specs={},
        auth_methods=[],
        require_auth=False,
        authenticated=True,
    )


async def _load(storage: JsonFileStorage) -> None:
    outcome = await _handler(storage).handle(
        ACPMessage(
            id="req_1",
            method="session/load",
            params={"sessionId": "sess_x", "cwd": "/work", "mcpServers": []},
        )
    )
    assert outcome.response is not None
    assert outcome.response.error is None


def _session_with_terminals(owner: str | None) -> SessionState:
    session = SessionState(session_id="sess_x", cwd="/work", mcp_servers=[])
    session.terminals = {"term_1": "client-uuid-1", "term_2": "client-uuid-2"}
    session.terminal_counter = 2
    session.terminals_owner = owner
    return session


class TestTerminalsFromPreviousProcess:
    @pytest.mark.asyncio
    async def test_terminals_of_another_process_are_dropped(self, tmp_path: Path) -> None:
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session_with_terminals(owner="другой-процесс"))

        await _load(storage)

        on_disk = await JsonFileStorage(tmp_path).load_session("sess_x")
        assert on_disk is not None
        assert on_disk.terminals == {}, "мёртвые дескрипторы не должны пережить загрузку"
        assert on_disk.terminals_owner is None

    @pytest.mark.asyncio
    async def test_terminals_of_same_process_are_kept(self, tmp_path: Path) -> None:
        """Тот же процесс — терминалы ещё живы, трогать нельзя."""
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session_with_terminals(owner=PROCESS_TOKEN))

        await _load(storage)

        on_disk = await JsonFileStorage(tmp_path).load_session("sess_x")
        assert on_disk is not None
        assert on_disk.terminals == {"term_1": "client-uuid-1", "term_2": "client-uuid-2"}

    @pytest.mark.asyncio
    async def test_unknown_owner_is_treated_as_another_process(self, tmp_path: Path) -> None:
        """Сессия записана до появления отметки — значит точно другим процессом."""
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session_with_terminals(owner=None))

        await _load(storage)

        on_disk = await JsonFileStorage(tmp_path).load_session("sess_x")
        assert on_disk is not None
        assert on_disk.terminals == {}

    @pytest.mark.asyncio
    async def test_counter_is_not_reset(self, tmp_path: Path) -> None:
        """Счётчик сохраняется: новый терминал не должен получить занятый в истории alias."""
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session_with_terminals(owner="другой-процесс"))

        await _load(storage)

        on_disk = await JsonFileStorage(tmp_path).load_session("sess_x")
        assert on_disk is not None
        assert on_disk.terminal_counter == 2
        assert TerminalAliasRegistry().register(on_disk, "новый") == "term_3"

    @pytest.mark.asyncio
    async def test_dropped_terminal_resolves_to_none(self, tmp_path: Path) -> None:
        """Обращение к старому alias'у идёт по пути «неизвестный терминал».

        Это и есть цель: модель получает внятный ответ вместо RPC Error -32603.
        """
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session_with_terminals(owner="другой-процесс"))

        await _load(storage)

        on_disk = await JsonFileStorage(tmp_path).load_session("sess_x")
        assert on_disk is not None
        assert TerminalAliasRegistry().resolve(on_disk, "term_1") is None


class TestRegistryStampsOwner:
    def test_register_marks_current_process(self) -> None:
        session = SessionState(session_id="sess_x", cwd="/work", mcp_servers=[])

        TerminalAliasRegistry().register(session, "client-uuid")

        assert session.terminals_owner == PROCESS_TOKEN

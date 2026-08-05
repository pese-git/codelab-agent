"""Терминалы прошлого процесса невозможны по построению (ADR-007, шаг A; P2-58).

История дефекта. Живьём (`sess_b959781bd8bf`) — три ошибки уровня `error` подряд по
одному терминалу: `output`, `wait_for_exit`, `release`, все с `RPC Error -32603` от
клиента. Терминал создал предыдущий процесс; сервер перезапустили, сессия загрузилась
вместе с реестром alias'ов, и модель по восстановленной истории обратилась к
дескриптору, которого уже нет.

Первым ответом (P2-44, схема v5→v8) была компенсация: отметка владельца плюс чистка
реестра на загрузке. Она лечила следствие — реестр всё равно персистился, и
пользоваться им можно было только доказав, что он ещё действителен.

Теперь причина снята: связка alias → client terminalId живёт в процессном
`TerminalAliasRegistry` и на диск не попадает вовсе, поэтому чистить нечего.
Проверяется именно это, а не поведение чистки.

Счётчик alias'ов при этом **обязан** переживать рестарт: при сбросе `term_1` из
восстановленной истории разрешился бы в терминал нового процесса, и модель получила бы
чужой вывод вместо внятного «неизвестный терминал». Гейт на это — ниже.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from codelab.server.mapping.session_mapper import SessionMapper
from codelab.server.messages import ACPMessage
from codelab.server.protocol.commands.session_load import SessionLoadCommandHandler
from codelab.server.storage import JsonFileStorage, SessionRepository
from codelab.server.storage.document import SessionDocument
from codelab.server.tools.executors.terminal_alias_registry import TerminalAliasRegistry
from tests.server._domain_sessions import make_domain_session


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


def _write_v8_document(base_path: Path, *, owner: str | None) -> None:
    """Кладёт на диск **настоящий** документ схемы v8 — с реестром терминалов.

    Именно так выглядят файлы, записанные до этого шага, поэтому миграция проверяется
    на реальной форме, а не на синтетической: v6→v7 в своё время живьём так и не
    проверили, и повторять это не стоит.
    """
    document: dict[str, Any] = {
        "schema_version": 8,
        "revision": 3,
        "session_id": "sess_x",
        "cwd": "/work",
        "mcp_servers": [],
        "terminals": {"term_1": "client-uuid-1", "term_2": "client-uuid-2"},
        "terminals_owner": owner,
        "terminal_counter": 2,
    }
    (base_path / "sess_x.json").write_text(json.dumps(document), encoding="utf-8")


class TestMigrationFromV8:
    """Документ v8 читается, реестр отбрасывается, счётчик остаётся."""

    @pytest.mark.asyncio
    async def test_v8_document_loads(self, tmp_path: Path) -> None:
        _write_v8_document(tmp_path, owner="другой-процесс")

        on_disk = await JsonFileStorage(tmp_path).load_session("sess_x")

        assert on_disk is not None
        assert on_disk.schema_version == 9

    @pytest.mark.asyncio
    async def test_alias_bindings_are_dropped(self, tmp_path: Path) -> None:
        """Связка не переносится в v9 ни при каком владельце: она мертва по смыслу."""
        _write_v8_document(tmp_path, owner="другой-процесс")

        on_disk = await JsonFileStorage(tmp_path).load_session("sess_x")

        assert on_disk is not None
        assert not hasattr(on_disk, "terminals")
        assert not hasattr(on_disk, "terminals_owner")

    @pytest.mark.asyncio
    async def test_counter_survives_migration(self, tmp_path: Path) -> None:
        """Счётчик — распределитель id сессии, а не состояние процесса."""
        _write_v8_document(tmp_path, owner="другой-процесс")

        on_disk = await JsonFileStorage(tmp_path).load_session("sess_x")

        assert on_disk is not None
        assert on_disk.terminal_counter == 2

    @pytest.mark.asyncio
    async def test_revision_survives_migration(self, tmp_path: Path) -> None:
        """Ревизия не сбрасывается: иначе следующая запись прошла бы CAS вслепую."""
        _write_v8_document(tmp_path, owner="другой-процесс")

        on_disk = await JsonFileStorage(tmp_path).load_session("sess_x")

        assert on_disk is not None
        assert on_disk.revision == 3


class TestAliasesNeverReachDisk:
    @pytest.mark.asyncio
    async def test_registered_alias_is_absent_from_saved_document(self, tmp_path: Path) -> None:
        """Главный гейт шага: регистрация терминала не меняет документ, кроме счётчика.

        Гейт стоит на `JsonFileStorage`, а не на памяти: in-memory backend отдаёт сам
        хранимый объект и скрыл бы «связка всё ещё в агрегате».
        """
        storage = JsonFileStorage(tmp_path)
        session = make_domain_session(session_id="sess_x", cwd="/work", mcp_servers=[])
        registry = TerminalAliasRegistry()

        alias = registry.register(session, "client-uuid-1")
        await storage.save_session(SessionMapper.to_protocol(session))

        raw = json.loads((tmp_path / "sess_x.json").read_text(encoding="utf-8"))
        assert "terminals" not in raw
        assert "terminals_owner" not in raw
        assert "client-uuid-1" not in json.dumps(raw), "client terminalId не должен попасть на диск"
        assert raw["terminal_counter"] == 1, "счётчик персистится — он выдаёт alias'ы"
        assert alias == "term_1"


class TestFreshProcessStartsEmpty:
    @pytest.mark.asyncio
    async def test_alias_from_previous_process_resolves_to_none(self, tmp_path: Path) -> None:
        """После рестарта alias не разрешается — это путь «неизвестный терминал».

        Новый процесс = новый реестр, поэтому доказывать актуальность связки больше не
        нужно: её просто нет.
        """
        _write_v8_document(tmp_path, owner="другой-процесс")
        await _load(JsonFileStorage(tmp_path))

        on_disk = await JsonFileStorage(tmp_path).load_session("sess_x")
        assert on_disk is not None
        domain_session = SessionMapper.to_domain(on_disk)
        fresh_process_registry = TerminalAliasRegistry()

        assert fresh_process_registry.resolve(domain_session, "term_1") is None
        assert fresh_process_registry.known_aliases(domain_session) == []

    @pytest.mark.asyncio
    async def test_new_alias_does_not_collide_with_history(self, tmp_path: Path) -> None:
        """Ради этого счётчик и персистится: `term_1` из истории не выдаётся заново.

        Иначе обращение к `term_1` из восстановленной истории разрешилось бы в
        терминал нового процесса — модель получила бы чужой вывод вместо ошибки.
        """
        _write_v8_document(tmp_path, owner="другой-процесс")
        await _load(JsonFileStorage(tmp_path))

        on_disk = await JsonFileStorage(tmp_path).load_session("sess_x")
        assert on_disk is not None

        assert TerminalAliasRegistry().register(SessionMapper.to_domain(on_disk), "новый") == (
            "term_3"
        )


class TestRegistryIsolatesSessions:
    def test_alias_of_one_session_is_invisible_to_another(self) -> None:
        """Реестр процессный, поэтому адресация по `session_id` обязательна."""
        registry = TerminalAliasRegistry()
        first = make_domain_session(session_id="sess_a", cwd="/work", mcp_servers=[])
        second = make_domain_session(session_id="sess_b", cwd="/work", mcp_servers=[])

        alias = registry.register(first, "client-uuid-1")

        assert registry.resolve(first, alias) == "client-uuid-1"
        assert registry.resolve(second, alias) is None

    def test_release_removes_binding(self) -> None:
        registry = TerminalAliasRegistry()
        session = make_domain_session(session_id="sess_a", cwd="/work", mcp_servers=[])
        alias = registry.register(session, "client-uuid-1")

        assert registry.release(session, alias) == "client-uuid-1"
        assert registry.resolve(session, alias) is None
        assert registry.release(session, alias) is None, "повторное освобождение идемпотентно"


class TestDocumentSchema:
    def test_new_document_declares_v9(self) -> None:
        document = SessionDocument(session_id="sess_x", cwd="/work", mcp_servers=[])

        assert document.schema_version == 9

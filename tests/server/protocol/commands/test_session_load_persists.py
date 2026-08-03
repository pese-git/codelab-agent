"""`session/load` сохраняет свои решения на диск (P2-42).

Дефект был измерим, а не выводим: обработчик решал одно, на диске оставалось
другое. `session/load` загружал сессию дважды за запрос (команда мутировала одну
копию, функция — другую) и не сохранял ничего, а `JsonFileStorage` отдаёт новый
объект на каждый `load_session`.

Все проверки читают состояние **с диска через новый экземпляр хранилища**. Смотреть
на мутированный объект здесь нельзя: именно так предыдущий тест на ответ
отложенного хвоста прошёл, хотя в проде ветка эффекта не давала.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codelab.server.messages import ACPMessage
from codelab.server.protocol.commands.session_load import SessionLoadCommandHandler
from codelab.server.models import HistoryMessage
from codelab.server.protocol.state import ActiveTurnState, SessionState, ToolCallState
from codelab.server.storage import JsonFileStorage, SessionRepository


def _tool_answers(session: SessionState) -> list[tuple[str, str]]:
    """Ответы `role: tool` из истории.
    
    Форма одна: после снятия союза `HistoryMessage | dict` (ADR-006, фаза D
    шаг 4) и свежая запись, и прочитанная с диска — одна и та же модель.
    """
    return [
        (message.tool_call_id or "", str(message.content or ""))
        for message in session.history
        if message.role == "tool"
    ]


def _handler(storage: JsonFileStorage) -> SessionLoadCommandHandler:
    """Обработчик на доменном порту поверх файлового бэкенда (фаза D ADR-006)."""
    return SessionLoadCommandHandler(
        repository=SessionRepository(backend=storage),
        config_specs={},
        auth_methods=[],
        require_auth=False,
        authenticated=True,
    )


def _session_with_interrupted_turn() -> SessionState:
    session = SessionState(session_id="sess_x", cwd="/old", mcp_servers=[])
    session.active_turn = ActiveTurnState(prompt_request_id="req_1", session_id="sess_x")
    session.active_turn.pending_batch = [
        {"id": "llm_2", "name": "fs_read_text_file", "arguments": {"path": "B.md"}}
    ]
    session.tool_calls["call_001"] = ToolCallState(
        tool_call_id="call_001",
        title="fs/read_text_file",
        kind="read",
        status="pending",
        tool_call_id_from_llm="llm_1",
    )
    return session


async def _load(storage: JsonFileStorage, cwd: str = "/work") -> None:
    outcome = await _handler(storage).handle(
        ACPMessage(
            id="req_2",
            method="session/load",
            params={"sessionId": "sess_x", "cwd": cwd, "mcpServers": []},
        )
    )
    assert outcome.response is not None
    assert outcome.response.error is None


class TestSessionLoadPersistsDecisions:
    @pytest.mark.asyncio
    async def test_client_cwd_reaches_disk(self, tmp_path: Path) -> None:
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session_with_interrupted_turn())

        await _load(storage, cwd="/work")

        on_disk = await JsonFileStorage(tmp_path).load_session("sess_x")
        assert on_disk is not None
        assert on_disk.cwd == "/work"

    @pytest.mark.asyncio
    async def test_interrupted_turn_is_cleared_on_disk(self, tmp_path: Path) -> None:
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session_with_interrupted_turn())

        await _load(storage)

        on_disk = await JsonFileStorage(tmp_path).load_session("sess_x")
        assert on_disk is not None
        assert on_disk.active_turn is None
        assert on_disk.tool_calls["call_001"].status == "cancelled"

    @pytest.mark.asyncio
    async def test_deferred_batch_answers_reach_disk(self, tmp_path: Path) -> None:
        """Ответы модели обязаны сохраниться, иначе ветки P2-38/P2-40 бесполезны."""
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session_with_interrupted_turn())

        await _load(storage)

        on_disk = await JsonFileStorage(tmp_path).load_session("sess_x")
        assert on_disk is not None
        answers = _tool_answers(on_disk)
        # llm_2 — отложенный хвост (P2-40), llm_1 — приостановленный вызов,
        # отменённый переключением сессии (P2-38, источник 2). Оба должны быть на
        # диске: без сохранения оба ответа терялись.
        assert {tool_call_id for tool_call_id, _ in answers} == {"llm_1", "llm_2"}
        assert all("переключена" in content for _, content in answers)

    @pytest.mark.asyncio
    async def test_single_load_per_request(self, tmp_path: Path) -> None:
        """Загрузка одна: вторая давала бы вторую копию и теряла мутации первой."""
        storage = JsonFileStorage(tmp_path)
        await storage.save_session(_session_with_interrupted_turn())

        loads = 0
        original = storage.load_session

        async def _counting_load(session_id: str):
            nonlocal loads
            loads += 1
            return await original(session_id)

        # Считаем обращения к бэкенду: порт ходит в него на каждую загрузку
        storage.load_session = _counting_load  # type: ignore[method-assign]

        await _load(storage)

        assert loads == 1

    @pytest.mark.asyncio
    async def test_orphaned_permission_cleared_on_disk(self, tmp_path: Path) -> None:
        """Осиротевший permission-request не должен оставаться на диске."""
        storage = JsonFileStorage(tmp_path)
        session = _session_with_interrupted_turn()
        session.active_turn.permission_request_id = "perm_1"
        await storage.save_session(session)

        await _load(storage)

        on_disk = await JsonFileStorage(tmp_path).load_session("sess_x")
        assert on_disk is not None
        assert on_disk.active_turn is None

    @pytest.mark.asyncio
    async def test_missing_session_is_not_saved(self, tmp_path: Path) -> None:
        """Ошибочный запрос не должен создавать сессию на диске."""
        storage = JsonFileStorage(tmp_path)

        outcome = await _handler(storage).handle(
            ACPMessage(
                id="req_2",
                method="session/load",
                params={"sessionId": "missing", "cwd": "/work", "mcpServers": []},
            )
        )

        assert outcome.response is not None
        assert outcome.response.error is not None
        assert await JsonFileStorage(tmp_path).load_session("missing") is None


class TestDomainRoundTripDoesNotRewriteFormat:
    """Гейт миграции на порт: `session/load` теперь пишет, значит потеря маппера
    переписала бы существующие сессии (фаза D ADR-006).

    Проверяется на форме, которую производит текущий код: сессия сначала проходит
    цикл через диск (там pydantic нормализует записи), и только эта форма — та, что
    реально лежит в `~/.codelab/data/sessions`.
    """

    @pytest.mark.asyncio
    async def test_load_does_not_change_untouched_fields(self, tmp_path: Path) -> None:

        storage = JsonFileStorage(tmp_path)
        session = SessionState(session_id="sess_x", cwd="/work", mcp_servers=[])
        session.title = "T"
        session.config_values = {"mode": "standard"}
        session.history = [
            {"role": "user", "content": [{"type": "text", "text": "hi"}]},
            {
                "role": "assistant",
                "text": "ok",
                # `arguments` обязателен: так пишет боевой путь (`loop.py`), и без него
                # round-trip добавил бы ключ — фикстура должна повторять реальную форму
                "tool_calls": [{"id": "llm_1", "name": "fs_read", "arguments": {"path": "a"}}],
            },
            {"role": "tool", "tool_call_id": "llm_1", "content": "res"},
        ]
        session.events_history = [
            {"type": "session_update", "update": {"sessionUpdate": "tool_call", "toolCallId": "c1"}}
        ]
        session.tool_calls["c1"] = ToolCallState(
            tool_call_id="c1",
            title="fs/read_text_file",
            kind="read",
            status="completed",
            tool_call_id_from_llm="llm_1",
            tool_name="fs/read_text_file",
            tool_arguments={"path": "a"},
            raw_input={"path": "a"},
        )
        session.latest_plan = [{"content": "x", "priority": "high", "status": "pending"}]
        await storage.save_session(session)

        before = (await JsonFileStorage(tmp_path).load_session("sess_x")).model_dump(mode="json")

        await _load(storage, cwd="/work")

        after = (await JsonFileStorage(tmp_path).load_session("sess_x")).model_dump(mode="json")

        # Транзакция меняет только то, что решила: turn и updated_at
        changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
        # revision растёт на каждой записи — это и есть механизм CAS (ADR-007)
        assert changed <= {"active_turn", "updated_at", "revision"}, (
            f"перезаписаны лишние поля: {changed}"
        )
        assert after["revision"] == before["revision"] + 1

    def test_known_normalizations_of_hand_built_records(self) -> None:
        """Известные нормализации маппера — зафиксированы осознанно.

        Обе проявляются только на записях, которых боевой путь не создаёт: он всегда
        заполняет и `raw_input` (`create_tool_call`), и `arguments` в истории
        (`loop.py`). На живой сессии таких записей 0 из 40 в обоих случаях. Тест
        держит поведение зафиксированным, чтобы изменение маппера было заметным.

        В домене у вызова одно поле `arguments` (решение фазы B), в wire их два:
        `raw_input` (ACP rawInput) и `tool_arguments` — отсюда заполнение пустого
        `raw_input`. Вторая нормализация: запись истории без ключа `arguments`
        получает `arguments: {}`.
        """
        from codelab.server.mapping.session_mapper import SessionMapper

        state = SessionState(session_id="s", cwd="/w", mcp_servers=[])
        state.tool_calls["c1"] = ToolCallState(
            tool_call_id="c1",
            title="fs/read_text_file",
            kind="read",
            status="completed",
            tool_name="fs/read_text_file",
            tool_arguments={"path": "a"},
            raw_input={},
        )

        restored = SessionMapper.to_protocol(SessionMapper.to_domain(state))

        assert restored.tool_calls["c1"].raw_input == {"path": "a"}
        assert restored.tool_calls["c1"].tool_arguments == {"path": "a"}

        # Вторая нормализация: отсутствующий `arguments` в истории. Документ
        # собирается валидацией, а не присваиванием поля, — именно так его
        # получает загрузка с диска, и именно так сырая запись прошлых версий
        # приводится к `HistoryMessage` после снятия союза (ADR-006, D4).
        loaded = SessionState.model_validate(
            {
                "session_id": "s",
                "cwd": "/w",
                "mcp_servers": [],
                "history": [
                    {"role": "assistant", "tool_calls": [{"id": "llm_1", "name": "fs_read"}]}
                ],
            }
        )
        assert isinstance(loaded.history[0], HistoryMessage), "сырой dict приведён к модели"

        restored = SessionMapper.to_protocol(SessionMapper.to_domain(loaded))
        assert restored.history[0].tool_calls[0]["arguments"] == {}

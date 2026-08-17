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

from codelab.server.domain.value_objects import MessageRole
from codelab.server.mapping.session_mapper import SessionMapper
from codelab.server.messages import ACPMessage
from codelab.server.models import HistoryMessage
from codelab.server.protocol.commands.session_load import SessionLoadCommandHandler
from codelab.server.protocol.pending_registry import PendingRequestRegistry
from codelab.server.storage import JsonFileStorage, SessionRepository
from codelab.server.storage.document import (
    ActiveTurnState,
    PermissionWaitState,
    SessionDocument,
    ToolCallState,
)


def _tool_answers(session: SessionDocument) -> list[tuple[str, str]]:
    """Ответы `role: tool`, восстановленные из документа.

    Источник — журнал: с шага 4f ADR-008 история стала проекцией и в документе не
    хранится, поэтому читать `session.history` значило бы проверять отсутствие
    коллекции. Гейт по-прежнему про диск — документ приходит из хранилища.
    """
    return [
        (message.tool_call_id or "", message.content.text)
        for message in SessionMapper.to_domain(session).history.get_messages()
        if message.role == MessageRole.TOOL
    ]


def _handler(
    storage: JsonFileStorage,
    pending_registry: PendingRequestRegistry | None = None,
) -> SessionLoadCommandHandler:
    """Обработчик на доменном порту поверх файлового бэкенда (фаза D ADR-006)."""
    return SessionLoadCommandHandler(
        repository=SessionRepository(backend=storage),
        config_specs={},
        auth_methods=[],
        require_auth=False,
        authenticated=True,
        pending_registry=pending_registry,
    )


def _session_with_interrupted_turn() -> SessionDocument:
    session = SessionDocument(session_id="sess_x", cwd="/old", mcp_servers=[])
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


async def _load(
    storage: JsonFileStorage,
    cwd: str = "/work",
    pending_registry: PendingRequestRegistry | None = None,
    session_id: str = "sess_x",
) -> None:
    outcome = await _handler(storage, pending_registry).handle(
        ACPMessage(
            id="req_2",
            method="session/load",
            params={"sessionId": session_id, "cwd": cwd, "mcpServers": []},
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
        # Ожидание заводится списком (v12): плоское поле стало выводимым, потому что
        # незакрытых разрешений может быть несколько (P1-61).
        session.active_turn.permission_waits = [PermissionWaitState(request_id="perm_1")]
        await storage.save_session(session)

        await _load(storage)

        on_disk = await JsonFileStorage(tmp_path).load_session("sess_x")
        assert on_disk is not None
        assert on_disk.active_turn is None

    @pytest.mark.asyncio
    async def test_orphaned_permission_does_not_preempt_cleanup(self, tmp_path: Path) -> None:
        """Сирота разрешения не отменяет отмену turn'а — она её делает (P2-62).

        Прежняя ветка звала `clear_active_turn()` **до** `_cleanup_session_state`,
        и тот не находил turn'а: замер дал ноль надгробий вместо двух и потерянный
        ответ отложенному хвосту. Судьбу решала одна пара полей («последнее»
        ожидание), про которую домен говорит, что решать по ней нельзя.
        """
        storage = JsonFileStorage(tmp_path)
        session = _session_with_interrupted_turn()
        session.active_turn.permission_waits = [
            PermissionWaitState(request_id="perm_live", tool_call_id="call_001"),
            PermissionWaitState(request_id="perm_orphan", tool_call_id="call_002"),
        ]
        await storage.save_session(session)

        # В реестре живёт первое ожидание — то, которое «последним» не является.
        registry = PendingRequestRegistry()
        registry.record_outgoing("perm_live", "sess_x")

        await _load(storage, pending_registry=registry)

        on_disk = await JsonFileStorage(tmp_path).load_session("sess_x")
        assert on_disk is not None
        assert on_disk.active_turn is None
        # Надгробие нужно **каждому** незакрытому ожиданию: поздний ответ без него
        # уходит в «неизвестный запрос» (-32603).
        assert set(on_disk.cancelled_permission_requests) == {"perm_live", "perm_orphan"}
        # Хвост батча (P2-40) обязан получить `role: tool`, иначе модель повторит
        # вызов (P2-38).
        assert {tool_call_id for tool_call_id, _ in _tool_answers(on_disk)} == {"llm_1", "llm_2"}

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
        session = SessionDocument(session_id="sess_x", cwd="/work", mcp_servers=[])
        session.title = "T"
        session.config_values = {"mode": "standard"}
        session.history = [
            HistoryMessage(role="user", content=[{"type": "text", "text": "hi"}]),
            HistoryMessage(
                role="assistant",
                text="ok",
                # `arguments` обязателен: так пишет боевой путь (`loop.py`), и без него
                # round-trip добавил бы ключ — фикстура должна повторять реальную форму
                tool_calls=[{"id": "llm_1", "name": "fs_read", "arguments": {"path": "a"}}],
            ),
            HistoryMessage(role="tool", tool_call_id="llm_1", content="res"),
        ]
        # Запись в форме v10 — намеренно: она проверяет, что старый носитель
        # читается. Что запись **v11** переживает загрузку без изменений, проверяет
        # `test_v11_journal_is_not_rewritten` ниже.
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
        # revision растёт на каждой записи — это и есть механизм CAS (ADR-007);
        # `events_history` — нормализация формы записи v10 → v11 (шаг 6a): журнал
        # стал доменной коллекцией, поэтому на диск он уезжает в единственной
        # форме, которую пишет маппер. Разовая и только для записей до 3b.
        assert changed <= {"active_turn", "updated_at", "revision", "events_history"}, (
            f"перезаписаны лишние поля: {changed}"
        )
        assert after["revision"] == before["revision"] + 1
        # `acp_update_verbatim`, а не `tool_call_started`: у записи нет ни `title`,
        # ни `kind`, ни `status`, поэтому вызовом она не распознаётся и сохраняется
        # непрозрачно (`UnknownUpdateRecorded`). Содержимое при этом не теряется —
        # теряется только запись, которая журналом не является вовсе.
        assert [record["event"] for record in after["events_history"]] == ["acp_update_verbatim"]
        assert after["events_history"][0]["data"]["update"] == {
            "sessionUpdate": "tool_call",
            "toolCallId": "c1",
        }

    @pytest.mark.asyncio
    async def test_v11_journal_is_not_rewritten(self, tmp_path: Path) -> None:
        """Журнал в текущей форме переживает загрузку **байт-в-байт**.

        Пара к тесту выше: нормализация v10 → v11 разовая и касается только
        записей, созданных до шага 3b. Документы, которые лежат в
        `~/.codelab/data/sessions` сегодня, состоят из записей v11 — замер на
        живой сессии (71 запись) и на `recorded_session_v14` (24) дал 0
        расхождений при round-trip, и этот гейт держит результат.
        """
        storage = JsonFileStorage(tmp_path)
        session = SessionDocument(session_id="sess_v11", cwd="/work", mcp_servers=[])
        session.events_history = [
            {
                "event": "user_message_recorded",
                "at": "2026-08-17T05:45:40.677000+00:00",
                "data": {"blocks": [{"type": "text", "text": "привет"}]},
            }
        ]
        await storage.save_session(session)
        before = (await JsonFileStorage(tmp_path).load_session("sess_v11")).model_dump(mode="json")

        await _load(storage, cwd="/work", session_id="sess_v11")

        after = (await JsonFileStorage(tmp_path).load_session("sess_v11")).model_dump(mode="json")
        assert after["events_history"] == before["events_history"]

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
        state = SessionDocument(session_id="s", cwd="/w", mcp_servers=[])
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
        loaded = SessionDocument.model_validate(
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

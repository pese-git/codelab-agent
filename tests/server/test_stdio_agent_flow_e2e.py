"""E2E тесты полных flow взаимодействия клиента с агентом через stdio.

Транспорт-специфична только оболочка (StdioTransport + запуск subprocess);
драйвер turn, ответчики и сценарии — из общего agent_flow_harness.

Проверяемые flow: чат, fs/read, fs/write, terminal, reject (cancelled),
bypass (no ask), plan (read allow / execute reject), ошибка инструмента,
мульти-tool за turn, session/cancel.
"""

from __future__ import annotations

from pathlib import Path

import agent_flow_harness as h
import pytest

# stdio-транспорт и запуск сервера вынесены в agent_flow_harness (h.StdioServer).
_server = h.StdioServer


@pytest.fixture
def tmp_cwd(tmp_path: Path) -> Path:
    return tmp_path


# --------------------------------------------------------------------------- #
# Тесты
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_multi_turn_chat(tmp_cwd: Path) -> None:
    """Многоходовой чат: два промпта в одной сессии, разные ответы."""
    async with _server(tmp_cwd, h.chat_scenario()) as t:
        session_id = await h.handshake(t, tmp_cwd)

        resp, notes, _ = await h.run_prompt(t, session_id, "привет", 10)
        assert resp["result"]["stopReason"] == "end_turn"
        assert "тестовый агент" in h.agent_text(notes)

        resp, notes, _ = await h.run_prompt(t, session_id, "как дела?", 11)
        assert resp["result"]["stopReason"] == "end_turn"
        assert "готов помогать" in h.agent_text(notes)


@pytest.mark.asyncio
async def test_fs_read_flow(tmp_cwd: Path) -> None:
    """fs/read: permission → recv answer → fs/read_text_file → result → text."""
    async with _server(tmp_cwd, h.fs_read_scenario()) as t:
        session_id = await h.handshake(t, tmp_cwd)
        resp, notes, rpc = await h.run_prompt(t, session_id, "прочти README.md", 10)

        assert resp["result"]["stopReason"] == "end_turn"
        assert "fs/read_text_file" in rpc
        assert "Прочитал README" in h.agent_text(notes)


@pytest.mark.asyncio
async def test_terminal_flow(tmp_cwd: Path) -> None:
    """terminal: create → wait_for_exit → release → show result."""
    async with _server(tmp_cwd, h.terminal_scenario()) as t:
        session_id = await h.handshake(t, tmp_cwd)
        resp, notes, rpc = await h.run_prompt(t, session_id, "запусти ls -ahl", 10)

        assert resp["result"]["stopReason"] == "end_turn"
        assert "terminal/create" in rpc
        assert "Команда выполнена" in h.agent_text(notes)


@pytest.mark.asyncio
async def test_fs_write_flow(tmp_cwd: Path) -> None:
    """fs/write: permission → recv answer → fs/write_text_file → result → text."""
    scenario = {
        "turns": [
            {
                "when_user": ["запиши", "создай файл"],
                "replies": [
                    {"tool_calls": [
                        {"name": "fs_write_text_file",
                         "arguments": {"path": "notes.txt", "content": "привет"}}
                    ]},
                    {"text": "Файл записан."},
                ],
            },
        ],
    }
    async with _server(tmp_cwd, scenario) as t:
        session_id = await h.handshake(t, tmp_cwd)
        resp, notes, rpc = await h.run_prompt(t, session_id, "запиши notes.txt", 10)

        assert resp["result"]["stopReason"] == "end_turn"
        assert "fs/write_text_file" in rpc
        assert "Файл записан" in h.agent_text(notes)


@pytest.mark.asyncio
async def test_permission_reject_cancels_turn(tmp_cwd: Path) -> None:
    """Отказ в разрешении: reject_once → turn cancelled, инструмент не вызван."""
    async with _server(tmp_cwd, h.terminal_single_scenario()) as t:
        session_id = await h.handshake(t, tmp_cwd)
        resp, _notes, rpc = await h.run_prompt(
            t, session_id, "запусти ls", 10, responders=h.REJECT_RESPONDER
        )

        assert resp["result"]["stopReason"] == "cancelled"
        assert "session/request_permission" in rpc
        assert "terminal/create" not in rpc


@pytest.mark.asyncio
async def test_bypass_mode_auto_allows_without_permission(tmp_cwd: Path) -> None:
    """mode=bypass: инструмент выполняется сразу, без session/request_permission."""
    scenario = h.terminal_scenario("Готово без запроса разрешения.")
    async with _server(tmp_cwd, scenario) as t:
        session_id = await h.handshake(t, tmp_cwd)
        await h.set_mode(t, session_id, "bypass", 3)
        resp, notes, rpc = await h.run_prompt(t, session_id, "запусти ls", 10)

        assert resp["result"]["stopReason"] == "end_turn"
        assert "session/request_permission" not in rpc
        assert "terminal/create" in rpc
        assert "Готово без запроса" in h.agent_text(notes)


@pytest.mark.asyncio
async def test_plan_mode_allows_read_rejects_execute(tmp_cwd: Path) -> None:
    """mode=plan: read авто-разрешён (без спроса), execute отклоняется.

    Отклонённый в plan-режиме инструмент не выполняется (нет client RPC),
    но агент получает "rejected" и продолжает — turn завершается нормально.
    """
    scenario = {
        "turns": [
            {
                "when_user": ["прочти"],
                "replies": [
                    {"tool_calls": [
                        {"name": "fs_read_text_file", "arguments": {"path": "R.md"}}
                    ]},
                    {"text": "Прочитал файл."},
                ],
            },
            {
                "when_user": ["запусти"],
                "replies": [
                    {"tool_calls": [
                        {"name": "terminal_create", "arguments": {"command": "ls"}}
                    ]},
                    {"text": "Понял, в plan-режиме выполнить нельзя."},
                ],
            },
        ],
    }
    async with _server(tmp_cwd, scenario) as t:
        session_id = await h.handshake(t, tmp_cwd)
        await h.set_mode(t, session_id, "plan", 3)

        # read — авто-разрешён, файл читается, без запроса разрешения
        resp, notes, rpc = await h.run_prompt(t, session_id, "прочти R.md", 10)
        assert resp["result"]["stopReason"] == "end_turn"
        assert "session/request_permission" not in rpc
        assert "fs/read_text_file" in rpc
        assert "Прочитал файл" in h.agent_text(notes)

        # execute — отклонён: инструмент до клиента не доходит, агент продолжает
        resp, notes, rpc = await h.run_prompt(t, session_id, "запусти ls", 11)
        assert resp["result"]["stopReason"] == "end_turn"
        assert "terminal/create" not in rpc
        assert "session/request_permission" not in rpc


@pytest.mark.asyncio
async def test_tool_error_is_handled(tmp_cwd: Path) -> None:
    """Ошибка инструмента: клиент вернул JSON-RPC error → агент продолжает."""
    async with _server(tmp_cwd, h.fs_error_scenario()) as t:
        session_id = await h.handshake(t, tmp_cwd)
        await h.set_mode(t, session_id, "bypass", 3)
        resp, notes, rpc = await h.run_prompt(
            t,
            session_id,
            "прочти missing.md",
            10,
            responders={
                "fs/read_text_file": lambda p: h.RpcError(-32000, "file not found")
            },
        )

        assert resp["result"]["stopReason"] == "end_turn"
        assert "fs/read_text_file" in rpc
        assert "обработал ошибку" in h.agent_text(notes)


@pytest.mark.asyncio
async def test_multi_tool_sequence_in_one_turn(tmp_cwd: Path) -> None:
    """Несколько инструментов за один turn: read → write → финальный текст."""
    async with _server(tmp_cwd, h.multi_tool_scenario()) as t:
        session_id = await h.handshake(t, tmp_cwd)
        await h.set_mode(t, session_id, "bypass", 3)
        resp, notes, rpc = await h.run_prompt(t, session_id, "обработай in.md", 10)

        assert resp["result"]["stopReason"] == "end_turn"
        assert "fs/read_text_file" in rpc
        assert "fs/write_text_file" in rpc
        assert rpc.index("fs/read_text_file") < rpc.index("fs/write_text_file")
        assert "записал out.md" in h.agent_text(notes)


@pytest.mark.asyncio
async def test_set_mode_invalid_returns_error(tmp_cwd: Path) -> None:
    """session/set_mode с невалидным modeId → error -32602."""
    async with _server(tmp_cwd, h.chat_scenario()) as t:
        session_id = await h.handshake(t, tmp_cwd)
        resp = await h.send_set_mode(t, session_id, "no_such_mode", 3)

        assert "error" in resp
        assert resp["error"]["code"] == -32602
        assert "modeId" in resp["error"]["message"]


@pytest.mark.asyncio
async def test_notifications_delivered_before_final_response(tmp_cwd: Path) -> None:
    """Порядок (риск №1): все session/update приходят ДО финального response.

    При живой доставке через NotificationBus turn публикует update'ы по ходу,
    а финальный ответ на session/prompt уходит только после завершения turn.
    """
    async with _server(tmp_cwd, h.terminal_scenario()) as t:
        session_id = await h.handshake(t, tmp_cwd)
        await h.set_mode(t, session_id, "bypass", 3)

        # Отправляем prompt и читаем сырой поток, фиксируя порядок.
        await t.send(h.request(
            "session/prompt",
            {"sessionId": session_id, "prompt": [{"type": "text", "text": "запусти ls -ahl"}]},
            10,
        ))
        saw_update = False
        response_index = None
        seq = 0
        while True:
            msg = await t.recv(timeout=20.0)
            if msg.get("id") == 10 and ("result" in msg or "error" in msg):
                response_index = seq
                break
            method = msg.get("method")
            if method == "session/update":
                saw_update = True
                # ни один update не должен прийти после response
                assert response_index is None
            elif method is not None and "id" in msg:
                await t.send(h.result(msg["id"], {}))
            seq += 1

        assert saw_update, "ожидались session/update до ответа"
        assert response_index is not None


@pytest.mark.asyncio
async def test_tool_call_status_lifecycle(tmp_cwd: Path) -> None:
    """tool_call проходит статусы pending → in_progress → completed (08-Tool Calls)."""
    async with _server(tmp_cwd, h.terminal_scenario()) as t:
        session_id = await h.handshake(t, tmp_cwd)
        await h.set_mode(t, session_id, "bypass", 3)
        resp, notes, _ = await h.run_prompt(t, session_id, "запусти ls -ahl", 10)

        assert resp["result"]["stopReason"] == "end_turn"
        statuses = h.tool_call_statuses(notes)
        # Должны присутствовать все три статуса в правильном порядке.
        assert "pending" in statuses
        assert "in_progress" in statuses
        assert "completed" in statuses
        assert statuses.index("pending") < statuses.index("in_progress")
        assert statuses.index("in_progress") < statuses.index("completed")


@pytest.mark.asyncio
async def test_plan_notifications_published_and_replaced(tmp_cwd: Path) -> None:
    """Agent Plan (11-Agent Plan): update_plan → session/update sessionUpdate=plan.

    Два обновления в turn: каждое — полный список entries со всеми
    обязательными полями; второе отражает изменившиеся статусы.
    """
    async with _server(tmp_cwd, h.plan_scenario()) as t:
        session_id = await h.handshake(t, tmp_cwd)
        await h.set_mode(t, session_id, "bypass", 3)
        resp, notes, _ = await h.run_prompt(t, session_id, "запланируй работу", 10)

        assert resp["result"]["stopReason"] == "end_turn"
        plans = h.plan_updates(notes)
        assert len(plans) == 2, "ожидались две plan-нотификации"

        # Каждое обновление — полный список из двух entries с ACP-полями.
        for entries in plans:
            assert len(entries) == 2
            for e in entries:
                assert isinstance(e["content"], str) and e["content"]
                assert e["priority"] in ("low", "medium", "high")
                assert e["status"] in ("pending", "in_progress", "completed")

        # Второе обновление отражает новые статусы (полная замена, не merge).
        assert [e["status"] for e in plans[1]] == ["completed", "in_progress"]


@pytest.mark.asyncio
async def test_session_cancel_during_turn(tmp_cwd: Path) -> None:
    """Отмена turn клиентом: session/cancel пока сервер ждёт разрешение."""
    async with _server(tmp_cwd, h.terminal_single_scenario()) as t:
        session_id = await h.handshake(t, tmp_cwd)
        final = await h.cancel_on_permission(t, session_id, "запусти sleep", 10)
        assert final["result"]["stopReason"] == "cancelled"

"""E2E тесты полных flow взаимодействия клиента с агентом через stdio.

Транспорт-специфична только оболочка (StdioTransport + запуск subprocess);
драйвер turn, ответчики и сценарии — из общего agent_flow_harness.

Проверяемые flow: чат, fs/read, fs/write, terminal, reject (cancelled),
bypass (no ask), plan (read allow / execute reject), ошибка инструмента,
мульти-tool за turn, session/cancel.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import agent_flow_harness as h
import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent


class StdioTransport:
    """Transport поверх stdin/stdout subprocess-сервера."""

    def __init__(self, proc: asyncio.subprocess.Process) -> None:
        self._proc = proc

    async def send(self, obj: dict) -> None:
        assert self._proc.stdin is not None
        self._proc.stdin.write((json.dumps(obj) + "\n").encode())
        await self._proc.stdin.drain()

    async def recv(self, timeout: float = 15.0) -> dict:
        assert self._proc.stdout is not None
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError("No JSON message from server")
            line = await asyncio.wait_for(
                self._proc.stdout.readline(), timeout=remaining
            )
            if not line:
                raise TimeoutError("Server stdout closed")
            text = line.decode().strip()
            if not text:
                continue
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                # Пропускаем не-JSON строки (напр. сообщения о создании конфигов)
                continue


async def _start_server(
    tmp_cwd: Path, scenario_path: Path
) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        "uv", "run", "--directory", str(_PROJECT_ROOT),
        "codelab", "serve", "--stdio",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(tmp_cwd),
        env=h.server_env(tmp_cwd, scenario_path),
    )


async def _stop_server(proc: asyncio.subprocess.Process) -> None:
    if proc.stdin is not None:
        proc.stdin.close()
    try:
        await asyncio.wait_for(proc.wait(), timeout=5.0)
    except TimeoutError:
        proc.terminate()
        await proc.wait()


class _server:
    """Async context manager: поднять stdio-сервер и отдать (transport)."""

    def __init__(self, tmp_cwd: Path, scenario: dict) -> None:
        self._tmp_cwd = tmp_cwd
        self._scenario = scenario
        self._proc: asyncio.subprocess.Process | None = None

    async def __aenter__(self) -> StdioTransport:
        h.default_primary_agent(self._tmp_cwd)
        scenario_path = h.write_scenario(self._tmp_cwd, self._scenario)
        self._proc = await _start_server(self._tmp_cwd, scenario_path)
        await asyncio.sleep(0.5)
        return StdioTransport(self._proc)

    async def __aexit__(self, *exc) -> None:
        if self._proc is not None:
            await _stop_server(self._proc)


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
async def test_session_cancel_during_turn(tmp_cwd: Path) -> None:
    """Отмена turn клиентом: session/cancel пока сервер ждёт разрешение."""
    async with _server(tmp_cwd, h.terminal_single_scenario()) as t:
        session_id = await h.handshake(t, tmp_cwd)
        final = await h.cancel_on_permission(t, session_id, "запусти sleep", 10)
        assert final["result"]["stopReason"] == "cancelled"

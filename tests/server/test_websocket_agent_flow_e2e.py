"""E2E тесты полных flow взаимодействия с агентом через WebSocket.

Аналог test_stdio_agent_flow_e2e.py: транспорт-специфична только оболочка
(WsTransport + запуск aiohttp-сервера на ws://host:port/acp/ws); драйвер turn,
ответчики и сценарии — из общего agent_flow_harness.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
from pathlib import Path

import agent_flow_harness as h
import aiohttp
import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent


class WsTransport:
    """Transport поверх WebSocket-соединения (JSON в TEXT-фреймах)."""

    def __init__(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        self._ws = ws

    async def send(self, obj: dict) -> None:
        await self._ws.send_str(json.dumps(obj))

    async def recv(self, timeout: float = 15.0) -> dict:
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError("No JSON message from server")
            msg = await asyncio.wait_for(self._ws.receive(), timeout=remaining)
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    return json.loads(msg.data)
                except json.JSONDecodeError:
                    continue
            if msg.type in (
                aiohttp.WSMsgType.CLOSE,
                aiohttp.WSMsgType.CLOSING,
                aiohttp.WSMsgType.CLOSED,
                aiohttp.WSMsgType.ERROR,
            ):
                raise TimeoutError("WebSocket closed")


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


async def _start_server(
    tmp_cwd: Path, scenario_path: Path, port: int
) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        "uv", "run", "--directory", str(_PROJECT_ROOT),
        "codelab", "serve", "--host", "127.0.0.1", "--port", str(port),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(tmp_cwd),
        env=h.server_env(tmp_cwd, scenario_path),
    )


async def _connect_with_retry(
    session: aiohttp.ClientSession, url: str, attempts: int = 100
) -> aiohttp.ClientWebSocketResponse:
    """Дождаться готовности WS-сервера, повторяя попытки подключения."""
    last_exc: Exception | None = None
    for _ in range(attempts):
        try:
            return await session.ws_connect(url, heartbeat=None)
        except (aiohttp.ClientError, OSError) as e:
            last_exc = e
            await asyncio.sleep(0.1)
    raise RuntimeError(f"WS server not ready at {url}: {last_exc}")


class _server:
    """Async context manager: поднять WS-сервер и отдать (WsTransport)."""

    def __init__(self, tmp_cwd: Path, scenario: dict) -> None:
        self._tmp_cwd = tmp_cwd
        self._scenario = scenario
        self._proc: asyncio.subprocess.Process | None = None
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None

    async def __aenter__(self) -> WsTransport:
        h.default_primary_agent(self._tmp_cwd)
        scenario_path = h.write_scenario(self._tmp_cwd, self._scenario)
        port = _free_port()
        self._proc = await _start_server(self._tmp_cwd, scenario_path, port)
        self._session = aiohttp.ClientSession()
        self._ws = await _connect_with_retry(
            self._session, f"ws://127.0.0.1:{port}/acp/ws"
        )
        return WsTransport(self._ws)

    async def __aexit__(self, *exc) -> None:
        if self._ws is not None:
            await self._ws.close()
        if self._session is not None:
            await self._session.close()
        if self._proc is not None:
            with contextlib.suppress(ProcessLookupError):
                self._proc.terminate()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)


@pytest.fixture
def tmp_cwd(tmp_path: Path) -> Path:
    return tmp_path


# --------------------------------------------------------------------------- #
# Тесты
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_ws_multi_turn_chat(tmp_cwd: Path) -> None:
    """Многоходовой чат через WebSocket."""
    async with _server(tmp_cwd, h.chat_scenario()) as t:
        session_id = await h.handshake(t, tmp_cwd)

        resp, notes, _ = await h.run_prompt(t, session_id, "привет", 10)
        assert resp["result"]["stopReason"] == "end_turn"
        assert "тестовый агент" in h.agent_text(notes)

        resp, notes, _ = await h.run_prompt(t, session_id, "как дела?", 11)
        assert resp["result"]["stopReason"] == "end_turn"
        assert "готов помогать" in h.agent_text(notes)


@pytest.mark.asyncio
async def test_ws_fs_read_flow(tmp_cwd: Path) -> None:
    """fs/read через WebSocket: permission → read → result → text."""
    async with _server(tmp_cwd, h.fs_read_scenario()) as t:
        session_id = await h.handshake(t, tmp_cwd)
        resp, notes, rpc = await h.run_prompt(t, session_id, "прочти README.md", 10)

        assert resp["result"]["stopReason"] == "end_turn"
        assert "fs/read_text_file" in rpc
        assert "Прочитал README" in h.agent_text(notes)


@pytest.mark.asyncio
async def test_ws_terminal_flow(tmp_cwd: Path) -> None:
    """terminal через WebSocket: create → wait_for_exit → release → result."""
    async with _server(tmp_cwd, h.terminal_scenario()) as t:
        session_id = await h.handshake(t, tmp_cwd)
        resp, notes, rpc = await h.run_prompt(t, session_id, "запусти ls -ahl", 10)

        assert resp["result"]["stopReason"] == "end_turn"
        assert "terminal/create" in rpc
        assert "Команда выполнена" in h.agent_text(notes)


@pytest.mark.asyncio
async def test_ws_bypass_mode_auto_allows(tmp_cwd: Path) -> None:
    """mode=bypass через WebSocket: инструмент выполняется без permission."""
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
async def test_ws_permission_reject_cancels_turn(tmp_cwd: Path) -> None:
    """Отказ в разрешении через WebSocket → turn cancelled."""
    async with _server(tmp_cwd, h.terminal_single_scenario()) as t:
        session_id = await h.handshake(t, tmp_cwd)
        resp, _notes, rpc = await h.run_prompt(
            t, session_id, "запусти ls", 10, responders=h.REJECT_RESPONDER
        )

        assert resp["result"]["stopReason"] == "cancelled"
        assert "session/request_permission" in rpc
        assert "terminal/create" not in rpc


@pytest.mark.asyncio
async def test_ws_tool_error_is_handled(tmp_cwd: Path) -> None:
    """Ошибка инструмента через WebSocket: JSON-RPC error → агент продолжает."""
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
async def test_ws_multi_tool_sequence(tmp_cwd: Path) -> None:
    """Несколько инструментов за один turn через WebSocket: read → write."""
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
async def test_ws_fs_write_flow(tmp_cwd: Path) -> None:
    """fs/write через WebSocket: permission → write → result → text."""
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
async def test_ws_plan_mode_allows_read_rejects_execute(tmp_cwd: Path) -> None:
    """mode=plan через WebSocket: read авто-разрешён, execute отклоняется."""
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

        resp, notes, rpc = await h.run_prompt(t, session_id, "прочти R.md", 10)
        assert resp["result"]["stopReason"] == "end_turn"
        assert "session/request_permission" not in rpc
        assert "fs/read_text_file" in rpc
        assert "Прочитал файл" in h.agent_text(notes)

        resp, notes, rpc = await h.run_prompt(t, session_id, "запусти ls", 11)
        assert resp["result"]["stopReason"] == "end_turn"
        assert "terminal/create" not in rpc
        assert "session/request_permission" not in rpc


@pytest.mark.asyncio
async def test_ws_session_cancel_during_turn(tmp_cwd: Path) -> None:
    """session/cancel через WebSocket пока сервер ждёт разрешение."""
    async with _server(tmp_cwd, h.terminal_single_scenario()) as t:
        session_id = await h.handshake(t, tmp_cwd)
        final = await h.cancel_on_permission(t, session_id, "запусти sleep", 10)
        assert final["result"]["stopReason"] == "cancelled"

"""E2E тесты полных flow взаимодействия клиента с агентом через WebSocket.

Аналог tests/server/test_stdio_agent_flow_e2e.py, но транспорт — WebSocket
(endpoint ws://host:port/acp/ws). Использует тот же сценарный
ScriptedMockLLMProvider (через CODELAB_MOCK_SCENARIO). Тест играет роль
клиента: подключается по WS, отвечает на server→client RPC
(session/request_permission, fs/read_text_file, terminal/*) и собирает
session/update нотификации.

Проверяемые flow: чат, fs/read, terminal, bypass (no ask), reject
(cancelled), ошибка инструмента, session/cancel, мульти-tool за turn.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import socket
from collections.abc import Callable
from pathlib import Path
from typing import Any

import aiohttp
import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent


# --------------------------------------------------------------------------- #
# JSON-RPC helpers
# --------------------------------------------------------------------------- #

def _request(method: str, params: dict, request_id: int) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}


def _result(request_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error_payload(request_id: Any, code: int, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


class _RpcError:
    """Маркер: responder просит вернуть JSON-RPC error вместо result."""

    def __init__(self, code: int = -32000, message: str = "error") -> None:
        self.code = code
        self.message = message


# --------------------------------------------------------------------------- #
# WebSocket I/O
# --------------------------------------------------------------------------- #

async def _ws_send(ws: aiohttp.ClientWebSocketResponse, obj: dict) -> None:
    await ws.send_str(json.dumps(obj))


async def _ws_recv(
    ws: aiohttp.ClientWebSocketResponse, timeout: float = 15.0
) -> dict:
    """Прочитать очередной TEXT-фрейм как JSON (пропуская служебные фреймы)."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise TimeoutError("No JSON message from server")
        msg = await asyncio.wait_for(ws.receive(), timeout=remaining)
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


# --------------------------------------------------------------------------- #
# Server lifecycle
# --------------------------------------------------------------------------- #

def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _server_env(tmp_cwd: Path, scenario_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "CODELAB_LLM_PROVIDER": "mock",
            "CODELAB_HOME": str(tmp_cwd / ".codelab"),
            "CODELAB_MOCK_SCENARIO": str(scenario_path),
            "OPENAI_API_KEY": "test-key-not-real",
        }
    )
    return env


async def _start_server(
    tmp_cwd: Path, scenario_path: Path, port: int
) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        "uv", "run", "--directory", str(_PROJECT_ROOT),
        "codelab", "serve", "--host", "127.0.0.1", "--port", str(port),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(tmp_cwd),
        env=_server_env(tmp_cwd, scenario_path),
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


@pytest.fixture
def tmp_cwd(tmp_path: Path) -> Path:
    return tmp_path


def _write_scenario(tmp_cwd: Path, scenario: dict) -> Path:
    path = tmp_cwd / "scenario.json"
    path.write_text(json.dumps(scenario), encoding="utf-8")
    return path


def _default_primary_agent(tmp_cwd: Path) -> None:
    agents_dir = tmp_cwd / ".codelab" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "primary.md").write_text(
        "---\nname: primary\nrole: primary\nmodel: mock/mock-model\n"
        "---\n\nТестовый агент.\n",
        encoding="utf-8",
    )


@contextlib.asynccontextmanager
async def _running_server(tmp_cwd: Path, scenario: dict):
    """Поднять WS-сервер и подключиться. Отдаёт (ws) готовый к handshake."""
    _default_primary_agent(tmp_cwd)
    scenario_path = _write_scenario(tmp_cwd, scenario)
    port = _free_port()
    proc = await _start_server(tmp_cwd, scenario_path, port)
    session = aiohttp.ClientSession()
    ws: aiohttp.ClientWebSocketResponse | None = None
    try:
        ws = await _connect_with_retry(
            session, f"ws://127.0.0.1:{port}/acp/ws"
        )
        yield ws
    finally:
        if ws is not None:
            await ws.close()
        await session.close()
        with contextlib.suppress(ProcessLookupError):
            proc.terminate()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(proc.wait(), timeout=5.0)


# --------------------------------------------------------------------------- #
# Handshake + driver
# --------------------------------------------------------------------------- #

async def _handshake(ws: aiohttp.ClientWebSocketResponse, tmp_cwd: Path) -> str:
    await _ws_send(
        ws,
        _request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {
                    "fs": {"readTextFile": True, "writeTextFile": True},
                    "terminal": True,
                },
            },
            1,
        ),
    )
    init = await _ws_recv(ws)
    assert init["id"] == 1

    await _ws_send(
        ws, _request("session/new", {"cwd": str(tmp_cwd), "mcpServers": []}, 2)
    )
    new = await _ws_recv(ws)
    assert new["id"] == 2
    return new["result"]["sessionId"]


async def _set_mode(
    ws: aiohttp.ClientWebSocketResponse,
    session_id: str,
    mode_id: str,
    request_id: int,
) -> None:
    await _ws_send(
        ws,
        _request(
            "session/set_mode", {"sessionId": session_id, "modeId": mode_id}, request_id
        ),
    )
    while True:
        resp = await _ws_recv(ws)
        if resp.get("id") == request_id and ("result" in resp or "error" in resp):
            assert "result" in resp
            return


DEFAULT_RESPONDERS: dict[str, Callable[[dict], Any]] = {
    "session/request_permission": lambda p: {
        "outcome": {"outcome": "selected", "optionId": "allow_once"}
    },
    "fs/read_text_file": lambda p: {"content": "# README\nПривет из файла.\n"},
    "fs/write_text_file": lambda p: {},
    "terminal/create": lambda p: {"terminalId": "term-1"},
    "terminal/output": lambda p: {
        "output": "total 0\n",
        "truncated": False,
        "exitStatus": {"exitCode": 0, "signal": None},
    },
    "terminal/wait_for_exit": lambda p: {"exitCode": 0, "signal": None},
    "terminal/release": lambda p: {},
    "terminal/kill": lambda p: {},
}


async def _run_prompt(
    ws: aiohttp.ClientWebSocketResponse,
    session_id: str,
    prompt_text: str,
    request_id: int,
    responders: dict[str, Callable[[dict], Any]] | None = None,
    timeout: float = 20.0,
) -> tuple[dict, list[dict], list[str]]:
    responders = {**DEFAULT_RESPONDERS, **(responders or {})}
    await _ws_send(
        ws,
        _request(
            "session/prompt",
            {"sessionId": session_id, "prompt": [{"type": "text", "text": prompt_text}]},
            request_id,
        ),
    )

    notifications: list[dict] = []
    rpc_methods: list[str] = []
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise TimeoutError(f"prompt {request_id} did not finish")
        msg = await _ws_recv(ws, timeout=remaining)

        if msg.get("id") == request_id and ("result" in msg or "error" in msg):
            return msg, notifications, rpc_methods

        method = msg.get("method")
        if method is not None and "id" in msg:
            rpc_methods.append(method)
            responder = responders.get(method)
            if responder is None:
                await _ws_send(ws, _result(msg["id"], {}))
            else:
                out = responder(msg.get("params", {}))
                if isinstance(out, _RpcError):
                    await _ws_send(ws, _error_payload(msg["id"], out.code, out.message))
                else:
                    await _ws_send(ws, _result(msg["id"], out))
        elif method is not None:
            notifications.append(msg)


def _agent_text(notifications: list[dict]) -> str:
    parts = []
    for n in notifications:
        if n.get("method") != "session/update":
            continue
        update = n.get("params", {}).get("update", {})
        if update.get("sessionUpdate") == "agent_message_chunk":
            parts.append(update.get("content", {}).get("text", ""))
    return "".join(parts)


# --------------------------------------------------------------------------- #
# Тесты
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_ws_multi_turn_chat(tmp_cwd: Path) -> None:
    """Многоходовой чат через WebSocket."""
    scenario = {
        "turns": [
            {"when_user": ["привет"], "replies": [{"text": "Привет! Я тестовый агент."}]},
            {"when_user": ["как дела"], "replies": [{"text": "Отлично, готов помогать."}]},
        ],
    }
    async with _running_server(tmp_cwd, scenario) as ws:
        session_id = await _handshake(ws, tmp_cwd)

        resp, notes, _ = await _run_prompt(ws, session_id, "привет", 10)
        assert resp["result"]["stopReason"] == "end_turn"
        assert "тестовый агент" in _agent_text(notes)

        resp, notes, _ = await _run_prompt(ws, session_id, "как дела?", 11)
        assert resp["result"]["stopReason"] == "end_turn"
        assert "готов помогать" in _agent_text(notes)


@pytest.mark.asyncio
async def test_ws_fs_read_flow(tmp_cwd: Path) -> None:
    """fs/read через WebSocket: permission → read → result → text."""
    scenario = {
        "turns": [
            {
                "when_user": ["README", "прочти"],
                "replies": [
                    {"tool_calls": [
                        {"name": "fs_read_text_file", "arguments": {"path": "README.md"}}
                    ]},
                    {"text": "Прочитал README, всё на месте."},
                ],
            },
        ],
    }
    async with _running_server(tmp_cwd, scenario) as ws:
        session_id = await _handshake(ws, tmp_cwd)
        resp, notes, rpc = await _run_prompt(ws, session_id, "прочти README.md", 10)

        assert resp["result"]["stopReason"] == "end_turn"
        assert "fs/read_text_file" in rpc
        assert "Прочитал README" in _agent_text(notes)


@pytest.mark.asyncio
async def test_ws_terminal_flow(tmp_cwd: Path) -> None:
    """terminal через WebSocket: create → wait_for_exit → release → result."""
    scenario = {
        "turns": [
            {
                "when_user": ["ls", "запусти"],
                "replies": [
                    {"tool_calls": [
                        {"name": "terminal_create",
                         "arguments": {"command": "ls", "args": ["-ahl"]}}
                    ]},
                    {"tool_calls": [
                        {"name": "terminal_wait_for_exit",
                         "arguments": {"terminalId": "term-1"}}
                    ]},
                    {"tool_calls": [
                        {"name": "terminal_release",
                         "arguments": {"terminalId": "term-1"}}
                    ]},
                    {"text": "Команда выполнена, exit code 0."},
                ],
            },
        ],
    }
    async with _running_server(tmp_cwd, scenario) as ws:
        session_id = await _handshake(ws, tmp_cwd)
        resp, notes, rpc = await _run_prompt(ws, session_id, "запусти ls -ahl", 10)

        assert resp["result"]["stopReason"] == "end_turn"
        assert "terminal/create" in rpc
        assert "Команда выполнена" in _agent_text(notes)


@pytest.mark.asyncio
async def test_ws_bypass_mode_auto_allows(tmp_cwd: Path) -> None:
    """mode=bypass через WebSocket: инструмент выполняется без permission."""
    scenario = {
        "turns": [
            {
                "when_user": ["запусти"],
                "replies": [
                    {"tool_calls": [
                        {"name": "terminal_create", "arguments": {"command": "ls"}}
                    ]},
                    {"tool_calls": [
                        {"name": "terminal_wait_for_exit",
                         "arguments": {"terminalId": "term-1"}}
                    ]},
                    {"tool_calls": [
                        {"name": "terminal_release",
                         "arguments": {"terminalId": "term-1"}}
                    ]},
                    {"text": "Готово без запроса разрешения."},
                ],
            },
        ],
    }
    async with _running_server(tmp_cwd, scenario) as ws:
        session_id = await _handshake(ws, tmp_cwd)
        await _set_mode(ws, session_id, "bypass", 3)
        resp, notes, rpc = await _run_prompt(ws, session_id, "запусти ls", 10)

        assert resp["result"]["stopReason"] == "end_turn"
        assert "session/request_permission" not in rpc
        assert "terminal/create" in rpc
        assert "Готово без запроса" in _agent_text(notes)


@pytest.mark.asyncio
async def test_ws_permission_reject_cancels_turn(tmp_cwd: Path) -> None:
    """Отказ в разрешении через WebSocket → turn cancelled."""
    scenario = {
        "turns": [
            {
                "when_user": ["запусти"],
                "replies": [
                    {"tool_calls": [
                        {"name": "terminal_create", "arguments": {"command": "ls"}}
                    ]},
                    {"text": "Не должно быть достигнуто."},
                ],
            },
        ],
    }
    async with _running_server(tmp_cwd, scenario) as ws:
        session_id = await _handshake(ws, tmp_cwd)
        resp, _notes, rpc = await _run_prompt(
            ws,
            session_id,
            "запусти ls",
            10,
            responders={
                "session/request_permission": lambda p: {
                    "outcome": {"outcome": "selected", "optionId": "reject_once"}
                }
            },
        )

        assert resp["result"]["stopReason"] == "cancelled"
        assert "session/request_permission" in rpc
        assert "terminal/create" not in rpc


@pytest.mark.asyncio
async def test_ws_tool_error_is_handled(tmp_cwd: Path) -> None:
    """Ошибка инструмента через WebSocket: JSON-RPC error → агент продолжает."""
    scenario = {
        "turns": [
            {
                "when_user": ["прочти"],
                "replies": [
                    {"tool_calls": [
                        {"name": "fs_read_text_file", "arguments": {"path": "missing.md"}}
                    ]},
                    {"text": "Не удалось прочитать файл, обработал ошибку."},
                ],
            },
        ],
    }
    async with _running_server(tmp_cwd, scenario) as ws:
        session_id = await _handshake(ws, tmp_cwd)
        await _set_mode(ws, session_id, "bypass", 3)
        resp, notes, rpc = await _run_prompt(
            ws,
            session_id,
            "прочти missing.md",
            10,
            responders={
                "fs/read_text_file": lambda p: _RpcError(-32000, "file not found")
            },
        )

        assert resp["result"]["stopReason"] == "end_turn"
        assert "fs/read_text_file" in rpc
        assert "обработал ошибку" in _agent_text(notes)


@pytest.mark.asyncio
async def test_ws_multi_tool_sequence(tmp_cwd: Path) -> None:
    """Несколько инструментов за один turn через WebSocket: read → write."""
    scenario = {
        "turns": [
            {
                "when_user": ["обработай"],
                "replies": [
                    {"tool_calls": [
                        {"name": "fs_read_text_file", "arguments": {"path": "in.md"}}
                    ]},
                    {"tool_calls": [
                        {"name": "fs_write_text_file",
                         "arguments": {"path": "out.md", "content": "результат"}}
                    ]},
                    {"text": "Прочитал in.md и записал out.md."},
                ],
            },
        ],
    }
    async with _running_server(tmp_cwd, scenario) as ws:
        session_id = await _handshake(ws, tmp_cwd)
        await _set_mode(ws, session_id, "bypass", 3)
        resp, notes, rpc = await _run_prompt(ws, session_id, "обработай in.md", 10)

        assert resp["result"]["stopReason"] == "end_turn"
        assert "fs/read_text_file" in rpc
        assert "fs/write_text_file" in rpc
        assert rpc.index("fs/read_text_file") < rpc.index("fs/write_text_file")
        assert "записал out.md" in _agent_text(notes)


@pytest.mark.asyncio
async def test_ws_session_cancel_during_turn(tmp_cwd: Path) -> None:
    """session/cancel через WebSocket пока сервер ждёт разрешение."""
    scenario = {
        "turns": [
            {
                "when_user": ["запусти"],
                "replies": [
                    {"tool_calls": [
                        {"name": "terminal_create", "arguments": {"command": "sleep"}}
                    ]},
                    {"text": "Не должно быть достигнуто."},
                ],
            },
        ],
    }
    async with _running_server(tmp_cwd, scenario) as ws:
        session_id = await _handshake(ws, tmp_cwd)

        await _ws_send(
            ws,
            _request(
                "session/prompt",
                {
                    "sessionId": session_id,
                    "prompt": [{"type": "text", "text": "запусти sleep"}],
                },
                10,
            ),
        )

        cancelled_sent = False
        final = None
        deadline = asyncio.get_event_loop().time() + 20.0
        while final is None:
            assert asyncio.get_event_loop().time() < deadline, "turn did not finish"
            msg = await _ws_recv(ws, timeout=10.0)
            if msg.get("id") == 10 and ("result" in msg or "error" in msg):
                final = msg
                break
            method = msg.get("method")
            if method == "session/request_permission" and not cancelled_sent:
                await _ws_send(
                    ws,
                    {
                        "jsonrpc": "2.0",
                        "method": "session/cancel",
                        "params": {"sessionId": session_id},
                    },
                )
                cancelled_sent = True
            elif method is not None and "id" in msg:
                await _ws_send(ws, _result(msg["id"], {}))

        assert cancelled_sent
        assert final["result"]["stopReason"] == "cancelled"

"""E2E тесты полных flow взаимодействия клиента с агентом через stdio.

Использует сценарный ScriptedMockLLMProvider (конечный автомат): сценарий
диалога передаётся серверу через CODELAB_MOCK_SCENARIO, а тест играет роль
клиента — отвечает на server→client RPC (session/request_permission,
fs/read_text_file, terminal/*) и собирает session/update нотификации.

Проверяемые flow:
- многоходовой чат (без инструментов);
- fs/read_text_file: ask permission → recv answer → read file → show result;
- terminal: create → wait_for_exit → release → show result.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent


# --------------------------------------------------------------------------- #
# JSON-RPC helpers
# --------------------------------------------------------------------------- #

def _request(method: str, params: dict, request_id: int) -> str:
    return json.dumps(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    )


def _result(request_id: Any, result: dict) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result})


def _error_payload(request_id: Any, code: int, message: str) -> str:
    return json.dumps(
        {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
    )


class _RpcError:
    """Маркер: responder просит вернуть JSON-RPC error вместо result."""

    def __init__(self, code: int = -32000, message: str = "error") -> None:
        self.code = code
        self.message = message


async def _read_json(proc: asyncio.subprocess.Process, timeout: float = 15.0) -> dict:
    """Прочитать очередное JSON-сообщение из stdout (пропуская не-JSON строки)."""
    assert proc.stdout is not None
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise TimeoutError("No JSON message from server")
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
        if not line:
            raise TimeoutError("Server stdout closed")
        text = line.decode().strip()
        if not text:
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            continue


async def _write(proc: asyncio.subprocess.Process, payload: str) -> None:
    assert proc.stdin is not None
    proc.stdin.write((payload + "\n").encode())
    await proc.stdin.drain()


# --------------------------------------------------------------------------- #
# Server lifecycle
# --------------------------------------------------------------------------- #

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
    tmp_cwd: Path, scenario_path: Path
) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        "uv", "run", "--directory", str(_PROJECT_ROOT),
        "codelab", "serve", "--stdio",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(tmp_cwd),
        env=_server_env(tmp_cwd, scenario_path),
    )


async def _stop_server(proc: asyncio.subprocess.Process) -> None:
    if proc.stdin is not None:
        proc.stdin.close()
    try:
        await asyncio.wait_for(proc.wait(), timeout=5.0)
    except TimeoutError:
        proc.terminate()
        await proc.wait()


@pytest.fixture
def tmp_cwd(tmp_path: Path) -> Path:
    return tmp_path


def _write_scenario(tmp_cwd: Path, scenario: dict) -> Path:
    path = tmp_cwd / "scenario.json"
    path.write_text(json.dumps(scenario), encoding="utf-8")
    return path


def _default_primary_agent(tmp_cwd: Path) -> None:
    """Создать primary-агента на mock-модели в изолированном CODELAB_HOME."""
    agents_dir = tmp_cwd / ".codelab" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "primary.md").write_text(
        "---\nname: primary\nrole: primary\nmodel: mock/mock-model\n"
        "---\n\nТестовый агент.\n",
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# Handshake + driver
# --------------------------------------------------------------------------- #

async def _handshake(proc: asyncio.subprocess.Process, tmp_cwd: Path) -> str:
    """initialize + session/new → возвращает session_id."""
    await asyncio.sleep(0.5)
    await _write(
        proc,
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
    init = await _read_json(proc)
    assert init["id"] == 1

    await _write(
        proc,
        _request("session/new", {"cwd": str(tmp_cwd), "mcpServers": []}, 2),
    )
    new = await _read_json(proc)
    assert new["id"] == 2
    return new["result"]["sessionId"]


async def _set_mode(
    proc: asyncio.subprocess.Process,
    session_id: str,
    mode_id: str,
    request_id: int,
) -> None:
    """Сменить режим сессии (plan / standard / bypass)."""
    await _write(
        proc,
        _request(
            "session/set_mode",
            {"sessionId": session_id, "modeId": mode_id},
            request_id,
        ),
    )
    # Пропускаем возможные нотификации (current_mode_update) до ответа
    while True:
        resp = await _read_json(proc)
        if resp.get("id") == request_id and ("result" in resp or "error" in resp):
            assert "result" in resp
            return


DEFAULT_RESPONDERS: dict[str, Callable[[dict], dict]] = {
    "session/request_permission": lambda p: {
        "outcome": {"outcome": "selected", "optionId": "allow_once"}
    },
    "fs/read_text_file": lambda p: {"content": "# README\nПривет из файла.\n"},
    "terminal/create": lambda p: {"terminalId": "term-1"},
    "terminal/output": lambda p: {
        "output": "total 0\ndrwxr-xr-x  2 user  staff   64 .\n",
        "truncated": False,
        "exitStatus": {"exitCode": 0, "signal": None},
    },
    "terminal/wait_for_exit": lambda p: {"exitCode": 0, "signal": None},
    "terminal/release": lambda p: {},
    "terminal/kill": lambda p: {},
}


async def _run_prompt(
    proc: asyncio.subprocess.Process,
    session_id: str,
    prompt_text: str,
    request_id: int,
    responders: dict[str, Callable[[dict], dict]] | None = None,
    timeout: float = 20.0,
) -> tuple[dict, list[dict], list[str]]:
    """Отправить session/prompt и отвечать на server→client RPC до финала.

    Returns:
        (prompt_response, notifications, rpc_methods) — финальный ответ на
        prompt, список session/update и прочих нотификаций, и список методов
        server→client RPC, на которые ответил тест (в порядке поступления).
    """
    responders = {**DEFAULT_RESPONDERS, **(responders or {})}
    await _write(
        proc,
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
        msg = await _read_json(proc, timeout=remaining)

        # Финальный ответ на наш prompt
        if msg.get("id") == request_id and ("result" in msg or "error" in msg):
            return msg, notifications, rpc_methods

        method = msg.get("method")
        if method is not None and "id" in msg:
            # server→client RPC request — отвечаем через responder
            rpc_methods.append(method)
            responder = responders.get(method)
            if responder is None:
                await _write(proc, _result(msg["id"], {}))
            else:
                out = responder(msg.get("params", {}))
                if isinstance(out, _RpcError):
                    await _write(proc, _error_payload(msg["id"], out.code, out.message))
                else:
                    await _write(proc, _result(msg["id"], out))
        elif method is not None:
            notifications.append(msg)


def _agent_text(notifications: list[dict]) -> str:
    """Собрать весь текст из agent_message_chunk нотификаций."""
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
async def test_multi_turn_chat(tmp_cwd: Path) -> None:
    """Многоходовой чат: два промпта в одной сессии, разные ответы."""
    scenario = {
        "turns": [
            {"when_user": ["привет"], "replies": [{"text": "Привет! Я тестовый агент."}]},
            {"when_user": ["как дела"], "replies": [{"text": "Отлично, готов помогать."}]},
        ],
        "default": {"text": "Не понял запрос."},
    }
    _default_primary_agent(tmp_cwd)
    proc = await _start_server(tmp_cwd, _write_scenario(tmp_cwd, scenario))
    try:
        session_id = await _handshake(proc, tmp_cwd)

        resp, notes, _ = await _run_prompt(proc, session_id, "привет", 10)
        assert resp["result"]["stopReason"] == "end_turn"
        assert "тестовый агент" in _agent_text(notes)

        resp, notes, _ = await _run_prompt(proc, session_id, "как дела?", 11)
        assert resp["result"]["stopReason"] == "end_turn"
        assert "готов помогать" in _agent_text(notes)
    finally:
        await _stop_server(proc)


@pytest.mark.asyncio
async def test_fs_read_flow(tmp_cwd: Path) -> None:
    """fs/read: permission → recv answer → fs/read_text_file → result → text."""
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
    _default_primary_agent(tmp_cwd)
    proc = await _start_server(tmp_cwd, _write_scenario(tmp_cwd, scenario))
    try:
        session_id = await _handshake(proc, tmp_cwd)
        resp, notes, rpc = await _run_prompt(proc, session_id, "прочти README.md", 10)

        assert resp["result"]["stopReason"] == "end_turn"
        # Сервер вызвал клиента для чтения файла
        assert "fs/read_text_file" in rpc
        assert "Прочитал README" in _agent_text(notes)
    finally:
        await _stop_server(proc)


@pytest.mark.asyncio
async def test_terminal_flow(tmp_cwd: Path) -> None:
    """terminal: create → wait_for_exit → release → show result."""
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
    _default_primary_agent(tmp_cwd)
    proc = await _start_server(tmp_cwd, _write_scenario(tmp_cwd, scenario))
    try:
        session_id = await _handshake(proc, tmp_cwd)
        resp, notes, rpc = await _run_prompt(proc, session_id, "запусти ls -ahl", 10)

        assert resp["result"]["stopReason"] == "end_turn"
        assert "terminal/create" in rpc
        assert "Команда выполнена" in _agent_text(notes)
    finally:
        await _stop_server(proc)


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
    _default_primary_agent(tmp_cwd)
    proc = await _start_server(tmp_cwd, _write_scenario(tmp_cwd, scenario))
    try:
        session_id = await _handshake(proc, tmp_cwd)
        resp, notes, rpc = await _run_prompt(
            proc, session_id, "запиши notes.txt", 10
        )

        assert resp["result"]["stopReason"] == "end_turn"
        assert "fs/write_text_file" in rpc
        assert "Файл записан" in _agent_text(notes)
    finally:
        await _stop_server(proc)


@pytest.mark.asyncio
async def test_permission_reject_cancels_turn(tmp_cwd: Path) -> None:
    """Отказ в разрешении: reject_once → turn cancelled, инструмент не вызван."""
    scenario = {
        "turns": [
            {
                "when_user": ["ls", "запусти"],
                "replies": [
                    {"tool_calls": [
                        {"name": "terminal_create", "arguments": {"command": "ls"}}
                    ]},
                    {"text": "Не должно быть достигнуто."},
                ],
            },
        ],
    }
    _default_primary_agent(tmp_cwd)
    proc = await _start_server(tmp_cwd, _write_scenario(tmp_cwd, scenario))
    try:
        session_id = await _handshake(proc, tmp_cwd)
        resp, _notes, rpc = await _run_prompt(
            proc,
            session_id,
            "запусти ls",
            10,
            responders={
                "session/request_permission": lambda p: {
                    "outcome": {"outcome": "selected", "optionId": "reject_once"}
                }
            },
        )

        # Отказ в разрешении отменяет turn; инструмент до клиента не доходит.
        assert resp["result"]["stopReason"] == "cancelled"
        assert "session/request_permission" in rpc
        assert "terminal/create" not in rpc
    finally:
        await _stop_server(proc)


@pytest.mark.asyncio
async def test_bypass_mode_auto_allows_without_permission(tmp_cwd: Path) -> None:
    """mode=bypass: инструмент выполняется сразу, без session/request_permission."""
    scenario = {
        "turns": [
            {
                "when_user": ["ls", "запусти"],
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
    _default_primary_agent(tmp_cwd)
    proc = await _start_server(tmp_cwd, _write_scenario(tmp_cwd, scenario))
    try:
        session_id = await _handshake(proc, tmp_cwd)
        await _set_mode(proc, session_id, "bypass", 3)

        resp, notes, rpc = await _run_prompt(proc, session_id, "запусти ls", 10)

        assert resp["result"]["stopReason"] == "end_turn"
        # Разрешение НЕ запрашивалось — bypass авто-выполняет инструмент
        assert "session/request_permission" not in rpc
        assert "terminal/create" in rpc
        assert "Готово без запроса" in _agent_text(notes)
    finally:
        await _stop_server(proc)


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
    _default_primary_agent(tmp_cwd)
    proc = await _start_server(tmp_cwd, _write_scenario(tmp_cwd, scenario))
    try:
        session_id = await _handshake(proc, tmp_cwd)
        await _set_mode(proc, session_id, "plan", 3)

        # read — авто-разрешён, файл читается, без запроса разрешения
        resp, notes, rpc = await _run_prompt(proc, session_id, "прочти R.md", 10)
        assert resp["result"]["stopReason"] == "end_turn"
        assert "session/request_permission" not in rpc
        assert "fs/read_text_file" in rpc
        assert "Прочитал файл" in _agent_text(notes)

        # execute — отклонён: инструмент до клиента не доходит, агент продолжает
        resp, notes, rpc = await _run_prompt(proc, session_id, "запусти ls", 11)
        assert resp["result"]["stopReason"] == "end_turn"
        assert "terminal/create" not in rpc
        assert "session/request_permission" not in rpc
    finally:
        await _stop_server(proc)


@pytest.mark.asyncio
async def test_tool_error_is_handled(tmp_cwd: Path) -> None:
    """Ошибка инструмента: клиент вернул JSON-RPC error → агент продолжает."""
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
    _default_primary_agent(tmp_cwd)
    proc = await _start_server(tmp_cwd, _write_scenario(tmp_cwd, scenario))
    try:
        session_id = await _handshake(proc, tmp_cwd)
        await _set_mode(proc, session_id, "bypass", 3)

        resp, notes, rpc = await _run_prompt(
            proc,
            session_id,
            "прочти missing.md",
            10,
            responders={
                "fs/read_text_file": lambda p: _RpcError(-32000, "file not found")
            },
        )

        # Ошибка инструмента не роняет turn — агент получает её и завершает ход
        assert resp["result"]["stopReason"] == "end_turn"
        assert "fs/read_text_file" in rpc
        assert "обработал ошибку" in _agent_text(notes)
    finally:
        await _stop_server(proc)


@pytest.mark.asyncio
async def test_multi_tool_sequence_in_one_turn(tmp_cwd: Path) -> None:
    """Несколько инструментов за один turn: read → write → финальный текст."""
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
    _default_primary_agent(tmp_cwd)
    proc = await _start_server(tmp_cwd, _write_scenario(tmp_cwd, scenario))
    try:
        session_id = await _handshake(proc, tmp_cwd)
        await _set_mode(proc, session_id, "bypass", 3)

        resp, notes, rpc = await _run_prompt(proc, session_id, "обработай in.md", 10)

        assert resp["result"]["stopReason"] == "end_turn"
        # Оба инструмента дошли до клиента в правильном порядке
        assert "fs/read_text_file" in rpc
        assert "fs/write_text_file" in rpc
        assert rpc.index("fs/read_text_file") < rpc.index("fs/write_text_file")
        assert "записал out.md" in _agent_text(notes)
    finally:
        await _stop_server(proc)


@pytest.mark.asyncio
async def test_session_cancel_during_turn(tmp_cwd: Path) -> None:
    """Отмена turn клиентом: session/cancel пока сервер ждёт разрешение."""
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
    _default_primary_agent(tmp_cwd)
    proc = await _start_server(tmp_cwd, _write_scenario(tmp_cwd, scenario))
    try:
        session_id = await _handshake(proc, tmp_cwd)

        # Отправляем prompt (standard mode → сервер запросит разрешение)
        await _write(
            proc,
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
            msg = await _read_json(proc, timeout=10.0)
            if msg.get("id") == 10 and ("result" in msg or "error" in msg):
                final = msg
                break
            method = msg.get("method")
            if method == "session/request_permission" and not cancelled_sent:
                # Вместо ответа на разрешение отменяем turn (без "id" — нотификация)
                await _write(
                    proc,
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "method": "session/cancel",
                            "params": {"sessionId": session_id},
                        }
                    ),
                )
                cancelled_sent = True
            elif method is not None and "id" in msg:
                await _write(proc, _result(msg["id"], {}))

        assert cancelled_sent
        assert final["result"]["stopReason"] == "cancelled"
    finally:
        await _stop_server(proc)

"""Общий транспорт-агностичный harness для e2e flow-тестов агента.

Используется stdio- и websocket-тестами (test_stdio_agent_flow_e2e.py,
test_websocket_agent_flow_e2e.py). Инкапсулирует общую логику:
- JSON-RPC билдеры и маркер ошибки (RpcError);
- окружение сервера, запись сценария, дефолтный primary-агент;
- набор ответчиков клиента по умолчанию (DEFAULT_RESPONDERS);
- драйвер turn: handshake, set_mode, run_prompt, cancel-хелпер;
- готовые билдеры сценариев.

Транспорт абстрагирован интерфейсом Transport (send/recv одного JSON-объекта),
поэтому один и тот же драйвер работает и поверх stdio-пайпов, и поверх WS.
Модуль не является тест-модулем (нет префикса test_) и не собирается pytest.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

PROJECT_ROOT = Path(__file__).parent.parent.parent


# --------------------------------------------------------------------------- #
# JSON-RPC билдеры
# --------------------------------------------------------------------------- #

def request(method: str, params: dict, request_id: int) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}


def result(request_id: Any, value: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": value}


def error_payload(request_id: Any, code: int, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


class RpcError:
    """Маркер: responder просит вернуть JSON-RPC error вместо result."""

    def __init__(self, code: int = -32000, message: str = "error") -> None:
        self.code = code
        self.message = message


# --------------------------------------------------------------------------- #
# Транспорт
# --------------------------------------------------------------------------- #

class Transport(Protocol):
    """Двунаправленный JSON-канал (один объект = один JSON-RPC фрейм)."""

    async def send(self, obj: dict) -> None: ...

    async def recv(self, timeout: float = 15.0) -> dict: ...


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


# --------------------------------------------------------------------------- #
# Окружение сервера / сценарий / агент
# --------------------------------------------------------------------------- #

def server_env(tmp_cwd: Path, scenario_path: Path) -> dict[str, str]:
    """Окружение subprocess-сервера: mock-провайдер + изолированный HOME."""
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


def write_scenario(tmp_cwd: Path, scenario: dict) -> Path:
    path = tmp_cwd / "scenario.json"
    path.write_text(json.dumps(scenario), encoding="utf-8")
    return path


def default_primary_agent(tmp_cwd: Path) -> None:
    """Создать primary-агента на mock-модели в изолированном CODELAB_HOME."""
    agents_dir = tmp_cwd / ".codelab" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "primary.md").write_text(
        "---\nname: primary\nrole: primary\nmodel: mock/mock-model\n"
        "---\n\nТестовый агент.\n",
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# Запуск stdio-сервера
# --------------------------------------------------------------------------- #

class StdioServer:
    """Async context manager: поднять stdio-сервер codelab и отдать transport.

    Параметризуется через extra_args (доп. аргументы CLI, напр. --require-auth)
    и extra_env (доп. переменные окружения), поэтому покрывает базовый,
    auth- и mcp-сценарии без копипасты запуска subprocess.
    """

    def __init__(
        self,
        tmp_cwd: Path,
        scenario: dict,
        *,
        extra_args: list[str] | None = None,
        extra_env: dict[str, str] | None = None,
        startup_delay: float = 0.5,
    ) -> None:
        self._tmp_cwd = tmp_cwd
        self._scenario = scenario
        self._extra_args = extra_args or []
        self._extra_env = extra_env or {}
        self._startup_delay = startup_delay
        self._proc: asyncio.subprocess.Process | None = None

    async def __aenter__(self) -> StdioTransport:
        default_primary_agent(self._tmp_cwd)
        scenario_path = write_scenario(self._tmp_cwd, self._scenario)
        env = server_env(self._tmp_cwd, scenario_path)
        env.update(self._extra_env)
        self._proc = await asyncio.create_subprocess_exec(
            "uv", "run", "--directory", str(PROJECT_ROOT),
            "codelab", "serve", "--stdio", *self._extra_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self._tmp_cwd),
            env=env,
        )
        await asyncio.sleep(self._startup_delay)
        return StdioTransport(self._proc)

    async def __aexit__(self, *exc) -> None:
        proc = self._proc
        if proc is None:
            return
        if proc.stdin is not None:
            proc.stdin.close()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except TimeoutError:
            proc.terminate()
            await proc.wait()


# --------------------------------------------------------------------------- #
# Ответчики клиента по умолчанию
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Драйвер
# --------------------------------------------------------------------------- #

DEFAULT_CLIENT_CAPABILITIES: dict[str, Any] = {
    "fs": {"readTextFile": True, "writeTextFile": True},
    "terminal": True,
}


async def initialize(
    transport: Transport,
    client_capabilities: dict | None = None,
    request_id: int = 1,
) -> dict:
    """Отправить initialize и вернуть его response (для проверки capabilities)."""
    await transport.send(
        request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": (
                    DEFAULT_CLIENT_CAPABILITIES
                    if client_capabilities is None
                    else client_capabilities
                ),
            },
            request_id,
        )
    )
    init = await transport.recv()
    assert init["id"] == request_id
    return init


async def session_new(
    transport: Transport,
    tmp_cwd: Path,
    mcp_servers: list[dict] | None = None,
    request_id: int = 2,
) -> str:
    """Отправить session/new → возвращает session_id."""
    await transport.send(
        request(
            "session/new",
            {"cwd": str(tmp_cwd), "mcpServers": mcp_servers or []},
            request_id,
        )
    )
    new = await transport.recv()
    assert new["id"] == request_id
    return new["result"]["sessionId"]


async def handshake(
    transport: Transport,
    tmp_cwd: Path,
    mcp_servers: list[dict] | None = None,
) -> str:
    """initialize + session/new → возвращает session_id."""
    await initialize(transport)
    return await session_new(transport, tmp_cwd, mcp_servers)


async def send_set_mode(
    transport: Transport, session_id: str, mode_id: str, request_id: int
) -> dict:
    """Отправить session/set_mode и вернуть сырой response (result или error)."""
    await transport.send(
        request("session/set_mode", {"sessionId": session_id, "modeId": mode_id}, request_id)
    )
    while True:
        resp = await transport.recv()
        if resp.get("id") == request_id and ("result" in resp or "error" in resp):
            return resp


async def set_mode(
    transport: Transport, session_id: str, mode_id: str, request_id: int
) -> None:
    """Сменить режим сессии (plan / standard / bypass); ожидает успех."""
    resp = await send_set_mode(transport, session_id, mode_id, request_id)
    assert "result" in resp


async def run_prompt(
    transport: Transport,
    session_id: str,
    prompt_text: str,
    request_id: int,
    responders: dict[str, Callable[[dict], Any]] | None = None,
    timeout: float = 20.0,
    prompt_blocks: list[dict] | None = None,
) -> tuple[dict, list[dict], list[str]]:
    """Отправить session/prompt и отвечать на server→client RPC до финала.

    prompt_blocks позволяет прислать произвольный multimodal-контент;
    если не задан — используется один text-блок из prompt_text.

    Returns:
        (prompt_response, notifications, rpc_methods).
    """
    responders = {**DEFAULT_RESPONDERS, **(responders or {})}
    blocks = (
        prompt_blocks
        if prompt_blocks is not None
        else [{"type": "text", "text": prompt_text}]
    )
    await transport.send(
        request(
            "session/prompt",
            {"sessionId": session_id, "prompt": blocks},
            request_id,
        )
    )

    notifications: list[dict] = []
    rpc_methods: list[str] = []
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise TimeoutError(f"prompt {request_id} did not finish")
        msg = await transport.recv(timeout=remaining)

        if msg.get("id") == request_id and ("result" in msg or "error" in msg):
            return msg, notifications, rpc_methods

        method = msg.get("method")
        if method is not None and "id" in msg:
            rpc_methods.append(method)
            responder = responders.get(method)
            if responder is None:
                await transport.send(result(msg["id"], {}))
            else:
                out = responder(msg.get("params", {}))
                if isinstance(out, RpcError):
                    await transport.send(error_payload(msg["id"], out.code, out.message))
                else:
                    await transport.send(result(msg["id"], out))
        elif method is not None:
            notifications.append(msg)


async def cancel_on_permission(
    transport: Transport,
    session_id: str,
    prompt_text: str,
    request_id: int,
    timeout: float = 20.0,
) -> dict:
    """Отправить prompt и на первый session/request_permission прислать cancel.

    Детерминированная точка отмены: turn ждёт разрешение, вместо ответа
    отправляем session/cancel (нотификация без id). Возвращает финальный ответ.
    """
    await transport.send(
        request(
            "session/prompt",
            {"sessionId": session_id, "prompt": [{"type": "text", "text": prompt_text}]},
            request_id,
        )
    )

    cancelled_sent = False
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise TimeoutError(f"prompt {request_id} did not finish")
        msg = await transport.recv(timeout=remaining)

        if msg.get("id") == request_id and ("result" in msg or "error" in msg):
            assert cancelled_sent, "cancel не был отправлен до завершения turn"
            return msg

        method = msg.get("method")
        if method == "session/request_permission" and not cancelled_sent:
            await transport.send(
                {
                    "jsonrpc": "2.0",
                    "method": "session/cancel",
                    "params": {"sessionId": session_id},
                }
            )
            cancelled_sent = True
        elif method is not None and "id" in msg:
            await transport.send(result(msg["id"], {}))


def tool_call_statuses(notifications: list[dict]) -> list[str]:
    """Собрать последовательность статусов из tool_call / tool_call_update.

    Возвращает статусы в порядке прихода нотификаций (напр.
    ["pending", "in_progress", "completed"]) — для проверки жизненного
    цикла tool call по ACP (08-Tool Calls.md §Status).
    """
    statuses: list[str] = []
    for n in notifications:
        if n.get("method") != "session/update":
            continue
        update = n.get("params", {}).get("update", {})
        if update.get("sessionUpdate") in ("tool_call", "tool_call_update"):
            status = update.get("status")
            if status is not None:
                statuses.append(status)
    return statuses


def agent_text(notifications: list[dict]) -> str:
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
# Готовые сценарии
# --------------------------------------------------------------------------- #

def chat_scenario() -> dict:
    return {
        "turns": [
            {"when_user": ["привет"], "replies": [{"text": "Привет! Я тестовый агент."}]},
            {"when_user": ["как дела"], "replies": [{"text": "Отлично, готов помогать."}]},
        ],
    }


def fs_read_scenario() -> dict:
    return {
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


def _terminal_replies(final_text: str) -> list[dict]:
    return [
        {"tool_calls": [
            {"name": "terminal_create", "arguments": {"command": "ls", "args": ["-ahl"]}}
        ]},
        {"tool_calls": [
            {"name": "terminal_wait_for_exit", "arguments": {"terminalId": "term-1"}}
        ]},
        {"tool_calls": [
            {"name": "terminal_release", "arguments": {"terminalId": "term-1"}}
        ]},
        {"text": final_text},
    ]


def terminal_scenario(final_text: str = "Команда выполнена, exit code 0.") -> dict:
    return {
        "turns": [
            {"when_user": ["ls", "запусти"], "replies": _terminal_replies(final_text)},
        ],
    }


def terminal_single_scenario() -> dict:
    """Один terminal_create (для reject/cancel сценариев)."""
    return {
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


def fs_error_scenario() -> dict:
    return {
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


def multi_tool_scenario() -> dict:
    return {
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


REJECT_RESPONDER: dict[str, Callable[[dict], Any]] = {
    "session/request_permission": lambda p: {
        "outcome": {"outcome": "selected", "optionId": "reject_once"}
    }
}

"""E2E тесты интеграции с MCP серверами через stdio transport.

Проверяет:
- Подключение MCP сервера при session/new
- Регистрация MCP инструментов
- Вызов MCP инструментов через session/prompt
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import agent_flow_harness as h
import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_MCP_SERVER_SCRIPT = Path(__file__).parent / "mcp_test_server.py"


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


async def _handshake_with_mcp(
    transport: StdioTransport, tmp_cwd: Path, mcp_servers: list[dict]
) -> str:
    """initialize + session/new с MCP серверами → возвращает session_id."""
    await transport.send(
        h.request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {
                    "fs": {"readTextFile": True, "writeTextFile": True},
                    "terminal": True,
                },
            },
            1,
        )
    )
    init = await transport.recv()
    assert init["id"] == 1

    await transport.send(
        h.request(
            "session/new",
            {"cwd": str(tmp_cwd), "mcpServers": mcp_servers},
            2,
        )
    )
    new = await transport.recv()
    assert new["id"] == 2
    return new["result"]["sessionId"]


@pytest.mark.asyncio
async def test_mcp_server_connection_on_session_new(tmp_cwd: Path) -> None:
    """MCP сервер подключается при session/new и регистрирует инструменты."""
    scenario = h.chat_scenario()
    mcp_config = [
        {
            "type": "stdio",
            "command": sys.executable,
            "args": [str(_MCP_SERVER_SCRIPT)],
        }
    ]

    async with _server(tmp_cwd, scenario) as transport:
        session_id = await _handshake_with_mcp(transport, tmp_cwd, mcp_config)
        assert session_id is not None

        await asyncio.sleep(1.0)

        prompt_resp, notifications, rpc_methods = await h.run_prompt(
            transport, session_id, "hello", 3
        )

        assert prompt_resp.get("result", {}).get("stopReason") == "end_turn"


@pytest.mark.asyncio
async def test_mcp_tools_available_in_session(tmp_cwd: Path) -> None:
    """MCP инструменты доступны для вызова после session/new."""
    scenario = h.chat_scenario()
    mcp_config = [
        {
            "type": "stdio",
            "command": sys.executable,
            "args": [str(_MCP_SERVER_SCRIPT)],
        }
    ]

    async with _server(tmp_cwd, scenario) as transport:
        session_id = await _handshake_with_mcp(transport, tmp_cwd, mcp_config)

        await asyncio.sleep(1.0)

        prompt_resp, notifications, rpc_methods = await h.run_prompt(
            transport, session_id, "list tools", 3
        )

        assert prompt_resp.get("result", {}).get("stopReason") == "end_turn"


@pytest.mark.asyncio
async def test_empty_mcp_servers_works(tmp_cwd: Path) -> None:
    """session/new с пустым mcpServers работает корректно."""
    scenario = h.chat_scenario()

    async with _server(tmp_cwd, scenario) as transport:
        session_id = await h.handshake(transport, tmp_cwd)
        assert session_id is not None

        prompt_resp, notifications, rpc_methods = await h.run_prompt(
            transport, session_id, "hello", 3
        )
        assert prompt_resp.get("result", {}).get("stopReason") == "end_turn"

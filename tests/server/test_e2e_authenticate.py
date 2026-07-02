"""E2E тесты аутентификации через stdio transport.

Проверяет:
- authMethods в initialize response
- authenticate метод с API key
- Создание сессии после аутентификации
- Отказ в создании сессии без аутентификации
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
                continue


async def _start_server_with_auth(
    tmp_cwd: Path, scenario_path: Path, api_key: str | None = None
) -> asyncio.subprocess.Process:
    env = h.server_env(tmp_cwd, scenario_path)
    cmd = [
        "uv", "run", "--directory", str(_PROJECT_ROOT),
        "codelab", "serve", "--stdio",
    ]
    if api_key:
        cmd.append("--require-auth")
        env["ACP_SERVER_API_KEY"] = api_key
    return await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(tmp_cwd),
        env=env,
    )


async def _stop_server(proc: asyncio.subprocess.Process) -> None:
    if proc.stdin is not None:
        proc.stdin.close()
    try:
        await asyncio.wait_for(proc.wait(), timeout=5.0)
    except TimeoutError:
        proc.terminate()
        await proc.wait()


class _server_with_auth:
    """Async context manager: поднять stdio-сервер с auth и отдать (transport)."""

    def __init__(self, tmp_cwd: Path, scenario: dict, api_key: str | None = None) -> None:
        self._tmp_cwd = tmp_cwd
        self._scenario = scenario
        self._api_key = api_key
        self._proc: asyncio.subprocess.Process | None = None

    async def __aenter__(self) -> StdioTransport:
        h.default_primary_agent(self._tmp_cwd)
        scenario_path = h.write_scenario(self._tmp_cwd, self._scenario)
        self._proc = await _start_server_with_auth(
            self._tmp_cwd, scenario_path, self._api_key
        )
        await asyncio.sleep(0.5)
        return StdioTransport(self._proc)

    async def __aexit__(self, *exc) -> None:
        if self._proc is not None:
            await _stop_server(self._proc)


@pytest.fixture
def tmp_cwd(tmp_path: Path) -> Path:
    return tmp_path


@pytest.mark.asyncio
async def test_initialize_returns_auth_methods_when_auth_enabled(tmp_cwd: Path) -> None:
    """initialize возвращает authMethods когда настроен auth backend."""
    scenario = h.chat_scenario()

    async with _server_with_auth(tmp_cwd, scenario, api_key="test-secret-key") as transport:
        await transport.send(
            h.request(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {},
                },
                1,
            )
        )
        init = await transport.recv()
        assert init["id"] == 1
        assert "result" in init

        result = init["result"]
        assert "authMethods" in result
        auth_methods = result["authMethods"]
        assert isinstance(auth_methods, list)
        assert len(auth_methods) >= 1

        auth_method = auth_methods[0]
        assert "id" in auth_method
        assert "name" in auth_method


@pytest.mark.asyncio
async def test_authenticate_with_valid_api_key(tmp_cwd: Path) -> None:
    """authenticate с валидным API key позволяет создать сессию."""
    scenario = h.chat_scenario()
    api_key = "test-secret-key-12345"

    async with _server_with_auth(tmp_cwd, scenario, api_key=api_key) as transport:
        await transport.send(
            h.request(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {},
                },
                1,
            )
        )
        init = await transport.recv()
        assert init["id"] == 1

        auth_method_id = init["result"]["authMethods"][0]["id"]

        await transport.send(
            h.request(
                "authenticate",
                {
                    "methodId": auth_method_id,
                    "apiKey": api_key,
                },
                2,
            )
        )
        auth_resp = await transport.recv()
        assert auth_resp["id"] == 2
        assert "result" in auth_resp

        await transport.send(
            h.request(
                "session/new",
                {"cwd": str(tmp_cwd), "mcpServers": []},
                3,
            )
        )
        new = await transport.recv()
        assert new["id"] == 3
        assert "result" in new
        assert "sessionId" in new["result"]


@pytest.mark.asyncio
async def test_session_new_requires_auth_when_enabled(tmp_cwd: Path) -> None:
    """session/new возвращает ошибку без предварительной аутентификации."""
    scenario = h.chat_scenario()

    async with _server_with_auth(tmp_cwd, scenario, api_key="secret") as transport:
        await transport.send(
            h.request(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {},
                },
                1,
            )
        )
        init = await transport.recv()
        assert init["id"] == 1

        await transport.send(
            h.request(
                "session/new",
                {"cwd": str(tmp_cwd), "mcpServers": []},
                2,
            )
        )
        new = await transport.recv()
        assert new["id"] == 2
        assert "error" in new
        assert new["error"]["code"] in (-32001, -32000, -32010)


@pytest.mark.asyncio
async def test_authenticate_with_invalid_api_key(tmp_cwd: Path) -> None:
    """authenticate с неверным API key возвращает ошибку."""
    scenario = h.chat_scenario()
    correct_key = "correct-key"
    wrong_key = "wrong-key"

    async with _server_with_auth(tmp_cwd, scenario, api_key=correct_key) as transport:
        await transport.send(
            h.request(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {},
                },
                1,
            )
        )
        init = await transport.recv()
        assert init["id"] == 1

        auth_method_id = init["result"]["authMethods"][0]["id"]

        await transport.send(
            h.request(
                "authenticate",
                {
                    "methodId": auth_method_id,
                    "apiKey": wrong_key,
                },
                2,
            )
        )
        auth_resp = await transport.recv()
        assert auth_resp["id"] == 2
        assert "error" in auth_resp


@pytest.mark.asyncio
async def test_no_auth_required_without_backend(tmp_cwd: Path) -> None:
    """Без auth backend сессия создаётся без аутентификации."""
    scenario = h.chat_scenario()

    async with _server_with_auth(tmp_cwd, scenario, api_key=None) as transport:
        await transport.send(
            h.request(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {},
                },
                1,
            )
        )
        init = await transport.recv()
        assert init["id"] == 1

        auth_methods = init["result"].get("authMethods", [])
        assert len(auth_methods) == 0

        await transport.send(
            h.request(
                "session/new",
                {"cwd": str(tmp_cwd), "mcpServers": []},
                2,
            )
        )
        new = await transport.recv()
        assert new["id"] == 2
        assert "result" in new
        assert "sessionId" in new["result"]

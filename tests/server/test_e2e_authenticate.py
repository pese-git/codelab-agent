"""E2E тесты аутентификации через stdio transport.

Проверяет:
- authMethods в initialize response
- authenticate метод с API key
- Создание сессии после аутентификации
- Отказ в создании сессии без аутентификации
"""

from __future__ import annotations

from pathlib import Path

import agent_flow_harness as h
import pytest


@pytest.fixture
def tmp_cwd(tmp_path: Path) -> Path:
    return tmp_path


def _auth_server(tmp_cwd: Path, api_key: str | None) -> h.StdioServer:
    """StdioServer с включённым auth backend (--require-auth), если задан ключ."""
    extra_args = ["--require-auth"] if api_key else []
    extra_env = {"ACP_SERVER_API_KEY": api_key} if api_key else {}
    return h.StdioServer(
        tmp_cwd,
        h.chat_scenario(),
        extra_args=extra_args,
        extra_env=extra_env,
    )


@pytest.mark.asyncio
async def test_initialize_returns_auth_methods_when_auth_enabled(tmp_cwd: Path) -> None:
    """initialize возвращает authMethods когда настроен auth backend."""
    async with _auth_server(tmp_cwd, api_key="test-secret-key") as transport:
        init = await h.initialize(transport, client_capabilities={})
        assert "result" in init

        auth_methods = init["result"]["authMethods"]
        assert isinstance(auth_methods, list)
        assert len(auth_methods) >= 1

        auth_method = auth_methods[0]
        assert "id" in auth_method
        assert "name" in auth_method


@pytest.mark.asyncio
async def test_authenticate_with_valid_api_key(tmp_cwd: Path) -> None:
    """authenticate с валидным API key позволяет создать сессию."""
    api_key = "test-secret-key-12345"

    async with _auth_server(tmp_cwd, api_key=api_key) as transport:
        init = await h.initialize(transport, client_capabilities={})
        auth_method_id = init["result"]["authMethods"][0]["id"]

        await transport.send(
            h.request("authenticate", {"methodId": auth_method_id, "apiKey": api_key}, 2)
        )
        auth_resp = await transport.recv()
        assert auth_resp["id"] == 2
        assert "result" in auth_resp

        session_id = await h.session_new(transport, tmp_cwd, request_id=3)
        assert session_id is not None


@pytest.mark.asyncio
async def test_session_new_requires_auth_when_enabled(tmp_cwd: Path) -> None:
    """session/new возвращает ошибку без предварительной аутентификации."""
    async with _auth_server(tmp_cwd, api_key="secret") as transport:
        await h.initialize(transport, client_capabilities={})

        await transport.send(
            h.request("session/new", {"cwd": str(tmp_cwd), "mcpServers": []}, 2)
        )
        new = await transport.recv()
        assert new["id"] == 2
        assert "error" in new
        assert new["error"]["code"] in (-32001, -32000, -32010)


@pytest.mark.asyncio
async def test_authenticate_with_invalid_api_key(tmp_cwd: Path) -> None:
    """authenticate с неверным API key возвращает ошибку."""
    async with _auth_server(tmp_cwd, api_key="correct-key") as transport:
        init = await h.initialize(transport, client_capabilities={})
        auth_method_id = init["result"]["authMethods"][0]["id"]

        await transport.send(
            h.request(
                "authenticate",
                {"methodId": auth_method_id, "apiKey": "wrong-key"},
                2,
            )
        )
        auth_resp = await transport.recv()
        assert auth_resp["id"] == 2
        assert "error" in auth_resp


@pytest.mark.asyncio
async def test_no_auth_required_without_backend(tmp_cwd: Path) -> None:
    """Без auth backend сессия создаётся без аутентификации."""
    async with _auth_server(tmp_cwd, api_key=None) as transport:
        init = await h.initialize(transport, client_capabilities={})

        auth_methods = init["result"].get("authMethods", [])
        assert len(auth_methods) == 0

        session_id = await h.session_new(transport, tmp_cwd)
        assert session_id is not None

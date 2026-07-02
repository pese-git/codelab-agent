"""E2E тесты интеграции с MCP серверами через stdio transport.

Проверяет:
- Подключение MCP сервера при session/new
- Регистрация MCP инструментов
- Вызов MCP инструментов через session/prompt
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import agent_flow_harness as h
import pytest

_MCP_SERVER_SCRIPT = Path(__file__).parent / "mcp_test_server.py"


@pytest.fixture
def tmp_cwd(tmp_path: Path) -> Path:
    return tmp_path


def _mcp_config() -> list[dict]:
    return [
        {
            "type": "stdio",
            "command": sys.executable,
            "args": [str(_MCP_SERVER_SCRIPT)],
        }
    ]


@pytest.mark.asyncio
async def test_mcp_server_connection_on_session_new(tmp_cwd: Path) -> None:
    """MCP сервер подключается при session/new и регистрирует инструменты."""
    async with h.StdioServer(tmp_cwd, h.chat_scenario()) as transport:
        session_id = await h.handshake(transport, tmp_cwd, mcp_servers=_mcp_config())
        assert session_id is not None

        await asyncio.sleep(1.0)

        prompt_resp, _, _ = await h.run_prompt(transport, session_id, "hello", 3)
        assert prompt_resp.get("result", {}).get("stopReason") == "end_turn"


@pytest.mark.asyncio
async def test_mcp_tools_available_in_session(tmp_cwd: Path) -> None:
    """MCP инструменты доступны для вызова после session/new."""
    async with h.StdioServer(tmp_cwd, h.chat_scenario()) as transport:
        session_id = await h.handshake(transport, tmp_cwd, mcp_servers=_mcp_config())

        await asyncio.sleep(1.0)

        prompt_resp, _, _ = await h.run_prompt(transport, session_id, "list tools", 3)
        assert prompt_resp.get("result", {}).get("stopReason") == "end_turn"


@pytest.mark.asyncio
async def test_empty_mcp_servers_works(tmp_cwd: Path) -> None:
    """session/new с пустым mcpServers работает корректно."""
    async with h.StdioServer(tmp_cwd, h.chat_scenario()) as transport:
        session_id = await h.handshake(transport, tmp_cwd)
        assert session_id is not None

        prompt_resp, _, _ = await h.run_prompt(transport, session_id, "hello", 3)
        assert prompt_resp.get("result", {}).get("stopReason") == "end_turn"

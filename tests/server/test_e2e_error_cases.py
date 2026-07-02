"""E2E тесты не-success веток через stdio transport.

Дополняют happy-path flow (test_stdio_agent_flow_e2e) ошибочными сценариями
на уровне полного JSON-RPC поверх subprocess-сервера:
- session/prompt в несуществующую сессию → Session not found (-32001);
- session/prompt без sessionId → Invalid params (-32602);
- session/prompt с неизвестным типом контента → блок молча отбрасывается
  (текущее поведение сервера, см. ЗАМЕЧАНИЕ ниже);
- session/new с битым MCP-сервером → graceful degradation (сессия работает).

ЗАМЕЧАНИЕ (несоответствие ACP): validate_prompt_content() возвращает -32602 на
неизвестный тип контента и покрыт юнит-тестами, но НЕ подключён к живому пути
(core._handle_session_prompt → orchestrator). acp_mapper._map_single молча
возвращает None для неизвестных блоков. По 06-Content/05-Prompt Turn сервер
должен отклонять неподдерживаемый контент — сейчас он его игнорирует.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import agent_flow_harness as h
import pytest

_server = h.StdioServer


@pytest.fixture
def tmp_cwd(tmp_path: Path) -> Path:
    return tmp_path


async def _send_and_await(
    transport: h.Transport,
    method: str,
    params: dict,
    request_id: int,
    timeout: float = 15.0,
) -> dict:
    """Отправить произвольный запрос и дождаться ответа с этим id.

    Промежуточные server→client RPC (если вдруг придут) закрываем пустым
    result, нотификации игнорируем.
    """
    await transport.send(h.request(method, params, request_id))
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise TimeoutError(f"no response for {method} id={request_id}")
        msg = await transport.recv(timeout=remaining)
        if msg.get("id") == request_id and ("result" in msg or "error" in msg):
            return msg
        if msg.get("method") is not None and "id" in msg:
            await transport.send(h.result(msg["id"], {}))


@pytest.mark.asyncio
async def test_prompt_unknown_session_returns_error(tmp_cwd: Path) -> None:
    """session/prompt в несуществующую сессию → error -32001."""
    async with _server(tmp_cwd, h.chat_scenario()) as t:
        await h.handshake(t, tmp_cwd)  # валидный handshake, но шлём чужой id

        resp = await _send_and_await(
            t,
            "session/prompt",
            {
                "sessionId": "sess_does_not_exist",
                "prompt": [{"type": "text", "text": "привет"}],
            },
            10,
        )
        assert "error" in resp
        assert resp["error"]["code"] == -32001
        assert "not found" in resp["error"]["message"].lower()


@pytest.mark.asyncio
async def test_prompt_missing_session_id_returns_error(tmp_cwd: Path) -> None:
    """session/prompt без sessionId → error -32602 (Invalid params)."""
    async with _server(tmp_cwd, h.chat_scenario()) as t:
        await h.handshake(t, tmp_cwd)

        resp = await _send_and_await(
            t,
            "session/prompt",
            {"prompt": [{"type": "text", "text": "привет"}]},
            10,
        )
        assert "error" in resp
        assert resp["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_prompt_unknown_content_type_is_silently_dropped(tmp_cwd: Path) -> None:
    """Неизвестный content-блок молча отбрасывается, текст обрабатывается.

    Документирует ТЕКУЩЕЕ поведение (не идеал по ACP — см. ЗАМЕЧАНИЕ в docstring
    модуля): сервер не отклоняет неподдерживаемый тип, а игнорирует его. Turn
    завершается за счёт соседнего text-блока.
    """
    async with _server(tmp_cwd, h.chat_scenario()) as t:
        session_id = await h.handshake(t, tmp_cwd)

        resp, notes, _ = await h.run_prompt(
            t,
            session_id,
            "",
            10,
            prompt_blocks=[
                {"type": "text", "text": "привет"},
                {"type": "video", "data": "xxx", "mimeType": "video/mp4"},
            ],
        )
        assert resp["result"]["stopReason"] == "end_turn"
        assert "тестовый агент" in h.agent_text(notes)


@pytest.mark.asyncio
async def test_mcp_bad_command_degrades_gracefully(tmp_cwd: Path) -> None:
    """session/new с несуществующим MCP-бинарём: сессия создаётся и работает.

    Сервер логирует ошибку и продолжает (graceful degradation, core.py),
    поэтому последующий prompt завершается нормально.
    """
    bad_mcp = [
        {
            "name": "broken",
            "type": "stdio",
            "command": "codelab-nonexistent-mcp-binary",
            "args": [],
        }
    ]
    async with _server(tmp_cwd, h.chat_scenario()) as t:
        await h.initialize(t)
        session_id = await h.session_new(t, tmp_cwd, mcp_servers=bad_mcp)
        assert session_id is not None

        resp, notes, _ = await h.run_prompt(t, session_id, "привет", 10)
        assert resp["result"]["stopReason"] == "end_turn"
        assert "тестовый агент" in h.agent_text(notes)

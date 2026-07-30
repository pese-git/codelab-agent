"""E2E: отмена во время активного клиентского RPC останавливает turn (P0-39).

Воспроизводит живую хронологию `sess_142dec045e89`: пока сервер ждёт ответа на
исходящий клиентский RPC, приходит `session/cancel`. До правки turn продолжался
после отмены — создавал новые tool call'ы и отправлял новые запросы разрешения,
хотя клиенту уже был отправлен `stop_reason: cancelled` (нарушение ACP
`05-Prompt Turn`).

Тест держит клиентский RPC неотвеченным — именно так отмена попадает в окно, в
котором дефект и жил.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import tests.server.agent_flow_harness as h

_server = h.StdioServer


@pytest.fixture
def tmp_cwd(tmp_path: Path) -> Path:
    return tmp_path


def _scenario() -> dict:
    """terminal_create → ещё два вызова, которые после отмены случиться не должны."""
    return {
        "turns": [
            {
                "when_user": ["запусти"],
                "replies": [
                    {
                        "tool_calls": [
                            {"name": "terminal_create", "arguments": {"command": "sleep 5"}}
                        ]
                    },
                    {"tool_calls": [{"name": "terminal_wait_for_exit", "arguments": {}}]},
                    {"tool_calls": [{"name": "fs_read_text_file", "arguments": {"path": "R.md"}}]},
                    {"text": "Не должно быть достигнуто."},
                ],
            },
        ],
    }


@pytest.mark.asyncio
async def test_cancel_during_client_rpc_stops_turn(tmp_cwd: Path) -> None:
    async with _server(tmp_cwd, _scenario()) as t:
        session_id = await h.handshake(t, tmp_cwd)
        await t.send(
            h.request(
                "session/prompt",
                {"sessionId": session_id, "prompt": [{"type": "text", "text": "запусти"}]},
                10,
            )
        )

        cancelled_at: int | None = None
        notifications: list[dict] = []
        rpcs: list[str] = []
        deadline = asyncio.get_event_loop().time() + 25
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError("turn не завершился после отмены")
            msg = await t.recv(timeout=remaining)

            if msg.get("id") == 10 and ("result" in msg or "error" in msg):
                final = msg
                break

            method = msg.get("method")
            if method == "session/update":
                notifications.append(msg)
                continue
            if method is None:
                continue
            rpcs.append(method)

            # Клиентский RPC в полёте: вместо ответа отправляем отмену
            if method == "terminal/create" and cancelled_at is None:
                await t.send(
                    {
                        "jsonrpc": "2.0",
                        "method": "session/cancel",
                        "params": {"sessionId": session_id},
                    }
                )
                cancelled_at = len(notifications)
                continue

            if "id" in msg:
                responder = h.DEFAULT_RESPONDERS.get(method)
                payload = responder(msg.get("params", {})) if responder else {}
                await t.send(h.result(msg["id"], payload))

        assert cancelled_at is not None, f"клиентский RPC не пришёл; rpcs={rpcs}"
        assert final["result"]["stopReason"] == "cancelled"

        new_calls = [
            n
            for n in notifications[cancelled_at:]
            if (n.get("params", {}).get("update", {}) or {}).get("sessionUpdate") == "tool_call"
        ]
        titles = [n["params"]["update"].get("title") for n in new_calls]
        assert new_calls == [], f"после отмены созданы новые tool call'ы: {titles}"

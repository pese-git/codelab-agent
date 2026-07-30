"""E2E: остаток батча возобновляется после разрешения (P2-40).

Живой прогон `sess_28f0a8011426`: модель шлёт батчи до 9 вызовов, пауза на первом
выбрасывала остальные — за один turn 80 брошенных вызовов и 81 служебный ответ
«вызов не выполнялся», из 109 запросов исполнились 28. Модель перезапрашивала одни
и те же файлы (`reset_counter_usecase.dart` — 9 раз), пользователь получал 25
запросов разрешения подряд.

Тест держит батч из трёх чтений: после разрешений должны исполниться все три, а
служебных ответов «не выполнялся» быть не должно.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import tests.server.agent_flow_harness as h

_server = h.StdioServer


@pytest.fixture
def tmp_cwd(tmp_path: Path) -> Path:
    return tmp_path


def _scenario() -> dict:
    return {
        "turns": [
            {
                "when_user": ["прочти"],
                "replies": [
                    {
                        "tool_calls": [
                            {"name": "fs_read_text_file", "arguments": {"path": "A.md"}},
                            {"name": "fs_read_text_file", "arguments": {"path": "B.md"}},
                            {"name": "fs_read_text_file", "arguments": {"path": "C.md"}},
                        ]
                    },
                    {"text": "Прочитал все три файла."},
                ],
            },
        ],
    }


@pytest.mark.asyncio
async def test_batch_tail_is_resumed_after_permission(tmp_cwd: Path) -> None:
    for name in ("A.md", "B.md", "C.md"):
        (tmp_cwd / name).write_text(f"# {name}\n", encoding="utf-8")

    async with _server(tmp_cwd, _scenario()) as t:
        session_id = await h.handshake(t, tmp_cwd)
        # standard: чтение вне разрешённого набора спрашивает разрешение
        resp, notes, _ = await h.run_prompt(t, session_id, "прочти файлы", 10)

        assert resp["result"]["stopReason"] == "end_turn"

        read_calls = [
            n["params"]["update"]
            for n in notes
            if n.get("method") == "session/update"
            and n["params"]["update"].get("sessionUpdate") == "tool_call"
        ]
        titles = [c.get("title") for c in read_calls]
        assert len(read_calls) == 3, f"исполнены не все вызовы батча: {titles}"

        statuses = [
            u["params"]["update"].get("status")
            for u in notes
            if u.get("method") == "session/update"
            and u["params"]["update"].get("sessionUpdate") == "tool_call_update"
        ]
        assert "completed" in statuses
        assert statuses.count("completed") == 3, f"завершены не все три: {statuses}"

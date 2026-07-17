"""Тесты чистой пересборки сообщений из replay-уведомлений (ReplayReducer)."""

from __future__ import annotations

from typing import Any

from codelab.client.application.replay_reducer import ReplayReducer


def _chunk(session_id: str, update_type: str, text: Any) -> dict[str, Any]:
    return {
        "params": {
            "sessionId": session_id,
            "update": {"sessionUpdate": update_type, "content": {"text": text}},
        }
    }


class TestReplayReducer:
    def test_empty_input_returns_empty(self) -> None:
        assert ReplayReducer().reduce("s", []) == []

    def test_aggregates_sequential_same_role_chunks(self) -> None:
        updates = [
            _chunk("s", "agent_message_chunk", "Hello"),
            _chunk("s", "agent_message_chunk", " World"),
        ]
        assert ReplayReducer().reduce("s", updates) == [
            {"role": "assistant", "content": "Hello World"}
        ]

    def test_separates_on_role_change(self) -> None:
        updates = [
            _chunk("s", "user_message_chunk", "Hi"),
            _chunk("s", "agent_message_chunk", "Hello"),
        ]
        assert ReplayReducer().reduce("s", updates) == [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]

    def test_skips_other_session(self) -> None:
        updates = [_chunk("other", "user_message_chunk", "hello")]
        assert ReplayReducer().reduce("target", updates) == []

    def test_skips_non_dict_content(self) -> None:
        updates = [
            {
                "params": {
                    "sessionId": "s",
                    "update": {"sessionUpdate": "user_message_chunk", "content": "x"},
                }
            }
        ]
        assert ReplayReducer().reduce("s", updates) == []

    def test_skips_empty_or_invalid_text(self) -> None:
        updates = [
            _chunk("s", "user_message_chunk", ""),
            _chunk("s", "user_message_chunk", None),
        ]
        assert ReplayReducer().reduce("s", updates) == []

    def test_ignores_non_message_updates(self) -> None:
        updates = [
            _chunk("s", "user_message_chunk", "keep"),
            _chunk("s", "tool_call", "drop"),
        ]
        assert ReplayReducer().reduce("s", updates) == [{"role": "user", "content": "keep"}]

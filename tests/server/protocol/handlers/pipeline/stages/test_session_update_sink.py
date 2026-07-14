"""Unit-тесты для SessionUpdateSink.

Проверяют контракт исходящего канала session/update:
- immediate delivery через callback с fallback в буфер;
- buffer_only без immediate delivery (permission / exception-ветка);
- порядок side-effects emit ПЕРЕД replay.save (детерминизм replay).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.messages import ACPMessage
from codelab.server.protocol.handlers.pipeline.stages.agent_loop.updates import (
    SessionUpdateSink,
)


def _notification(text: str = "hi") -> ACPMessage:
    return ACPMessage.notification(
        "session/update",
        {
            "sessionId": "s1",
            "update": {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": text},
            },
        },
    )


@pytest.mark.asyncio
async def test_emit_delivers_immediately_when_callback_set() -> None:
    delivered: list[ACPMessage] = []

    async def callback(msg: ACPMessage) -> None:
        delivered.append(msg)

    buffer: list[ACPMessage] = []
    sink = SessionUpdateSink(MagicMock(), callback, buffer)
    notification = _notification()

    await sink.emit(notification)

    assert delivered == [notification]
    assert buffer == []  # успешная доставка — в буфер не дублируется


@pytest.mark.asyncio
async def test_emit_falls_back_to_buffer_without_callback() -> None:
    buffer: list[ACPMessage] = []
    sink = SessionUpdateSink(MagicMock(), None, buffer)
    notification = _notification()

    await sink.emit(notification)

    assert buffer == [notification]


@pytest.mark.asyncio
async def test_emit_falls_back_to_buffer_when_callback_raises() -> None:
    async def callback(msg: ACPMessage) -> None:
        raise RuntimeError("transport down")

    buffer: list[ACPMessage] = []
    sink = SessionUpdateSink(MagicMock(), callback, buffer)
    notification = _notification()

    await sink.emit(notification)

    assert buffer == [notification]


def test_buffer_only_never_delivers_immediately() -> None:
    callback = AsyncMock()
    buffer: list[ACPMessage] = []
    sink = SessionUpdateSink(MagicMock(), callback, buffer)
    notification = _notification()

    sink.buffer_only(notification)

    assert buffer == [notification]
    callback.assert_not_called()


@pytest.mark.asyncio
async def test_emit_and_save_tool_update_order_emit_before_replay() -> None:
    calls: list[str] = []

    async def callback(_msg: ACPMessage) -> None:
        calls.append("emit")

    replay = MagicMock()
    replay.save_tool_call_update.side_effect = lambda **_: calls.append("replay")
    sink = SessionUpdateSink(replay, callback, [])

    await sink.emit_and_save_tool_update(
        _notification(),
        session=MagicMock(),
        tool_call_id="call_1",
        status="completed",
        content=None,
    )

    assert calls == ["emit", "replay"]
    replay.save_tool_call_update.assert_called_once()


@pytest.mark.asyncio
async def test_streaming_delta_never_buffers() -> None:
    async def callback(msg: ACPMessage) -> None:
        raise RuntimeError("dropped")

    buffer: list[ACPMessage] = []
    sink = SessionUpdateSink(MagicMock(), callback, buffer)

    await sink.emit_streaming_delta("s1", "chunk")

    # Дельта, не доставленная callback'ом, НЕ накапливается в буфере.
    assert buffer == []


def test_buffer_and_save_tool_update_buffers_and_records() -> None:
    replay = MagicMock()
    buffer: list[ACPMessage] = []
    sink = SessionUpdateSink(replay, AsyncMock(), buffer)
    notification = _notification()

    sink.buffer_and_save_tool_update(
        notification,
        session=MagicMock(),
        tool_call_id="call_1",
        status="failed",
    )

    assert buffer == [notification]
    replay.save_tool_call_update.assert_called_once()

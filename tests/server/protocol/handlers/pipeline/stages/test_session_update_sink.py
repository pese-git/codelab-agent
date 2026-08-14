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
from tests.server._domain_sessions import make_commands, make_domain_session


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
    sink = SessionUpdateSink(MagicMock(), callback, buffer, make_commands(make_domain_session()))
    notification = _notification()

    await sink.emit(notification)

    assert delivered == [notification]
    assert buffer == []  # успешная доставка — в буфер не дублируется


@pytest.mark.asyncio
async def test_emit_falls_back_to_buffer_without_callback() -> None:
    buffer: list[ACPMessage] = []
    sink = SessionUpdateSink(MagicMock(), None, buffer, make_commands(make_domain_session()))
    notification = _notification()

    await sink.emit(notification)

    assert buffer == [notification]


@pytest.mark.asyncio
async def test_emit_falls_back_to_buffer_when_callback_raises() -> None:
    async def callback(msg: ACPMessage) -> None:
        raise RuntimeError("transport down")

    buffer: list[ACPMessage] = []
    sink = SessionUpdateSink(MagicMock(), callback, buffer, make_commands(make_domain_session()))
    notification = _notification()

    await sink.emit(notification)

    assert buffer == [notification]


def test_buffer_only_never_delivers_immediately() -> None:
    callback = AsyncMock()
    buffer: list[ACPMessage] = []
    sink = SessionUpdateSink(MagicMock(), callback, buffer, make_commands(make_domain_session()))
    notification = _notification()

    sink.buffer_only(notification)

    assert buffer == [notification]
    callback.assert_not_called()


@pytest.mark.asyncio
async def test_emit_tool_update_does_not_write_journal() -> None:
    """Sink только отправляет: событие статуса пишет дверь перехода (шаг 4g ADR-008).

    Пока запись жила здесь, между сменой статуса и событием успевала пройти
    перезагрузка агрегата, и статус терялся. Хуже того, дыра была невидима:
    тест, подменивший писателя моком, продолжал проходить.
    """
    delivered: list[str] = []

    async def callback(_msg: ACPMessage) -> None:
        delivered.append("emit")

    replay = MagicMock()
    sink = SessionUpdateSink(replay, callback, [], make_commands(make_domain_session()))

    await sink.emit_tool_update(_notification())

    assert delivered == ["emit"]
    replay.save_tool_call_update.assert_not_called()


@pytest.mark.asyncio
async def test_streaming_delta_never_buffers() -> None:
    async def callback(msg: ACPMessage) -> None:
        raise RuntimeError("dropped")

    buffer: list[ACPMessage] = []
    sink = SessionUpdateSink(MagicMock(), callback, buffer, make_commands(make_domain_session()))

    await sink.emit_streaming_delta("s1", "chunk")

    # Дельта, не доставленная callback'ом, НЕ накапливается в буфере.
    assert buffer == []

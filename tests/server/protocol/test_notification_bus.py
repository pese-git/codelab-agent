"""Тесты SessionNotificationBus — публикация, подписка, буфер, очистка.

Особое внимание — clear_buffer() (риск двойной доставки при реконнекте):
на session/load транспорт чистит буфер до подписки, чтобы устаревшие
буферизованные сообщения не доставились повторно поверх реплея истории.
"""

from __future__ import annotations

import pytest

from codelab.server.protocol.notification_bus import SessionNotificationBus


def _collector(sink: list):
    """Async-подписчик, складывающий сообщения в sink."""
    async def _cb(message) -> None:
        sink.append(message)

    return _cb


@pytest.mark.asyncio
async def test_publish_delivers_to_subscriber() -> None:
    """С подписчиком publish доставляет сразу, буфер пуст."""
    bus = SessionNotificationBus()
    received: list = []
    bus.subscribe(_collector(received))

    await bus.publish({"n": 1})

    assert received == [{"n": 1}]
    assert bus.buffered_count == 0


@pytest.mark.asyncio
async def test_publish_buffers_without_subscriber() -> None:
    """Без подписчика publish буферизует сообщение."""
    bus = SessionNotificationBus()

    await bus.publish({"n": 1})
    await bus.publish({"n": 2})

    assert bus.buffered_count == 2
    assert not bus.has_subscribers


@pytest.mark.asyncio
async def test_clear_buffer_drops_buffered_keeps_subscribers() -> None:
    """clear_buffer() чистит буфер, но не трогает подписчиков."""
    bus = SessionNotificationBus()
    received: list = []
    bus.subscribe(_collector(received))

    # Второй bus имитирует состояние без подписчика (дисконнект)
    disconnected = SessionNotificationBus()
    await disconnected.publish({"stale": 1})
    await disconnected.publish({"stale": 2})
    assert disconnected.buffered_count == 2

    disconnected.clear_buffer()

    assert disconnected.buffered_count == 0
    # У первого bus подписчик на месте
    assert bus.has_subscribers


@pytest.mark.asyncio
async def test_reconnect_clear_buffer_prevents_double_delivery() -> None:
    """Реконнект: буфер, накопленный в дисконнекте, после clear_buffer не
    доставляется новому подписчику повторно (нет двойной доставки)."""
    bus = SessionNotificationBus()

    # Клиент отключён — сообщения буферизуются
    await bus.publish({"chunk": "a"})
    await bus.publish({"chunk": "b"})
    assert bus.buffered_count == 2

    # session/load: транспорт чистит буфер ДО подписки (реплей авторитетен)
    bus.clear_buffer()

    # Реконнект: новый подписчик не получает устаревший буфер
    received: list = []
    bus.subscribe(_collector(received))

    assert received == []
    assert bus.buffered_count == 0

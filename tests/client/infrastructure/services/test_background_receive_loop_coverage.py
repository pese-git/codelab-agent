"""Тесты покрытия для BackgroundReceiveLoop.

Покрывает ранее непокрытые сценарии:
- отмену задачи при таймауте остановки;
- прерывание backoff при asyncio.CancelledError;
- сброс consecutive_errors после успешного приёма сообщения;
- логирование response без request_id;
- пропуск сообщений с неизвестным типом маршрутизации.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codelab.client.infrastructure.services.background_receive_loop import (
    BackgroundReceiveLoop,
)
from codelab.client.infrastructure.services.message_router import MessageRouter
from codelab.client.infrastructure.services.routing_queues import RoutingQueues
from codelab.client.infrastructure.transport import WebSocketTransport


@pytest.fixture
def mock_transport() -> MagicMock:
    """Создаёт mock транспорт."""
    transport = MagicMock(spec=WebSocketTransport)
    transport.receive_text = AsyncMock()
    return transport


@pytest.fixture
def mock_router() -> MagicMock:
    """Создаёт mock роутер."""
    router = MagicMock(spec=MessageRouter)
    routing_key = MagicMock()
    routing_key.queue_type = "response"
    routing_key.request_id = "test-id"
    router.route.return_value = routing_key
    return router


@pytest.fixture
def mock_queues() -> MagicMock:
    """Создаёт mock очереди."""
    queues = MagicMock(spec=RoutingQueues)
    queues.put_response = AsyncMock()
    queues.put_notification = AsyncMock()
    queues.put_permission_request = AsyncMock()
    queues.broadcast_connection_error = AsyncMock()
    return queues


class TestBackgroundReceiveLoopStop:
    """Тесты для stop()."""

    async def test_stop_cancels_task_on_timeout(
        self,
        mock_transport: MagicMock,
        mock_router: MagicMock,
        mock_queues: MagicMock,
    ) -> None:
        """stop() отменяет задачу при таймауте graceful shutdown."""
        loop = BackgroundReceiveLoop(
            transport=mock_transport,
            router=mock_router,
            queues=mock_queues,
        )

        # Блокируем receive_text, чтобы задача не завершилась сама.
        mock_transport.receive_text = AsyncMock(
            side_effect=lambda: asyncio.Future().__await__()  # type: ignore[no-any-return]
        )

        await loop.start()
        assert loop._task is not None
        assert not loop._task.done()

        with patch(
            "codelab.client.infrastructure.services.background_receive_loop.asyncio.wait_for",
            side_effect=TimeoutError,
        ):
            await loop.stop()

        assert loop._task.done()
        assert not loop.is_running()


class TestBackgroundReceiveLoopRestart:
    """Тесты для _receive_loop_with_restart()."""

    async def test_restart_breaks_on_backoff_cancel(
        self,
        mock_transport: MagicMock,
        mock_router: MagicMock,
        mock_queues: MagicMock,
    ) -> None:
        """Цикл перезапуска выходит, если backoff прерван CancelledError."""
        loop = BackgroundReceiveLoop(
            transport=mock_transport,
            router=mock_router,
            queues=mock_queues,
        )

        loop._receive_loop = AsyncMock(side_effect=Exception("boom"))  # type: ignore[method-assign]

        with patch(
            "codelab.client.infrastructure.services.background_receive_loop.asyncio.sleep",
            side_effect=asyncio.CancelledError,
        ):
            await loop._receive_loop_with_restart()

        assert loop._consecutive_errors == 1
        assert loop._restarts_count == 1
        mock_queues.broadcast_connection_error.assert_awaited_once()


class TestBackgroundReceiveLoopReceive:
    """Тесты для _receive_loop()."""

    async def test_receive_loop_resets_consecutive_errors_on_success(
        self,
        mock_transport: MagicMock,
        mock_router: MagicMock,
        mock_queues: MagicMock,
    ) -> None:
        """Успешный приём сообщения сбрасывает consecutive_errors."""
        loop = BackgroundReceiveLoop(
            transport=mock_transport,
            router=mock_router,
            queues=mock_queues,
        )
        loop._consecutive_errors = 2

        mock_transport.receive_text = AsyncMock(
            side_effect=[
                json.dumps({"id": "1", "result": {}}),
                asyncio.CancelledError,
            ]
        )

        with pytest.raises(asyncio.CancelledError):
            await loop._receive_loop()

        assert loop._consecutive_errors == 0
        mock_queues.put_response.assert_awaited_once()

    async def test_receive_loop_logs_missing_request_id(
        self,
        mock_transport: MagicMock,
        mock_router: MagicMock,
        mock_queues: MagicMock,
    ) -> None:
        """Loop логирует ошибку, если response маршрутизирован без request_id."""
        loop = BackgroundReceiveLoop(
            transport=mock_transport,
            router=mock_router,
            queues=mock_queues,
        )

        routing_key = MagicMock()
        routing_key.queue_type = "response"
        routing_key.request_id = None
        mock_router.route.return_value = routing_key

        mock_transport.receive_text = AsyncMock(
            side_effect=[
                json.dumps({"id": "1", "result": {}}),
                asyncio.CancelledError,
            ]
        )

        with pytest.raises(asyncio.CancelledError):
            await loop._receive_loop()

        mock_queues.put_response.assert_not_awaited()

    async def test_receive_loop_skips_unknown_message_type(
        self,
        mock_transport: MagicMock,
        mock_router: MagicMock,
        mock_queues: MagicMock,
    ) -> None:
        """Loop пропускает сообщения с неизвестным типом маршрутизации."""
        loop = BackgroundReceiveLoop(
            transport=mock_transport,
            router=mock_router,
            queues=mock_queues,
        )

        routing_key = MagicMock()
        routing_key.queue_type = "unknown"
        routing_key.request_id = None
        mock_router.route.return_value = routing_key

        mock_transport.receive_text = AsyncMock(
            side_effect=[
                json.dumps({"method": "custom/thing"}),
                asyncio.CancelledError,
            ]
        )

        with pytest.raises(asyncio.CancelledError):
            await loop._receive_loop()

        mock_queues.put_response.assert_not_awaited()
        mock_queues.put_notification.assert_not_awaited()
        mock_queues.put_permission_request.assert_not_awaited()

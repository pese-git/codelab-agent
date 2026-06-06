"""Тесты для BackgroundReceiveLoop - фоновой задачи приёма сообщений."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from codelab.client.infrastructure.services.background_receive_loop import (
    BackgroundReceiveLoop,
)
from codelab.client.infrastructure.services.message_router import MessageRouter
from codelab.client.infrastructure.services.routing_queues import RoutingQueues
from codelab.client.infrastructure.transport import WebSocketTransport


class TestBackgroundReceiveLoop:
    """Тесты для BackgroundReceiveLoop."""

    @pytest.mark.asyncio
    async def test_loop_starts_and_stops(self) -> None:
        """Фоновый loop запускается и останавливается."""
        # Создаем mock транспорт
        transport = AsyncMock(spec=WebSocketTransport)
        # Имитируем бесконечное получение сообщений (будет остановлено флагом)
        transport.receive_text = AsyncMock(side_effect=asyncio.CancelledError())

        router = MessageRouter()
        queues = RoutingQueues()
        loop = BackgroundReceiveLoop(transport, router, queues)

        # Loop не запущена
        assert not loop.is_running()

        # Запускаем loop
        await loop.start()
        assert loop.is_running()

        # Даем время на запуск
        await asyncio.sleep(0.1)

        # Останавливаем loop
        await loop.stop()
        assert not loop.is_running()

    @pytest.mark.asyncio
    async def test_messages_dispatched_to_response_queue(self) -> None:
        """Сообщения с id распределяются в response queues."""
        # Создаем mock транспорт
        transport = AsyncMock(spec=WebSocketTransport)

        # Имитируем получение одного сообщения, потом ошибку для выхода
        response_message = {"id": 123, "result": {"status": "ok"}}
        transport.receive_text = AsyncMock(
            side_effect=[json.dumps(response_message), asyncio.CancelledError()]
        )

        router = MessageRouter()
        queues = RoutingQueues()
        loop = BackgroundReceiveLoop(transport, router, queues)

        # Создаем очередь для request_id (как это делает request_with_callbacks)
        queue = await queues.get_or_create_response_queue(123)

        # Запускаем loop
        await loop.start()

        # Ждем, что сообщение попадет в очередь
        received = await asyncio.wait_for(queue.get(), timeout=2.0)

        assert received == response_message

        # Останавливаем loop
        await loop.stop()

    @pytest.mark.asyncio
    async def test_messages_dispatched_to_notification_queue(self) -> None:
        """Сообщения session/update распределяются в notification queue."""
        # Создаем mock транспорт
        transport = AsyncMock(spec=WebSocketTransport)

        notification = {
            "method": "session/update",
            "params": {"sessionId": "sess-1"},
        }
        transport.receive_text = AsyncMock(
            side_effect=[json.dumps(notification), asyncio.CancelledError()]
        )

        router = MessageRouter()
        queues = RoutingQueues()
        loop = BackgroundReceiveLoop(transport, router, queues)

        # Запускаем loop
        await loop.start()

        # Ждем сообщения в очереди уведомлений
        received = await asyncio.wait_for(queues.notification_queue.get(), timeout=2.0)

        assert received == notification

        # Останавливаем loop
        await loop.stop()

    @pytest.mark.asyncio
    async def test_messages_dispatched_to_permission_queue(self) -> None:
        """Сообщения session/request_permission распределяются в permission queue."""
        # Создаем mock транспорт
        transport = AsyncMock(spec=WebSocketTransport)

        permission = {
            "method": "session/request_permission",
            "params": {"permission": "read"},
        }
        transport.receive_text = AsyncMock(
            side_effect=[json.dumps(permission), asyncio.CancelledError()]
        )

        router = MessageRouter()
        queues = RoutingQueues()
        loop = BackgroundReceiveLoop(transport, router, queues)

        # Запускаем loop
        await loop.start()

        # Ждем сообщения в очереди разрешений
        received = await asyncio.wait_for(queues.permission_queue.get(), timeout=2.0)

        assert received == permission

        # Останавливаем loop
        await loop.stop()

    @pytest.mark.asyncio
    async def test_permission_request_with_id_dispatched_to_permission_queue(self) -> None:
        """session/request_permission c id попадает в permission queue."""
        transport = AsyncMock(spec=WebSocketTransport)

        permission = {
            "id": "perm-1",
            "method": "session/request_permission",
            "params": {"sessionId": "sess-1"},
        }
        transport.receive_text = AsyncMock(
            side_effect=[json.dumps(permission), asyncio.CancelledError()]
        )

        router = MessageRouter()
        queues = RoutingQueues()
        loop = BackgroundReceiveLoop(transport, router, queues)

        await loop.start()

        received = await asyncio.wait_for(queues.permission_queue.get(), timeout=2.0)

        assert received == permission

        await loop.stop()

    @pytest.mark.asyncio
    async def test_fs_request_with_id_dispatched_to_notification_queue(self) -> None:
        """fs/* request c id попадает в notification queue."""
        transport = AsyncMock(spec=WebSocketTransport)

        fs_request = {
            "id": "rpc-1",
            "method": "fs/read_text_file",
            "params": {"path": "/tmp/test.txt"},
        }
        transport.receive_text = AsyncMock(
            side_effect=[json.dumps(fs_request), asyncio.CancelledError()]
        )

        router = MessageRouter()
        queues = RoutingQueues()
        loop = BackgroundReceiveLoop(transport, router, queues)

        await loop.start()

        received = await asyncio.wait_for(queues.notification_queue.get(), timeout=2.0)

        assert received == fs_request

        await loop.stop()

    @pytest.mark.asyncio
    async def test_loop_handles_connection_error(self) -> None:
        """Loop обрабатывает ConnectionError и пытается перезапуститься."""
        # Создаем mock транспорт
        transport = AsyncMock(spec=WebSocketTransport)

        error = ConnectionError("Connection lost")
        transport.receive_text = AsyncMock(side_effect=error)

        router = MessageRouter()
        queues = RoutingQueues()
        loop = BackgroundReceiveLoop(transport, router, queues)

        # Уменьшаем backoff для быстрого теста
        loop.INITIAL_BACKOFF_SECONDS = 0.01
        loop.MAX_BACKOFF_SECONDS = 0.02
        loop.MAX_CONSECUTIVE_RETRIES = 2

        # Создаем pending запрос
        queue = await queues.get_or_create_response_queue(999)

        # Запускаем loop
        await loop.start()

        # Ждем ошибку в очереди (broadcast_connection_error)
        error_msg = await asyncio.wait_for(queue.get(), timeout=2.0)

        # Проверяем, что это error сообщение
        assert "error" in error_msg
        assert error_msg["id"] == 999

        # Loop должна попытаться перезапуститься, но после MAX_RETRIES остановиться
        await asyncio.sleep(0.3)
        
        # Проверяем, что были попытки рестарта
        stats = loop.get_stats()
        assert stats["restarts_count"] >= 1
        assert stats["consecutive_errors"] >= loop.MAX_CONSECUTIVE_RETRIES
        
        # После превышения лимита loop должна остановиться
        assert not loop.is_running()

    @pytest.mark.asyncio
    async def test_loop_handles_generic_error(self) -> None:
        """Loop обрабатывает общие ошибки и пытается перезапуститься."""
        # Создаем mock транспорт
        transport = AsyncMock(spec=WebSocketTransport)

        error = RuntimeError("Some error")
        transport.receive_text = AsyncMock(side_effect=error)

        router = MessageRouter()
        queues = RoutingQueues()
        loop = BackgroundReceiveLoop(transport, router, queues)

        # Уменьшаем backoff и лимит для быстрого теста
        loop.INITIAL_BACKOFF_SECONDS = 0.01
        loop.MAX_BACKOFF_SECONDS = 0.02
        loop.MAX_CONSECUTIVE_RETRIES = 2

        # Запускаем loop
        await loop.start()

        # Даем время на обработку ошибки и попытки рестарта
        await asyncio.sleep(0.3)

        # Loop должна попытаться перезапуститься, но после MAX_RETRIES остановиться
        stats = loop.get_stats()
        assert stats["restarts_count"] >= 1
        assert stats["consecutive_errors"] >= loop.MAX_CONSECUTIVE_RETRIES
        
        # После превышения лимита loop должна остановиться
        assert not loop.is_running()

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self) -> None:
        """Graceful shutdown с timeout."""
        # Создаем mock транспорт который долго обрабатывает
        transport = AsyncMock(spec=WebSocketTransport)

        async def slow_receive_text():
            await asyncio.sleep(10)  # Очень долго
            return json.dumps({"id": 1, "result": "ok"})

        transport.receive_text = slow_receive_text

        router = MessageRouter()
        queues = RoutingQueues()
        loop = BackgroundReceiveLoop(transport, router, queues)

        # Запускаем loop
        await loop.start()
        await asyncio.sleep(0.1)

        # Останавливаем с timeout (таск будет отменена)
        await loop.stop()

        # Проверяем что loop остановлена
        assert not loop.is_running()

    @pytest.mark.asyncio
    async def test_get_stats(self) -> None:
        """Получение статистики loop'а."""
        # Создаем mock транспорт
        transport = AsyncMock(spec=WebSocketTransport)

        msg1 = {"id": 1, "result": "ok"}
        msg2 = {"id": 2, "result": "ok"}
        transport.receive_text = AsyncMock(
            side_effect=[json.dumps(msg1), json.dumps(msg2), asyncio.CancelledError()]
        )

        router = MessageRouter()
        queues = RoutingQueues()
        loop = BackgroundReceiveLoop(transport, router, queues)

        # Создаем очереди для сообщений
        await queues.get_or_create_response_queue(1)
        await queues.get_or_create_response_queue(2)

        # Запускаем loop
        await loop.start()

        # Получаем сообщения (чтобы они были обработаны)
        queue1 = await queues.get_or_create_response_queue(1)
        queue2 = await queues.get_or_create_response_queue(2)
        await asyncio.wait_for(queue1.get(), timeout=2.0)
        await asyncio.wait_for(queue2.get(), timeout=2.0)

        # Останавливаем
        await loop.stop()

        # Получаем статистику
        stats = loop.get_stats()

        assert stats["running"] is False
        assert stats["messages_received"] == 2
        assert stats["messages_routed"] == 2
        assert stats["errors_count"] == 0

    @pytest.mark.asyncio
    async def test_start_multiple_times(self) -> None:
        """Запуск loop несколько раз - вторая попытка игнорируется."""
        # Создаем mock транспорт
        transport = AsyncMock(spec=WebSocketTransport)

        # Даем транспорту долго обрабатывать чтобы таска не завершилась
        async def slow_receive_text():
            await asyncio.sleep(10)
            return json.dumps({"id": 1, "result": "ok"})

        transport.receive_text = slow_receive_text

        router = MessageRouter()
        queues = RoutingQueues()
        loop = BackgroundReceiveLoop(transport, router, queues)

        # Первый запуск
        await loop.start()
        task1 = loop._task
        assert task1 is not None
        assert not task1.done()

        await asyncio.sleep(0.1)

        # Второй запуск (должен быть проигнорирован)
        await loop.start()
        task2 = loop._task

        # Таск не должна измениться
        assert task1 is task2

        await loop.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self) -> None:
        """stop() безопасно вызывается когда loop не запущена."""
        # Создаем mock транспорт
        transport = AsyncMock(spec=WebSocketTransport)

        router = MessageRouter()
        queues = RoutingQueues()
        loop = BackgroundReceiveLoop(transport, router, queues)

        # Вызываем stop без запуска - не должно быть ошибки
        await loop.stop()

        # Вызываем еще раз
        await loop.stop()

        assert not loop.is_running()

"""Тесты для RoutingQueues - управления очередями маршрутизации."""

import asyncio

import pytest

from codelab.client.infrastructure.services.routing_queues import RoutingQueues


class TestRoutingQueues:
    """Тесты для RoutingQueues."""

    @pytest.mark.asyncio
    async def test_get_or_create_response_queue(self) -> None:
        """Получение или создание очереди для request_id."""
        queues = RoutingQueues()

        # Первый раз создаем новую очередь
        queue1 = await queues.get_or_create_response_queue(123)
        assert queue1 is not None

        # Второй раз получаем существующую
        queue2 = await queues.get_or_create_response_queue(123)
        assert queue1 is queue2

    @pytest.mark.asyncio
    async def test_put_and_get_response(self) -> None:
        """Добавление и получение RPC ответа."""
        queues = RoutingQueues()
        message = {"id": 123, "result": {"status": "ok"}}

        # Создаем очередь для этого request_id
        queue = await queues.get_or_create_response_queue(123)

        # Кладем ответ
        await queues.put_response(123, message)

        # Получаем ответ из очереди
        received = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert received == message

    @pytest.mark.asyncio
    async def test_put_and_get_notification(self) -> None:
        """Добавление и получение уведомления."""
        queues = RoutingQueues()
        notification = {
            "method": "session/update",
            "params": {"sessionId": "sess-1"},
        }

        # Кладем уведомление
        await queues.put_notification(notification)

        # Получаем из очереди уведомлений
        received = await asyncio.wait_for(
            queues.notification_queue.get(), timeout=1.0
        )
        assert received == notification

    @pytest.mark.asyncio
    async def test_put_and_get_permission_request(self) -> None:
        """Добавление и получение запроса разрешения."""
        queues = RoutingQueues()
        permission_req = {
            "method": "session/request_permission",
            "params": {"permission": "read"},
        }

        # Кладем запрос разрешения
        await queues.put_permission_request(permission_req)

        # Получаем из очереди разрешений
        received = await asyncio.wait_for(
            queues.permission_queue.get(), timeout=1.0
        )
        assert received == permission_req

    @pytest.mark.asyncio
    async def test_multiple_concurrent_requests(self) -> None:
        """Несколько конкурентных запросов используют разные очереди."""
        queues = RoutingQueues()

        # Создаем несколько очередей для разных request_id
        queue1 = await queues.get_or_create_response_queue(1)
        queue2 = await queues.get_or_create_response_queue(2)
        queue3 = await queues.get_or_create_response_queue(3)

        # Кладем сообщения
        msg1 = {"id": 1, "result": "response1"}
        msg2 = {"id": 2, "result": "response2"}
        msg3 = {"id": 3, "result": "response3"}

        await queues.put_response(1, msg1)
        await queues.put_response(2, msg2)
        await queues.put_response(3, msg3)

        # Каждая очередь должна содержать свое сообщение
        received1 = await asyncio.wait_for(queue1.get(), timeout=1.0)
        received2 = await asyncio.wait_for(queue2.get(), timeout=1.0)
        received3 = await asyncio.wait_for(queue3.get(), timeout=1.0)

        assert received1 == msg1
        assert received2 == msg2
        assert received3 == msg3

    @pytest.mark.asyncio
    async def test_cleanup_response_queue(self) -> None:
        """Очистка очереди ответов после использования."""
        queues = RoutingQueues()

        # Создаем и используем очередь
        await queues.get_or_create_response_queue(123)
        assert await queues.response_queue_exists(123)

        # Очищаем очередь
        await queues.cleanup_response_queue(123)
        assert not await queues.response_queue_exists(123)

    @pytest.mark.asyncio
    async def test_get_pending_requests_count(self) -> None:
        """Подсчет количества pending запросов."""
        queues = RoutingQueues()

        assert queues.get_pending_requests_count() == 0

        # Создаем несколько очередей
        await queues.get_or_create_response_queue(1)
        await queues.get_or_create_response_queue(2)
        await queues.get_or_create_response_queue(3)

        assert queues.get_pending_requests_count() == 3

        # Очищаем одну
        await queues.cleanup_response_queue(1)
        assert queues.get_pending_requests_count() == 2

    @pytest.mark.asyncio
    async def test_put_response_creates_queue_if_missing(self) -> None:
        """put_response создает очередь если её нет (сервер ответил раньше)."""
        queues = RoutingQueues()
        message = {"id": 999, "result": {"status": "ok"}}

        # Кладем ответ БЕЗ предварительного создания очереди
        await queues.put_response(999, message)

        # Очередь должна быть создана
        assert await queues.response_queue_exists(999)

        # И сообщение должно быть в очереди
        queue = await queues.get_or_create_response_queue(999)
        received = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert received == message

    @pytest.mark.asyncio
    async def test_broadcast_connection_error(self) -> None:
        """Broadcast ошибки соединения всем pending очередям."""
        queues = RoutingQueues()

        # Создаем несколько pending запросов
        queue1 = await queues.get_or_create_response_queue(1)
        queue2 = await queues.get_or_create_response_queue(2)

        # Отправляем ошибку
        error = ConnectionError("Connection lost")
        await queues.broadcast_connection_error(error)

        # Каждая очередь должна содержать error сообщение
        error_msg1 = await asyncio.wait_for(queue1.get(), timeout=1.0)
        error_msg2 = await asyncio.wait_for(queue2.get(), timeout=1.0)

        assert "error" in error_msg1
        assert error_msg1["id"] == 1
        assert "error" in error_msg2
        assert error_msg2["id"] == 2

    @pytest.mark.asyncio
    async def test_clear_all_queues(self) -> None:
        """Очистка всех очередей."""
        queues = RoutingQueues()

        # Заполняем все очереди
        await queues.get_or_create_response_queue(1)
        await queues.get_or_create_response_queue(2)
        await queues.put_notification({"method": "session/update"})
        await queues.put_permission_request({"method": "session/request_permission"})

        # Очищаем все
        await queues.clear_all()

        # Все должно быть пусто
        assert queues.get_pending_requests_count() == 0
        assert queues.notification_queue.empty()
        assert queues.permission_queue.empty()

    @pytest.mark.asyncio
    async def test_notification_queue_property(self) -> None:
        """Получение очереди уведомлений через property."""
        queues = RoutingQueues()
        notification_queue = queues.notification_queue

        assert isinstance(notification_queue, asyncio.Queue)

    @pytest.mark.asyncio
    async def test_permission_queue_property(self) -> None:
        """Получение очереди разрешений через property."""
        queues = RoutingQueues()
        permission_queue = queues.permission_queue

        assert isinstance(permission_queue, asyncio.Queue)

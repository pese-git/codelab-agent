"""RoutingQueues - управление очередями маршрутизации.

Хранилище для:
- Отдельных очередей RPC ответов (по request_id)
- Общей очереди асинхронных уведомлений
- Общей очереди запросов разрешения
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from codelab.client.messages import JsonRpcId


class RoutingQueues:
    """Управляет системой очередей маршрутизации.

    Архитектура очередей:
    1. response_queues: dict[request_id → asyncio.Queue]
       - Отдельная очередь для каждого RPC запроса
       - Содержит ответ на конкретный request

    2. notification_queue: asyncio.Queue
       - Общая очередь для всех асинхронных уведомлений
       - session/update, session/cancel

    3. permission_queue: asyncio.Queue
       - Общая очередь для всех запросов разрешения
       - session/request_permission
    """

    def __init__(self) -> None:
        """Инициализирует систему очередей."""
        self._logger = structlog.get_logger("routing_queues")

        # Очереди RPC ответов: {request_id → asyncio.Queue}
        self._response_queues: dict[JsonRpcId, asyncio.Queue[dict[str, Any]]] = {}

        # Общая очередь уведомлений
        self._notification_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        # Общая очередь запросов разрешения
        self._permission_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        # Lock для синхронизации доступа к response_queues
        self._response_queues_lock = asyncio.Lock()

    @property
    def notification_queue(self) -> asyncio.Queue[dict[str, Any]]:
        """Получить очередь уведомлений."""
        return self._notification_queue

    @property
    def permission_queue(self) -> asyncio.Queue[dict[str, Any]]:
        """Получить очередь запросов разрешения."""
        return self._permission_queue

    async def get_or_create_response_queue(
        self, request_id: JsonRpcId
    ) -> asyncio.Queue[dict[str, Any]]:
        """Получить или создать очередь для конкретного request_id.

        Args:
            request_id: ID запроса

        Returns:
            asyncio.Queue для этого request_id

        Note:
            Потокобезопасно - использует lock для синхронизации
        """
        async with self._response_queues_lock:
            if request_id not in self._response_queues:
                queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
                self._response_queues[request_id] = queue
                self._logger.debug("response_queue_created", request_id=request_id)
                return queue
            else:
                return self._response_queues[request_id]

    async def response_queue_exists(self, request_id: JsonRpcId) -> bool:
        """Проверить, существует ли очередь для request_id.

        Args:
            request_id: ID запроса

        Returns:
            True если очередь существует и ждет ответов
        """
        async with self._response_queues_lock:
            return request_id in self._response_queues

    async def put_response(self, request_id: JsonRpcId, message: dict[str, Any]) -> None:
        """Положить RPC ответ в очередь по request_id.

        Args:
            request_id: ID запроса
            message: Ответное сообщение

        Raises:
            RuntimeError: Если очередь для этого request_id не существует
        """
        async with self._response_queues_lock:
            if request_id not in self._response_queues:
                self._logger.warning(
                    "no_queue_for_response",
                    request_id=request_id,
                    message_keys=list(message.keys()),
                )
                # Создаем очередь на лету (может случиться, если сервер отправил
                # ответ раньше, чем вызывающий создал очередь)
                queue = asyncio.Queue()
                self._response_queues[request_id] = queue
            else:
                queue = self._response_queues[request_id]

        # Кладем вне lock чтобы не блокировать
        await queue.put(message)
        self._logger.debug(
            "response_queued",
            request_id=request_id,
            message_has_result=("result" in message),
        )

    async def put_notification(self, message: dict[str, Any]) -> None:
        """Положить асинхронное уведомление в общую очередь.

        Args:
            message: Уведомление (session/update, session/cancel)
        """
        await self._notification_queue.put(message)
        self._logger.debug(
            "notification_queued",
            method=message.get("method"),
        )

    async def put_permission_request(self, message: dict[str, Any]) -> None:
        """Положить запрос разрешения в очередь.

        Args:
            message: Запрос разрешения (session/request_permission)
        """
        await self._permission_queue.put(message)
        self._logger.debug(
            "permission_request_queued",
            method=message.get("method"),
        )

    async def cleanup_response_queue(self, request_id: JsonRpcId) -> None:
        """Очистить очередь ответов после использования.

        Args:
            request_id: ID запроса

        Note:
            Должна вызываться после завершения обработки ответа
            чтобы избежать утечек памяти
        """
        async with self._response_queues_lock:
            if request_id in self._response_queues:
                del self._response_queues[request_id]
                self._logger.debug("response_queue_cleaned", request_id=request_id)

    async def broadcast_connection_error(self, error: Exception) -> None:
        """Отправить ошибку подключения всем pending очередям.

        Args:
            error: Ошибка подключения

        Note:
            Используется при разрыве WebSocket соединения.
            Пробуждает все ждущие операции с ошибкой.
        """
        async with self._response_queues_lock:
            # Для каждой очереди добавляем ошибку
            # Вызывающие могут обработать исключение в очереди
            for request_id, queue in self._response_queues.items():
                error_message = {
                    "id": request_id,
                    "error": {
                        "code": -1,
                        "message": f"Connection error: {str(error)}",
                    },
                }
                try:
                    queue.put_nowait(error_message)
                except asyncio.QueueFull:
                    self._logger.warning(
                        "error_queue_full",
                        request_id=request_id,
                    )

            self._logger.info(
                "broadcast_connection_error",
                queues_count=len(self._response_queues),
            )

    def get_pending_requests_count(self) -> int:
        """Получить количество pending запросов.

        Returns:
            Количество очередей RPC ответов, которые ждут ответов
        """
        return len(self._response_queues)

    async def clear_all(self) -> None:
        """Очистить все очереди.

        Note:
            Используется при shutdown для корректной очистки ресурсов
        """
        async with self._response_queues_lock:
            self._response_queues.clear()

        # Очищаем остальные очереди
        while not self._notification_queue.empty():
            try:
                self._notification_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        while not self._permission_queue.empty():
            try:
                self._permission_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        self._logger.info("all_queues_cleared")

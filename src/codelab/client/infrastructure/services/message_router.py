"""MessageRouter - маршрутизация сообщений по типам.

Анализирует входящие сообщения и определяет их маршрут на основе:
- message.id (для RPC ответов)
- message.method (для асинхронных уведомлений и запросов разрешения)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from codelab.client.messages import JsonRpcId


@dataclass(frozen=True)
class RoutingKey:
    """Ключ маршрутизации для сообщения."""

    queue_type: str  # "response", "notification", "permission", "unknown"
    request_id: JsonRpcId | None = None  # Для response сообщений


class MessageRouter:
    """Маршрутизирует сообщения в нужные очереди.

    Правила маршрутизации:
    1. Если message.id есть → RPC Response (в response_queue[id])
    2. Если message.method == "session/update" → Notification Queue
    3. Если message.method == "session/request_permission" → Permission Queue
    4. Если message.method == "session/cancel" → Notification Queue
    5. Остальные → Unknown (логируем ошибку)
    """

    def __init__(self) -> None:
        """Инициализирует маршрутизатор."""
        self._logger = structlog.get_logger("message_router")

    def route(self, message: dict[str, Any]) -> RoutingKey:
        """Определяет маршрут сообщения.

        Args:
            message: Сообщение от сервера (JSON-RPC или ACP уведомление)

        Returns:
            RoutingKey с информацией о маршруте
        """
        # Сначала анализируем method: server->client RPC requests тоже содержат id,
        # поэтому приоритет по id здесь ломал маршрутизацию и приводил к дедлоку.
        message_id = message.get("id")
        method = message.get("method")

        if method == "session/update":
            # Асинхронное уведомление об обновлении сессии
            self._logger.debug("route_notification_update", method=method)
            return RoutingKey(queue_type="notification")

        if method == "session/request_permission":
            # Запрос разрешения (требует ответа)
            self._logger.debug("route_permission_request", method=method)
            return RoutingKey(queue_type="permission")

        if isinstance(method, str) and (method.startswith("fs/") or method.startswith("terminal/")):
            # Agent->client RPC (fs/*, terminal/*) обрабатываем как уведомления,
            # чтобы request_with_callbacks мог забрать запрос, вызвать callback
            # и отправить response клиенту.
            self._logger.debug("route_client_rpc_request", method=method)
            return RoutingKey(queue_type="notification")

        if message_id is not None:
            # Это обычный RPC response
            self._logger.debug(
                "route_response_message",
                message_id=message_id,
                method=method,
            )
            return RoutingKey(queue_type="response", request_id=message_id)

        if method == "session/cancel":
            # Отмена запроса (асинхронное уведомление)
            self._logger.debug("route_cancel_notification", method=method)
            return RoutingKey(queue_type="notification")

        # Неизвестный тип сообщения
        self._logger.warning(
            "route_unknown_message",
            method=method,
            has_id=message_id is not None,
        )
        return RoutingKey(queue_type="unknown")

    def is_response(self, message: dict[str, Any]) -> bool:
        """Проверяет, это ответ на запрос (есть id)."""
        return message.get("id") is not None

    def is_notification(self, message: dict[str, Any]) -> bool:
        """Проверяет, это асинхронное уведомление (нет id, есть method)."""
        method = message.get("method")
        return message.get("id") is None and method in (
            "session/update",
            "session/cancel",
        )

    def is_permission_request(self, message: dict[str, Any]) -> bool:
        """Проверяет, это запрос разрешения.

        Примечание: session/request_permission - это JSON-RPC request с id,
        отправляемый сервером клиенту и ожидающий response.
        """
        return message.get("method") == "session/request_permission"

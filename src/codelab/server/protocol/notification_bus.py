"""SessionNotificationBus — per-session шина для notifications.

Бизнес-логика публикует notifications в шину, транспорт подписывается на шину
и доставляет сообщения клиенту. Это разделяет ответственность:
- Бизнес-логика не знает о транспорте
- Транспорт не знает о бизнес-логике
- Компоненты тестируются независимо

Архитектура:
    MCPSessionManager ──┐
    BackgroundExecutor ──┤──→ SessionNotificationBus ──→ Транспорт ──→ Клиент
    AgentLoop          ──┘

Пример использования:
    # Бизнес-логика публикует
    bus = await runtime_registry.get_notification_bus(session_id)
    await bus.publish(notification)

    # Транспорт подписывается при подключении
    bus.subscribe(transport.send)
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)


class SessionNotificationBus:
    """Per-session шина для notifications.

    Бизнес-логика публикует notifications, транспорт доставляет.
    Буферизует сообщения до подписки транспорта.

    Attributes:
        _subscribers: Список callback-ов для доставки.
        _buffer: Буфер сообщений до подписки.
    """

    def __init__(self) -> None:
        """Инициализирует пустую шину."""
        self._subscribers: list[Callable[[Any], Awaitable[None]]] = []
        self._buffer: list[Any] = []

    async def publish(self, message: Any) -> None:
        """Публикует notification.

        Если есть подписчики — доставляет всем.
        Если нет подписчиков — буферизует для последующей доставки.

        Args:
            message: Сообщение для доставки.
        """
        if self._subscribers:
            for subscriber in self._subscribers:
                try:
                    await subscriber(message)
                except Exception as e:
                    logger.error(
                        "notification_delivery_failed",
                        subscriber=subscriber.__name__,
                        error=str(e),
                    )
        else:
            self._buffer.append(message)
            logger.debug(
                "notification_buffered",
                buffer_size=len(self._buffer),
            )

    def subscribe(self, callback: Callable[[Any], Awaitable[None]]) -> None:
        """Транспорт подписывается при подключении.

        Доставляет все буферизованные сообщения и очищает буфер.

        Args:
            callback: Функция для доставки сообщений.
        """
        self._subscribers.append(callback)
        logger.debug(
            "transport_subscribed",
            subscribers_count=len(self._subscribers),
            buffered_messages=len(self._buffer),
        )

        # Доставляем буферизованные сообщения
        for message in self._buffer:
            try:
                # Используем asyncio для async доставки
                import asyncio
                loop = asyncio.get_running_loop()
                loop.create_task(callback(message))
            except RuntimeError:
                # Нет running loop — пропускаем
                logger.warning(
                    "no_running_loop_for_buffered_delivery",
                    message=message,
                )
        self._buffer.clear()

    def unsubscribe(self, callback: Callable[[Any], Awaitable[None]]) -> None:
        """Транспорт отписывается при отключении.

        Args:
            callback: Функция для удаления из подписчиков.
        """
        if callback in self._subscribers:
            self._subscribers.remove(callback)
            logger.debug(
                "transport_unsubscribed",
                subscribers_count=len(self._subscribers),
            )

    def clear(self) -> None:
        """Очищает шину (подписчиков и буфер).

        Вызывается при закрытии сессии.
        """
        self._subscribers.clear()
        self._buffer.clear()
        logger.debug("notification_bus_cleared")

    @property
    def has_subscribers(self) -> bool:
        """Проверяет наличие подписчиков."""
        return len(self._subscribers) > 0

    @property
    def buffered_count(self) -> int:
        """Количество буферизованных сообщений."""
        return len(self._buffer)

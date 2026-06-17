"""Event Bus - реализация Publish-Subscribe шины для доменных событий.

EventBus обеспечивает слабую связанность между компонентами системы,
позволяя им взаимодействовать через события без прямых зависимостей.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import structlog

from codelab.client.domain.events import DomainEvent

# Тип события (любой подкласс DomainEvent)
T = TypeVar("T", bound=DomainEvent)

# Тип обработчика - может быть синхронной или асинхронной функцией
# Используем более гибкое определение без позиционного параметра
# чтобы type checker принимал функции с конкретными типами событий
EventHandler = Callable[..., Any]


class EventBus:
    """Publish-Subscribe шина для доменных событий.

    Позволяет компонентам подписываться на события и публиковать их
    без прямых зависимостей. Поддерживает как синхронные, так и
    асинхронные обработчики.

    Пример использования:
        bus = EventBus()

        async def on_session_created(event: SessionCreatedEvent) -> None:
            print(f"Session {event.session_id} was created")

        bus.subscribe(SessionCreatedEvent, on_session_created)
        await bus.publish(SessionCreatedEvent(...))
    """

    def __init__(self) -> None:
        """Инициализировать пустую шину."""
        # Словарь: тип события -> список обработчиков
        self._subscribers: dict[type[DomainEvent], list[EventHandler]] = {}
        self._logger = structlog.get_logger()

    def subscribe(
        self,
        event_type: type[T],
        handler: EventHandler,
    ) -> None:
        """Подписаться на события определённого типа.

        Args:
            event_type: Тип события для подписки (класс события)
            handler: Функция-обработчик (может быть async или sync)

        Raises:
            TypeError: Если handler не вызываемый объект
        """
        if not callable(handler):
            raise TypeError(f"Handler must be callable, got {type(handler)}")

        if event_type not in self._subscribers:
            self._subscribers[event_type] = []

        # Избегаем дубликатов подписок
        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)

            self._logger.debug(
                "subscriber_added",
                event_type=event_type.__name__,
                handler_name=getattr(handler, "__name__", str(handler)),
            )

    def unsubscribe(
        self,
        event_type: type[T],
        handler: EventHandler,
    ) -> None:
        """Отписаться от событий определённого типа.

        Args:
            event_type: Тип события, от которого отписываемся
            handler: Обработчик, который удаляем

        Raises:
            ValueError: Если обработчик не найден
        """
        if event_type not in self._subscribers:
            raise ValueError(
                f"No subscribers for event type {event_type.__name__}"
            )

        try:
            self._subscribers[event_type].remove(handler)
            self._logger.debug(
                "subscriber_removed",
                event_type=event_type.__name__,
                handler_name=getattr(handler, "__name__", str(handler)),
            )
        except ValueError as e:
            raise ValueError(
                f"Handler {handler} not subscribed to {event_type.__name__}"
            ) from e

    async def publish(self, event: T) -> None:
        """Опубликовать событие всем подписчикам.

        Событие доставляется всем зарегистрированным обработчикам.
        Обработчики могут быть синхронными или асинхронными.
        Исключения в обработчиках логируются, но не прерывают других
        обработчиков.

        Args:
            event: Событие для публикации
        """
        event_type = type(event)
        handlers = self._subscribers.get(event_type, [])

        self._logger.info(
            "event_published",
            event_type=event_type.__name__,
            aggregate_id=event.aggregate_id,
            num_handlers=len(handlers),
        )

        if not handlers:
            return

        # Подготовить список задач для параллельного выполнения
        tasks: list[Awaitable[None]] = []

        for handler in handlers:
            try:
                result = handler(event)

                # Проверить, асинхронный ли это обработчик
                if hasattr(result, "__await__"):
                    tasks.append(result)
            except Exception as e:
                self._logger.error(
                    "handler_sync_error",
                    event_type=event_type.__name__,
                    handler_name=getattr(handler, "__name__", str(handler)),
                    error=str(e),
                    exc_info=True,
                )

        # Выполнить все асинхронные обработчики параллельно
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Логировать ошибки из асинхронных обработчиков
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    handler = handlers[i]
                    self._logger.error(
                        "handler_async_error",
                        event_type=event_type.__name__,
                        handler_name=getattr(
                            handler, "__name__", str(handler)
                        ),
                        error=str(result),
                        exc_info=True,
                    )

    def subscribers_count(self, event_type: type[T]) -> int:
        """Получить количество подписчиков для типа события.

        Args:
            event_type: Тип события

        Returns:
            Количество зарегистрированных обработчиков
        """
        return len(self._subscribers.get(event_type, []))

    def has_subscribers(self, event_type: type[T]) -> bool:
        """Проверить, есть ли подписчики на событие.

        Args:
            event_type: Тип события

        Returns:
            True если есть подписчики, иначе False
        """
        return event_type in self._subscribers and len(
            self._subscribers[event_type]
        ) > 0

    def clear(self) -> None:
        """Удалить всех подписчиков со всех событий.

        Используется в основном для тестирования и очистки ресурсов.
        """
        self._subscribers.clear()
        self._logger.debug("event_bus_cleared")

    def clear_subscribers(self, event_type: type[T]) -> None:
        """Удалить всех подписчиков конкретного события.

        Args:
            event_type: Тип события, подписчиков которого удаляем
        """
        if event_type in self._subscribers:
            count = len(self._subscribers[event_type])
            self._subscribers[event_type].clear()
            self._logger.debug(
                "event_subscribers_cleared",
                event_type=event_type.__name__,
                count=count,
            )

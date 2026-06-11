"""Абстрактный интерфейс шины событий.

Определяет:
- AbstractEventBus — ABC с методами subscribe, unsubscribe, publish, clear
- Subscription — dataclass для управления подпиской
- Handler — Protocol для обработчиков событий
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from codelab.server.agent.contracts.base import DomainEvent


@runtime_checkable
class Handler(Protocol):
    """Протокол обработчика событий.

    Любой callable, принимающий DomainEvent и возвращающий None.
    """

    async def __call__(self, event: DomainEvent) -> None: ...


@dataclass
class Subscription:
    """Управление подпиской на события.

    Attributes:
        event_type: Тип события, на который оформлена подписка.
        handler: Обработчик событий.
        is_active: Флаг активности подписки.
    """

    event_type: type[DomainEvent]
    handler: Handler
    is_active: bool = field(default=True, init=False)

    def cancel(self) -> None:
        """Отменить подписку."""
        self.is_active = False


class AbstractEventBus(ABC):
    """Абстрактная шина событий для pub/sub коммуникации.

    Используется observability компонентами (MetricsTracker, EventTimeline)
    для подписки на события шины.
    """

    @abstractmethod
    def subscribe(self, event_type: type[DomainEvent], handler: Handler) -> Subscription:
        """Подписаться на события указанного типа.

        Args:
            event_type: Класс события для подписки.
            handler: Callable-обработчик.

        Returns:
            Subscription объект для управления подпиской.
        """

    @abstractmethod
    def unsubscribe(self, subscription: Subscription) -> None:
        """Отменить подписку.

        Args:
            subscription: Объект подписки, полученный из subscribe().
        """

    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        """Опубликовать событие (fire-and-forget).

        Вызывает всех активных подписчиков параллельно.
        Ошибки отдельных обработчиков логируются, не прерывая остальных.

        Args:
            event: Событие для публикации.
        """

    @abstractmethod
    async def clear(self) -> None:
        """Очистить все подписки и зарегистрированных агентов."""

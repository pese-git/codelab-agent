"""Шина событий для мультиагентной коммуникации.

Реализует два интерфейса:
- AbstractEventBus — pub/sub для observability компонентов
- AgentRoutingInterface — agent routing для стратегий выполнения

Основной класс: AgentEventBus (реализует оба интерфейса).
"""

from codelab.server.agent.event_bus.abstract import (
    AbstractEventBus,
    Handler,
    Subscription,
)
from codelab.server.agent.event_bus.bus import AgentEventBus, RetryConfig
from codelab.server.agent.event_bus.routing import (
    AgentRoutingInterface,
    RequestHandler,
)

__all__ = [
    "AbstractEventBus",
    "Subscription",
    "Handler",
    "AgentRoutingInterface",
    "RequestHandler",
    "AgentEventBus",
    "RetryConfig",
]

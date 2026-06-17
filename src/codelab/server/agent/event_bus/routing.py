"""Протокол маршрутизации агентов.

Определяет:
- RequestHandler — Protocol для обработчиков запросов к агентам
- AgentRoutingInterface — Protocol для управления routing
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from codelab.server.agent.contracts.base import (
        AgentRequest,
        AgentResponse,
        ChoreographyAnswer,
        ContextBroadcast,
    )


# SpanContext будет определён в observability, пока используем Any
SpanContext = Any


class RequestHandler(Protocol):
    """Протокол обработчика запросов к агенту.

    Реализуется компонентом, который может выполнить запрос к конкретному
    агенту (например, LLMAdapter).
    """

    async def __call__(
        self,
        request: AgentRequest,
        parent_span: SpanContext | None = None,
    ) -> AgentResponse: ...


class AgentRoutingInterface(Protocol):
    """Протокол маршрутизации запросов к агентам.

    Используется стратегиями выполнения для отправки запросов
    конкретным агентам или broadcast всем агентам.
    """

    async def register_agent(self, agent_name: str, handler: RequestHandler) -> None:
        """Зарегистрировать обработчик для агента.

        Args:
            agent_name: Уникальное имя агента.
            handler: RequestHandler для обработки запросов.
        """

    async def unregister_agent(self, agent_name: str) -> None:
        """Удалить агента из шины.

        Args:
            agent_name: Имя агента для удаления.
        """

    async def send_request(
        self,
        request: AgentRequest,
        parent_span: SpanContext | None = None,
    ) -> AgentResponse:
        """Отправить запрос конкретному агенту.

        Args:
            request: Запрос к агенту.
            parent_span: Контекст tracing (опционально).

        Returns:
            AgentResponse — обёрнутый результат агента.

        Raises:
            AgentNotFoundError: Если агент не зарегистрирован.
            AgentDispatchError: Если все retry попытки исчерпаны.
        """

    async def broadcast(
        self,
        broadcast_msg: ContextBroadcast,
    ) -> list[ChoreographyAnswer]:
        """Отправить broadcast всем зарегистрированным агентам.

        Args:
            broadcast_msg: Сообщение для рассылки.

        Returns:
            Список ответов от всех агентов.
        """

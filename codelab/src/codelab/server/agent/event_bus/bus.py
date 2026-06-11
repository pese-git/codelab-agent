"""Реализация шины событий для мультиагентной коммуникации.

AgentEventBus реализует:
- AbstractEventBus — pub/sub для observability
- AgentRoutingInterface — agent routing для стратегий
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from codelab.server.agent.contracts.base import (
    AgentDispatchError,
    AgentListChanged,
    AgentNotFoundError,
    AgentRegistered,
    AgentRequest,
    AgentResponse,
    AgentUnregistered,
    BroadcastPartialFailure,
    ChoreographyAnswer,
    ContextBroadcast,
)
from codelab.server.agent.event_bus.abstract import AbstractEventBus, Handler, Subscription
from codelab.server.agent.event_bus.routing import AgentRoutingInterface, RequestHandler

if TYPE_CHECKING:
    from codelab.server.agent.contracts.base import DomainEvent

# SpanContext будет определён в observability, пока используем Any
SpanContext = Any

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Конфигурация retry для dispatch операций.

    Attributes:
        max_attempts: Максимальное количество попыток (default: 3).
        base_delay: Базовая задержка в секундах для exponential backoff (default: 0.1).
    """

    max_attempts: int = 3
    base_delay: float = 0.1


class AgentEventBus(AbstractEventBus, AgentRoutingInterface):
    """In-memory шина межагентской коммуникации.

    Реализует два интерфейса:
    - AbstractEventBus (pub/sub) — для observability компонентов
    - AgentRoutingInterface (agent routing) — для стратегий выполнения

    Attributes:
        _subscribers: dict[type, list[tuple[Handler, bool]]] — event_type → [(handler, is_active)]
        _agents: dict[str, RequestHandler] — agent_name → handler
        _retry_config: конфигурация retry операций
    """

    def __init__(self, retry_config: RetryConfig | None = None) -> None:
        self._subscribers: dict[type[DomainEvent], list[tuple[Handler, bool]]] = {}
        self._agents: dict[str, RequestHandler] = {}
        self._retry_config = retry_config or RetryConfig()

    # ─────────────────────────────────────────────
    # AbstractEventBus implementation
    # ─────────────────────────────────────────────

    def subscribe(self, event_type: type[DomainEvent], handler: Handler) -> Subscription:
        """Подписаться на события указанного типа."""
        subscription = Subscription(event_type=event_type, handler=handler)
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append((handler, True))
        logger.debug("Subscribed handler to %s", event_type.__name__)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        """Отменить подписку."""
        subscription.cancel()
        # Удаляем из списка
        if subscription.event_type in self._subscribers:
            self._subscribers[subscription.event_type] = [
                (h, active)
                for h, active in self._subscribers[subscription.event_type]
                if h is not subscription.handler
            ]
        logger.debug("Unsubscribed handler from %s", subscription.event_type.__name__)

    async def publish(self, event: DomainEvent) -> None:
        """Опубликовать событие — параллельный вызов всех подписчиков."""
        event_type = type(event)
        handlers = self._subscribers.get(event_type, [])
        active_handlers = [(h, active) for h, active in handlers if active]

        if not active_handlers:
            return

        async def _safe_call(handler: Handler) -> None:
            try:
                await handler(event)
            except Exception:
                logger.exception("Error in event handler for %s", event_type.__name__)

        await asyncio.gather(
            *[_safe_call(handler) for handler, _ in active_handlers],
            return_exceptions=True,
        )

    async def clear(self) -> None:
        """Очистить все подписки и зарегистрированных агентов."""
        # Публикуем AgentListChanged для всех удалённых агентов
        removed = list(self._agents.keys())
        self._agents.clear()
        self._subscribers.clear()

        if removed:
            await self.publish(AgentListChanged(removed=removed))

    # ─────────────────────────────────────────────
    # AgentRoutingInterface implementation
    # ─────────────────────────────────────────────

    async def register_agent(self, agent_name: str, handler: RequestHandler) -> None:
        """Зарегистрировать обработчик для агента."""
        self._agents[agent_name] = handler
        logger.info("Registered agent: %s", agent_name)
        await self.publish(AgentRegistered(agent_name=agent_name))

    async def unregister_agent(self, agent_name: str) -> None:
        """Удалить агента из шины."""
        if agent_name not in self._agents:
            logger.warning("Attempt to unregister unknown agent: %s", agent_name)
            return

        del self._agents[agent_name]
        logger.info("Unregistered agent: %s", agent_name)
        await self.publish(AgentUnregistered(agent_name=agent_name))

    async def send_request(
        self,
        request: AgentRequest,
        parent_span: SpanContext | None = None,
    ) -> AgentResponse:
        """Отправить запрос конкретному агенту с retry."""
        target = request.target_agent
        if target not in self._agents:
            raise AgentNotFoundError(f"Agent '{target}' is not registered")

        handler = self._agents[target]

        last_error: Exception | None = None
        for attempt in range(self._retry_config.max_attempts):
            try:
                result = await handler(request, parent_span)
                # Оборачиваем AgentResult в AgentResponse (DomainEvent)
                response = AgentResponse(
                    request_id=request.correlation_id,
                    text=result.text,
                    tool_calls=result.tool_calls,
                    usage=result.usage,
                    stop_reason=result.stop_reason,
                    agent_name=result.agent_name,
                    session_id=request.session_id,
                )
                # Публикуем для observability
                await self.publish(response)
                return response
            except Exception as exc:
                last_error = exc
                if attempt < self._retry_config.max_attempts - 1:
                    delay = self._retry_config.base_delay * (2**attempt)
                    logger.warning(
                        "Dispatch to '%s' failed (attempt %d/%d), retrying in %.2fs: %s",
                        target,
                        attempt + 1,
                        self._retry_config.max_attempts,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)

        raise AgentDispatchError(
            f"Failed to dispatch to '{target}' after {self._retry_config.max_attempts} attempts"
        ) from last_error

    async def broadcast(
        self,
        broadcast_msg: ContextBroadcast,
    ) -> list[ChoreographyAnswer]:
        """Отправить broadcast всем зарегистрированным агентам."""
        if not self._agents:
            return []

        async def _dispatch_agent(
            agent_name: str, handler: RequestHandler
        ) -> tuple[str, ChoreographyAnswer | Exception]:
            try:
                request = AgentRequest(
                    target_agent=agent_name,
                    messages=broadcast_msg.context,
                    correlation_id=broadcast_msg.correlation_id,
                    session_id=broadcast_msg.session_id,
                )
                result = await handler(request, parent_span=None)
                answer = ChoreographyAnswer(
                    agent_name=agent_name,
                    action_taken=bool(result.tool_calls),
                    reasoning=result.text,
                    output=result.text or None,
                    status_signal="completed" if result.stop_reason == "end_turn" else "continue",
                    usage=result.usage,
                    session_id=broadcast_msg.session_id,
                )
                return (agent_name, answer)
            except Exception as exc:
                logger.exception("Broadcast to '%s' failed", agent_name)
                return (agent_name, exc)

        tasks = [
            _dispatch_agent(name, handler) for name, handler in self._agents.items()
        ]
        results: list[
            tuple[str, ChoreographyAnswer | Exception] | BaseException
        ] = await asyncio.gather(
            *tasks, return_exceptions=True,
        )

        answers: list[ChoreographyAnswer] = []
        failed_agents: list[str] = []

        for item in results:
            if isinstance(item, BaseException) and not isinstance(item, tuple):
                failed_agents.append("unknown")
            else:
                agent_name, result = item  # type: ignore[assignment]
                if isinstance(result, Exception):
                    failed_agents.append(agent_name)
                else:
                    answers.append(result)

        if failed_agents:
            raise BroadcastPartialFailure(
                f"Broadcast failed for {len(failed_agents)} agent(s)",
                failed_agents=failed_agents,
            )

        return answers

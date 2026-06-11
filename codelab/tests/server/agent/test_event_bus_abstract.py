"""Тесты для AbstractEventBus, Subscription, Handler."""

import pytest

from codelab.server.agent.contracts.base import (
    DomainEvent,
)
from codelab.server.agent.event_bus.abstract import (
    Handler,
    Subscription,
)


class SampleEvent(DomainEvent):
    """Тестовое событие."""


class SampleEvent2(DomainEvent):
    """Ещё одно тестовое событие."""


class TestSubscription:
    def test_creates_active(self):
        sub = Subscription(event_type=SampleEvent, handler=lambda e: None)
        assert sub.is_active is True

    def test_cancel_sets_inactive(self):
        sub = Subscription(event_type=SampleEvent, handler=lambda e: None)
        sub.cancel()
        assert sub.is_active is False

    def test_stores_event_type(self):
        sub = Subscription(event_type=SampleEvent, handler=lambda e: None)
        assert sub.event_type is SampleEvent

    def test_stores_handler(self):
        def handler(e: DomainEvent) -> None:
            pass

        sub = Subscription(event_type=SampleEvent, handler=handler)
        assert sub.handler is handler


class TestHandlerProtocol:
    def test_async_function_is_handler(self):
        async def my_handler(event: DomainEvent) -> None:
            pass

        assert isinstance(my_handler, Handler)


class TestAbstractEventBus:
    """Тесты через конкретную реализацию AgentEventBus."""

    @pytest.fixture
    def bus(self):
        from codelab.server.agent.event_bus.bus import AgentEventBus

        return AgentEventBus()

    @pytest.mark.asyncio
    async def test_subscribe_returns_subscription(self, bus):
        async def handler(event: DomainEvent) -> None:
            pass

        sub = bus.subscribe(SampleEvent, handler)
        assert isinstance(sub, Subscription)
        assert sub.event_type is SampleEvent
        assert sub.is_active is True

    @pytest.mark.asyncio
    async def test_unsubscribe_deactivates(self, bus):
        async def handler(event: DomainEvent) -> None:
            pass

        sub = bus.subscribe(SampleEvent, handler)
        bus.unsubscribe(sub)
        assert sub.is_active is False

    @pytest.mark.asyncio
    async def test_publish_calls_active_handlers(self, bus):
        received = []

        async def handler1(event: DomainEvent) -> None:
            received.append(1)

        async def handler2(event: DomainEvent) -> None:
            received.append(2)

        bus.subscribe(SampleEvent, handler1)
        bus.subscribe(SampleEvent, handler2)

        await bus.publish(SampleEvent(session_id="test"))

        assert 1 in received
        assert 2 in received

    @pytest.mark.asyncio
    async def test_publish_does_not_call_unsubscribed(self, bus):
        received = []

        async def handler(event: DomainEvent) -> None:
            received.append(1)

        sub = bus.subscribe(SampleEvent, handler)
        bus.unsubscribe(sub)

        await bus.publish(SampleEvent(session_id="test"))

        assert received == []

    @pytest.mark.asyncio
    async def test_publish_error_does_not_stop_other_handlers(self, bus):
        received = []

        async def bad_handler(event: DomainEvent) -> None:
            raise ValueError("boom")

        async def good_handler(event: DomainEvent) -> None:
            received.append("ok")

        bus.subscribe(SampleEvent, bad_handler)
        bus.subscribe(SampleEvent, good_handler)

        await bus.publish(SampleEvent(session_id="test"))

        assert received == ["ok"]

    @pytest.mark.asyncio
    async def test_publish_only_matching_type(self, bus):
        received = []

        async def handler(event: DomainEvent) -> None:
            received.append(1)

        bus.subscribe(SampleEvent, handler)

        await bus.publish(SampleEvent2(session_id="test"))

        assert received == []

    @pytest.mark.asyncio
    async def test_clear_removes_all_subscribers(self, bus):
        received = []

        async def handler(event: DomainEvent) -> None:
            received.append(1)

        bus.subscribe(SampleEvent, handler)
        await bus.clear()

        await bus.publish(SampleEvent(session_id="test"))

        assert received == []

    @pytest.mark.asyncio
    async def test_multiple_subscriptions_same_type(self, bus):
        count = 0

        async def handler(event: DomainEvent) -> None:
            nonlocal count
            count += 1

        bus.subscribe(SampleEvent, handler)
        bus.subscribe(SampleEvent, handler)

        await bus.publish(SampleEvent(session_id="test"))

        # Оба обработчика вызваны
        assert count == 2

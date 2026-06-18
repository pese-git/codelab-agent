"""Tests for EventBus - Publish-Subscribe event system.

Comprehensive tests for EventBus functionality including synchronous
and asynchronous handlers, error handling, and subscription management.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from codelab.client.domain.events import (
    DomainEvent,
    PermissionRequestedEvent,
    PromptCompletedEvent,
    SessionCreatedEvent,
)
from codelab.client.infrastructure.events.bus import EventBus


class TestEventBusBasics:
    """Базовые тесты для EventBus."""

    def test_event_bus_creation(self) -> None:
        """Тест: EventBus успешно создаётся."""
        bus = EventBus()
        assert bus is not None

    def test_subscribe_sync_handler(self) -> None:
        """Тест: можно подписаться на событие с синхронным обработчиком."""
        bus = EventBus()
        handler = lambda event: None  # noqa: E731

        bus.subscribe(SessionCreatedEvent, handler)
        assert bus.subscribers_count(SessionCreatedEvent) == 1

    def test_subscribe_async_handler(self) -> None:
        """Тест: можно подписаться на событие с асинхронным обработчиком."""
        bus = EventBus()

        async def async_handler(event: SessionCreatedEvent) -> None:
            await asyncio.sleep(0)

        bus.subscribe(SessionCreatedEvent, async_handler)
        assert bus.subscribers_count(SessionCreatedEvent) == 1

    def test_subscribe_prevents_duplicates(self) -> None:
        """Тест: один обработчик не может быть подписан дважды."""
        bus = EventBus()
        handler = lambda event: None  # noqa: E731

        bus.subscribe(SessionCreatedEvent, handler)
        bus.subscribe(SessionCreatedEvent, handler)  # Duplicate

        assert bus.subscribers_count(SessionCreatedEvent) == 1

    def test_subscribe_multiple_different_handlers(self) -> None:
        """Тест: можно подписать несколько разных обработчиков."""
        bus = EventBus()
        handler1 = lambda event: None  # noqa: E731
        handler2 = lambda event: None  # noqa: E731

        bus.subscribe(SessionCreatedEvent, handler1)
        bus.subscribe(SessionCreatedEvent, handler2)

        assert bus.subscribers_count(SessionCreatedEvent) == 2

    def test_subscribe_non_callable_raises_error(self) -> None:
        """Тест: попытка подписать не-вызываемый объект вызывает ошибку."""
        bus = EventBus()

        with pytest.raises(TypeError, match="Handler must be callable"):
            bus.subscribe(SessionCreatedEvent, "not_callable")  # type: ignore

    def test_unsubscribe_handler(self) -> None:
        """Тест: можно отписать обработчик."""
        bus = EventBus()
        handler = lambda event: None  # noqa: E731

        bus.subscribe(SessionCreatedEvent, handler)
        assert bus.subscribers_count(SessionCreatedEvent) == 1

        bus.unsubscribe(SessionCreatedEvent, handler)
        assert bus.subscribers_count(SessionCreatedEvent) == 0

    def test_unsubscribe_nonexistent_handler_raises_error(self) -> None:
        """Тест: попытка отписать несуществующий обработчик вызывает ошибку."""
        bus = EventBus()
        handler1 = lambda event: None  # noqa: E731
        handler2 = lambda event: None  # noqa: E731

        bus.subscribe(SessionCreatedEvent, handler1)

        with pytest.raises(ValueError, match="Handler .* not subscribed"):
            bus.unsubscribe(SessionCreatedEvent, handler2)


class TestEventBusPublishing:
    """Тесты публикации событий."""

    @pytest.mark.asyncio
    async def test_publish_calls_sync_handler(self) -> None:
        """Тест: публикация вызывает синхронный обработчик."""
        bus = EventBus()
        called = False

        def handler(event: SessionCreatedEvent) -> None:
            nonlocal called
            called = True

        bus.subscribe(SessionCreatedEvent, handler)

        event = SessionCreatedEvent(
            aggregate_id="session1",
            occurred_at=datetime.now(UTC),
            session_id="session1",
            server_host="localhost",
            server_port=8000,
        )
        await bus.publish(event)

        assert called is True

    @pytest.mark.asyncio
    async def test_publish_calls_async_handler(self) -> None:
        """Тест: публикация вызывает асинхронный обработчик."""
        bus = EventBus()
        called = False

        async def handler(event: SessionCreatedEvent) -> None:
            nonlocal called
            called = True
            await asyncio.sleep(0)

        bus.subscribe(SessionCreatedEvent, handler)

        event = SessionCreatedEvent(
            aggregate_id="session1",
            occurred_at=datetime.now(UTC),
            session_id="session1",
            server_host="localhost",
            server_port=8000,
        )
        await bus.publish(event)

        assert called is True

    @pytest.mark.asyncio
    async def test_publish_calls_multiple_handlers(self) -> None:
        """Тест: публикация вызывает всех подписчиков."""
        bus = EventBus()
        calls = []

        def handler1(event: SessionCreatedEvent) -> None:
            calls.append(1)

        def handler2(event: SessionCreatedEvent) -> None:
            calls.append(2)

        bus.subscribe(SessionCreatedEvent, handler1)
        bus.subscribe(SessionCreatedEvent, handler2)

        event = SessionCreatedEvent(
            aggregate_id="session1",
            occurred_at=datetime.now(UTC),
            session_id="session1",
            server_host="localhost",
            server_port=8000,
        )
        await bus.publish(event)

        assert len(calls) == 2
        assert set(calls) == {1, 2}

    @pytest.mark.asyncio
    async def test_publish_mixed_sync_async_handlers(self) -> None:
        """Тест: публикация работает с смешанными синхронными и асинхронными обработчиками."""
        bus = EventBus()
        calls = []

        def sync_handler(event: SessionCreatedEvent) -> None:
            calls.append("sync")

        async def async_handler(event: SessionCreatedEvent) -> None:
            calls.append("async")
            await asyncio.sleep(0.01)

        bus.subscribe(SessionCreatedEvent, sync_handler)
        bus.subscribe(SessionCreatedEvent, async_handler)

        event = SessionCreatedEvent(
            aggregate_id="session1",
            occurred_at=datetime.now(UTC),
            session_id="session1",
            server_host="localhost",
            server_port=8000,
        )
        await bus.publish(event)

        assert "sync" in calls
        assert "async" in calls

    @pytest.mark.asyncio
    async def test_publish_no_handlers(self) -> None:
        """Тест: публикация события без подписчиков не вызывает ошибку."""
        bus = EventBus()

        event = SessionCreatedEvent(
            aggregate_id="session1",
            occurred_at=datetime.now(UTC),
            session_id="session1",
            server_host="localhost",
            server_port=8000,
        )
        # Не должно быть исключений
        await bus.publish(event)

    @pytest.mark.asyncio
    async def test_publish_only_matching_event_types(self) -> None:
        """Тест: подписчики получают только события своего типа."""
        bus = EventBus()
        session_calls = []
        prompt_calls = []

        def session_handler(event: SessionCreatedEvent) -> None:
            session_calls.append(1)

        def prompt_handler(event: PromptCompletedEvent) -> None:
            prompt_calls.append(1)

        bus.subscribe(SessionCreatedEvent, session_handler)
        bus.subscribe(PromptCompletedEvent, prompt_handler)

        session_event = SessionCreatedEvent(
            aggregate_id="session1",
            occurred_at=datetime.now(UTC),
            session_id="session1",
            server_host="localhost",
            server_port=8000,
        )
        await bus.publish(session_event)

        assert len(session_calls) == 1
        assert len(prompt_calls) == 0


class TestEventBusErrorHandling:
    """Тесты обработки ошибок в обработчиках."""

    @pytest.mark.asyncio
    async def test_sync_handler_error_doesnt_stop_other_handlers(self) -> None:
        """Тест: ошибка в синхронном обработчике не останавливает других."""
        bus = EventBus()
        called = []

        def failing_handler(event: SessionCreatedEvent) -> None:
            raise ValueError("Test error")

        def working_handler(event: SessionCreatedEvent) -> None:
            called.append(1)

        bus.subscribe(SessionCreatedEvent, failing_handler)
        bus.subscribe(SessionCreatedEvent, working_handler)

        event = SessionCreatedEvent(
            aggregate_id="session1",
            occurred_at=datetime.now(UTC),
            session_id="session1",
            server_host="localhost",
            server_port=8000,
        )
        await bus.publish(event)

        assert len(called) == 1

    @pytest.mark.asyncio
    async def test_async_handler_error_doesnt_stop_other_handlers(self) -> None:
        """Тест: ошибка в асинхронном обработчике не останавливает других."""
        bus = EventBus()
        called = []

        async def failing_handler(event: SessionCreatedEvent) -> None:
            raise ValueError("Test error")

        async def working_handler(event: SessionCreatedEvent) -> None:
            called.append(1)

        bus.subscribe(SessionCreatedEvent, failing_handler)
        bus.subscribe(SessionCreatedEvent, working_handler)

        event = SessionCreatedEvent(
            aggregate_id="session1",
            occurred_at=datetime.now(UTC),
            session_id="session1",
            server_host="localhost",
            server_port=8000,
        )
        await bus.publish(event)

        assert len(called) == 1


class TestEventBusSubscriberManagement:
    """Тесты управления подписчиками."""

    def test_subscribers_count(self) -> None:
        """Тест: метод subscribers_count возвращает правильное количество."""
        bus = EventBus()
        handler1 = lambda event: None  # noqa: E731
        handler2 = lambda event: None  # noqa: E731

        assert bus.subscribers_count(SessionCreatedEvent) == 0

        bus.subscribe(SessionCreatedEvent, handler1)
        assert bus.subscribers_count(SessionCreatedEvent) == 1

        bus.subscribe(SessionCreatedEvent, handler2)
        assert bus.subscribers_count(SessionCreatedEvent) == 2

        bus.unsubscribe(SessionCreatedEvent, handler1)
        assert bus.subscribers_count(SessionCreatedEvent) == 1

    def test_has_subscribers(self) -> None:
        """Тест: метод has_subscribers правильно определяет наличие подписчиков."""
        bus = EventBus()
        handler = lambda event: None  # noqa: E731

        assert not bus.has_subscribers(SessionCreatedEvent)

        bus.subscribe(SessionCreatedEvent, handler)
        assert bus.has_subscribers(SessionCreatedEvent)

        bus.unsubscribe(SessionCreatedEvent, handler)
        assert not bus.has_subscribers(SessionCreatedEvent)

    def test_clear_all_subscribers(self) -> None:
        """Тест: clear() удаляет всех подписчиков со всех событий."""
        bus = EventBus()
        handler1 = lambda event: None  # noqa: E731
        handler2 = lambda event: None  # noqa: E731

        bus.subscribe(SessionCreatedEvent, handler1)
        bus.subscribe(PromptCompletedEvent, handler2)

        assert bus.subscribers_count(SessionCreatedEvent) == 1
        assert bus.subscribers_count(PromptCompletedEvent) == 1

        bus.clear()

        assert bus.subscribers_count(SessionCreatedEvent) == 0
        assert bus.subscribers_count(PromptCompletedEvent) == 0

    def test_clear_subscribers_for_specific_event(self) -> None:
        """Тест: clear_subscribers() удаляет подписчиков конкретного события."""
        bus = EventBus()
        handler1 = lambda event: None  # noqa: E731
        handler2 = lambda event: None  # noqa: E731

        bus.subscribe(SessionCreatedEvent, handler1)
        bus.subscribe(PromptCompletedEvent, handler2)

        assert bus.subscribers_count(SessionCreatedEvent) == 1
        assert bus.subscribers_count(PromptCompletedEvent) == 1

        bus.clear_subscribers(SessionCreatedEvent)

        assert bus.subscribers_count(SessionCreatedEvent) == 0
        assert bus.subscribers_count(PromptCompletedEvent) == 1


class TestEventBusRealWorldScenarios:
    """Реальные сценарии использования EventBus."""

    @pytest.mark.asyncio
    async def test_event_bus_with_multiple_event_types(self) -> None:
        """Тест: работа с несколькими типами событий одновременно."""
        bus = EventBus()
        events_received: list[str] = []

        def session_handler(event: SessionCreatedEvent) -> None:
            events_received.append("session_created")

        async def prompt_handler(event: PromptCompletedEvent) -> None:
            events_received.append("prompt_completed")
            await asyncio.sleep(0)

        def permission_handler(event: PermissionRequestedEvent) -> None:
            events_received.append("permission_requested")

        bus.subscribe(SessionCreatedEvent, session_handler)
        bus.subscribe(PromptCompletedEvent, prompt_handler)
        bus.subscribe(PermissionRequestedEvent, permission_handler)

        # Публикуем события
        session_event = SessionCreatedEvent(
            aggregate_id="session1",
            occurred_at=datetime.now(UTC),
            session_id="session1",
            server_host="localhost",
            server_port=8000,
        )
        await bus.publish(session_event)

        prompt_event = PromptCompletedEvent(
            aggregate_id="session1",
            occurred_at=datetime.now(UTC),
            session_id="session1",
            stop_reason="end_turn",
        )
        await bus.publish(prompt_event)

        permission_event = PermissionRequestedEvent(
            aggregate_id="session1",
            occurred_at=datetime.now(UTC),
            session_id="session1",
            action="execute",
            resource="/bin/bash",
            permission_id="perm1",
        )
        await bus.publish(permission_event)

        assert len(events_received) == 3
        assert "session_created" in events_received
        assert "prompt_completed" in events_received
        assert "permission_requested" in events_received

    @pytest.mark.asyncio
    async def test_event_bus_with_stateful_handler(self) -> None:
        """Тест: обработчик может хранить состояние между событиями."""
        bus = EventBus()

        class StatefulHandler:
            def __init__(self) -> None:
                self.events_count = 0

            def handle(self, event: DomainEvent) -> None:
                self.events_count += 1

        handler = StatefulHandler()

        bus.subscribe(SessionCreatedEvent, handler.handle)
        bus.subscribe(PromptCompletedEvent, handler.handle)

        session_event = SessionCreatedEvent(
            aggregate_id="session1",
            occurred_at=datetime.now(UTC),
            session_id="session1",
            server_host="localhost",
            server_port=8000,
        )
        await bus.publish(session_event)

        prompt_event = PromptCompletedEvent(
            aggregate_id="session1",
            occurred_at=datetime.now(UTC),
            session_id="session1",
            stop_reason="end_turn",
        )
        await bus.publish(prompt_event)

        assert handler.events_count == 2

    @pytest.mark.asyncio
    async def test_dynamic_subscription_and_unsubscription(self) -> None:
        """Тест: динамическая подписка/отписка во время обработки событий."""
        bus = EventBus()
        calls = []

        def handler1(event: SessionCreatedEvent) -> None:
            calls.append(1)

        def handler2(event: SessionCreatedEvent) -> None:
            calls.append(2)
            # Отписываемся во время обработки события
            bus.unsubscribe(SessionCreatedEvent, handler1)

        bus.subscribe(SessionCreatedEvent, handler1)
        bus.subscribe(SessionCreatedEvent, handler2)

        event = SessionCreatedEvent(
            aggregate_id="session1",
            occurred_at=datetime.now(UTC),
            session_id="session1",
            server_host="localhost",
            server_port=8000,
        )
        await bus.publish(event)

        # Оба обработчика должны быть вызваны в этом событии
        assert len(calls) == 2

        # Но при следующем событии handler1 не будет вызван
        calls.clear()
        await bus.publish(event)
        assert len(calls) == 1
        assert 2 in calls

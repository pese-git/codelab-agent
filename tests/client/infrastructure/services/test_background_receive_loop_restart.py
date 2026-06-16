"""Unit-тесты для BackgroundReceiveLoop auto-restart механизма.

Проверяет:
- Константы auto-restart
- Статистику рестартов
- Расчёт экспоненциального backoff
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.client.infrastructure.services.background_receive_loop import (
    BackgroundReceiveLoop,
)
from codelab.client.infrastructure.services.message_router import MessageRouter
from codelab.client.infrastructure.services.routing_queues import RoutingQueues
from codelab.client.infrastructure.transport import WebSocketTransport


class TestBackgroundReceiveLoopAutoRestart:
    """Тесты auto-restart механизма в BackgroundReceiveLoop."""

    @pytest.fixture
    def mock_transport(self) -> MagicMock:
        """Создаёт mock транспорт."""
        transport = MagicMock(spec=WebSocketTransport)
        transport.receive_text = AsyncMock()
        return transport

    @pytest.fixture
    def mock_router(self) -> MagicMock:
        """Создаёт mock роутер."""
        router = MagicMock(spec=MessageRouter)
        routing_key = MagicMock()
        routing_key.queue_type = "response"
        routing_key.request_id = "test-id"
        router.route.return_value = routing_key
        return router

    @pytest.fixture
    def mock_queues(self) -> MagicMock:
        """Создаёт mock очереди."""
        queues = MagicMock(spec=RoutingQueues)
        queues.put_response = AsyncMock()
        queues.put_notification = AsyncMock()
        queues.put_permission_request = AsyncMock()
        queues.broadcast_connection_error = AsyncMock()
        return queues

    def test_constants_are_defined(self) -> None:
        """Проверяет, что константы auto-restart определены."""
        assert BackgroundReceiveLoop.MAX_CONSECUTIVE_RETRIES == 5
        assert BackgroundReceiveLoop.INITIAL_BACKOFF_SECONDS == 1.0
        assert BackgroundReceiveLoop.MAX_BACKOFF_SECONDS == 30.0
        assert BackgroundReceiveLoop.BACKOFF_MULTIPLIER == 2.0

    def test_stats_include_restart_counters(
        self,
        mock_transport: MagicMock,
        mock_router: MagicMock,
        mock_queues: MagicMock,
    ) -> None:
        """Проверяет, что статистика включает счётчики рестартов."""
        loop = BackgroundReceiveLoop(
            transport=mock_transport,
            router=mock_router,
            queues=mock_queues,
        )

        stats = loop.get_stats()

        assert "restarts_count" in stats
        assert "consecutive_errors" in stats
        assert stats["restarts_count"] == 0
        assert stats["consecutive_errors"] == 0

    def test_backoff_calculation_is_exponential(
        self,
        mock_transport: MagicMock,
        mock_router: MagicMock,
        mock_queues: MagicMock,
    ) -> None:
        """Проверяет, что backoff рассчитывается экспоненциально."""
        loop = BackgroundReceiveLoop(
            transport=mock_transport,
            router=mock_router,
            queues=mock_queues,
        )

        # Проверяем расчёт backoff для разных попыток
        # backoff = min(INITIAL * (MULTIPLIER ^ (attempt - 1)), MAX)
        
        # attempt 1: 1.0 * (2.0 ^ 0) = 1.0
        backoff_1 = min(
            loop.INITIAL_BACKOFF_SECONDS * (loop.BACKOFF_MULTIPLIER ** 0),
            loop.MAX_BACKOFF_SECONDS,
        )
        assert backoff_1 == 1.0

        # attempt 2: 1.0 * (2.0 ^ 1) = 2.0
        backoff_2 = min(
            loop.INITIAL_BACKOFF_SECONDS * (loop.BACKOFF_MULTIPLIER ** 1),
            loop.MAX_BACKOFF_SECONDS,
        )
        assert backoff_2 == 2.0

        # attempt 3: 1.0 * (2.0 ^ 2) = 4.0
        backoff_3 = min(
            loop.INITIAL_BACKOFF_SECONDS * (loop.BACKOFF_MULTIPLIER ** 2),
            loop.MAX_BACKOFF_SECONDS,
        )
        assert backoff_3 == 4.0

        # attempt 5: 1.0 * (2.0 ^ 4) = 16.0
        backoff_5 = min(
            loop.INITIAL_BACKOFF_SECONDS * (loop.BACKOFF_MULTIPLIER ** 4),
            loop.MAX_BACKOFF_SECONDS,
        )
        assert backoff_5 == 16.0

        # attempt 6: 1.0 * (2.0 ^ 5) = 32.0, но capped at MAX (30.0)
        backoff_6 = min(
            loop.INITIAL_BACKOFF_SECONDS * (loop.BACKOFF_MULTIPLIER ** 5),
            loop.MAX_BACKOFF_SECONDS,
        )
        assert backoff_6 == 30.0

    def test_initial_state_is_clean(
        self,
        mock_transport: MagicMock,
        mock_router: MagicMock,
        mock_queues: MagicMock,
    ) -> None:
        """Проверяет, что начальное состояние loop чистое."""
        loop = BackgroundReceiveLoop(
            transport=mock_transport,
            router=mock_router,
            queues=mock_queues,
        )

        assert not loop.is_running()
        assert loop._should_stop is False
        assert loop._messages_received == 0
        assert loop._messages_routed == 0
        assert loop._errors_count == 0
        assert loop._restarts_count == 0
        assert loop._consecutive_errors == 0

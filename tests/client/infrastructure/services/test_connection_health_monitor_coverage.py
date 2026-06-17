"""Тесты покрытия для ConnectionHealthMonitor.

Покрывает ранее непокрытые сценарии:
- отмену задачи мониторинга при таймауте остановки;
- обработку asyncio.CancelledError внутри monitoring_loop;
- обработку произвольных исключений в monitoring_loop.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from codelab.client.infrastructure.services.connection_health_monitor import (
    ConnectionHealthMonitor,
)


class TestConnectionHealthMonitorStop:
    """Тесты для stop()."""

    async def test_stop_cancels_task_on_timeout(self) -> None:
        """stop() отменяет задачу, если она не завершилась за таймаут."""
        receive_loop = MagicMock()
        receive_loop.get_stats.return_value = {
            "running": True,
            "restarts_count": 0,
            "consecutive_errors": 0,
            "errors_count": 0,
            "messages_received": 0,
            "messages_routed": 0,
        }

        monitor = ConnectionHealthMonitor(
            receive_loop=receive_loop,
            session_id="test-session",
        )

        await monitor.start()
        assert monitor._task is not None
        assert not monitor._task.done()

        with patch.object(
            monitor,
            "CHECK_INTERVAL_SECONDS",
            60.0,
        ), patch(
            "codelab.client.infrastructure.services.connection_health_monitor.asyncio.wait_for",
            side_effect=TimeoutError,
        ):
            await monitor.stop()

        assert monitor._task.done()
        assert monitor._should_stop is True


class TestConnectionHealthMonitorMonitoringLoop:
    """Тесты для _monitoring_loop()."""

    async def test_monitoring_loop_handles_cancelled_error(self) -> None:
        """Цикл корректно завершается при asyncio.CancelledError."""
        receive_loop = MagicMock()
        receive_loop.get_stats.return_value = {
            "running": True,
            "restarts_count": 0,
            "consecutive_errors": 0,
            "errors_count": 0,
            "messages_received": 0,
            "messages_routed": 0,
        }

        monitor = ConnectionHealthMonitor(
            receive_loop=receive_loop,
            session_id="test-session",
        )

        with patch.object(
            monitor,
            "_check_health",
            side_effect=asyncio.CancelledError,
        ), patch.object(
            monitor,
            "CHECK_INTERVAL_SECONDS",
            0.01,
        ):
            await monitor._monitoring_loop()

        assert monitor._should_stop is False

    async def test_monitoring_loop_handles_check_health_exception(self) -> None:
        """Цикл продолжает работу после исключения в _check_health."""
        receive_loop = MagicMock()
        receive_loop.get_stats.return_value = {
            "running": True,
            "restarts_count": 0,
            "consecutive_errors": 0,
            "errors_count": 0,
            "messages_received": 0,
            "messages_routed": 0,
        }

        monitor = ConnectionHealthMonitor(
            receive_loop=receive_loop,
            session_id="test-session",
        )

        call_count = 0

        async def failing_then_stop() -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("health check failed")
            monitor._should_stop = True

        with patch.object(
            monitor,
            "_check_health",
            side_effect=failing_then_stop,
        ), patch.object(
            monitor,
            "CHECK_INTERVAL_SECONDS",
            0.01,
        ):
            await monitor._monitoring_loop()

        assert call_count >= 2
        assert monitor._should_stop is True

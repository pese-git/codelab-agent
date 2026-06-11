"""Тесты для ConnectionHealthMonitor."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from codelab.client.infrastructure.services.connection_health_monitor import (
    ConnectionHealthMonitor,
)


class TestConnectionHealthMonitorInit:
    """Тесты для инициализации ConnectionHealthMonitor."""

    def test_initial_state(self) -> None:
        """Начальное состояние корректное."""
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

        assert monitor._session_id == "test-session"
        assert monitor._task is None
        assert monitor._should_stop is False
        assert monitor._degradation_detected is False
        assert monitor._failure_detected is False


class TestConnectionHealthMonitorStart:
    """Тесты для start()."""

    @pytest.mark.asyncio
    async def test_start_creates_task(self) -> None:
        """start() создаёт фоновую задачу."""
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

        await monitor.stop()

    @pytest.mark.asyncio
    async def test_start_already_running_does_nothing(self) -> None:
        """Повторный start() не создаёт новую задачу."""
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
        first_task = monitor._task

        await monitor.start()

        assert monitor._task is first_task

        await monitor.stop()


class TestConnectionHealthMonitorStop:
    """Тесты для stop()."""

    @pytest.mark.asyncio
    async def test_stop_not_running_does_nothing(self) -> None:
        """stop() когда не запущен — ничего не делает."""
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

        await monitor.stop()

        assert monitor._task is None


class TestConnectionHealthMonitorCheckHealth:
    """Тесты для _check_health()."""

    @pytest.mark.asyncio
    async def test_degradation_detected_on_restarts(self) -> None:
        """Деградация обнаруживается при рестартах."""
        receive_loop = MagicMock()
        receive_loop.get_stats.return_value = {
            "running": True,
            "restarts_count": 2,
            "consecutive_errors": 0,
            "errors_count": 2,
            "messages_received": 100,
            "messages_routed": 98,
        }

        monitor = ConnectionHealthMonitor(
            receive_loop=receive_loop,
            session_id="test-session",
        )

        await monitor._check_health()

        assert monitor._degradation_detected is True
        assert monitor._failure_detected is False

    @pytest.mark.asyncio
    async def test_failure_detected_on_stopped_loop(self) -> None:
        """Отказ обнаруживается когда loop остановлен."""
        receive_loop = MagicMock()
        receive_loop.get_stats.return_value = {
            "running": False,
            "restarts_count": 0,
            "consecutive_errors": 5,
            "errors_count": 5,
            "messages_received": 0,
            "messages_routed": 0,
        }

        monitor = ConnectionHealthMonitor(
            receive_loop=receive_loop,
            session_id="test-session",
        )

        await monitor._check_health()

        assert monitor._degradation_detected is False
        assert monitor._failure_detected is True

    @pytest.mark.asyncio
    async def test_no_issue_when_running_clean(self) -> None:
        """Нет проблем когда loop работает без ошибок."""
        receive_loop = MagicMock()
        receive_loop.get_stats.return_value = {
            "running": True,
            "restarts_count": 0,
            "consecutive_errors": 0,
            "errors_count": 0,
            "messages_received": 100,
            "messages_routed": 100,
        }

        monitor = ConnectionHealthMonitor(
            receive_loop=receive_loop,
            session_id="test-session",
        )

        await monitor._check_health()

        assert monitor._degradation_detected is False
        assert monitor._failure_detected is False

    @pytest.mark.asyncio
    async def test_degradation_only_reported_once(self) -> None:
        """Деградация логируется только один раз."""
        receive_loop = MagicMock()
        receive_loop.get_stats.return_value = {
            "running": True,
            "restarts_count": 2,
            "consecutive_errors": 0,
            "errors_count": 2,
            "messages_received": 100,
            "messages_routed": 98,
        }

        monitor = ConnectionHealthMonitor(
            receive_loop=receive_loop,
            session_id="test-session",
        )

        await monitor._check_health()
        assert monitor._degradation_detected is True

        receive_loop.get_stats.return_value = {
            "running": True,
            "restarts_count": 5,
            "consecutive_errors": 0,
            "errors_count": 5,
            "messages_received": 200,
            "messages_routed": 195,
        }

        await monitor._check_health()

        assert monitor._degradation_detected is True


class TestConnectionHealthMonitorGetHealthStatus:
    """Тесты для get_health_status()."""

    def test_returns_full_status(self) -> None:
        """Возвращает полную информацию о состоянии."""
        receive_loop = MagicMock()
        receive_loop.get_stats.return_value = {
            "running": True,
            "restarts_count": 2,
            "consecutive_errors": 1,
            "errors_count": 3,
            "messages_received": 150,
            "messages_routed": 148,
        }

        monitor = ConnectionHealthMonitor(
            receive_loop=receive_loop,
            session_id="test-session",
        )
        monitor._degradation_detected = True

        status = monitor.get_health_status()

        assert status["session_id"] == "test-session"
        assert status["is_running"] is True
        assert status["restarts_count"] == 2
        assert status["consecutive_errors"] == 1
        assert status["total_errors"] == 3
        assert status["messages_received"] == 150
        assert status["messages_routed"] == 148
        assert status["degradation_detected"] is True
        assert status["failure_detected"] is False

    def test_returns_defaults_when_stats_empty(self) -> None:
        """Возвращает defaults когда stats пустой."""
        receive_loop = MagicMock()
        receive_loop.get_stats.return_value = {}

        monitor = ConnectionHealthMonitor(
            receive_loop=receive_loop,
            session_id="test-session",
        )

        status = monitor.get_health_status()

        assert status["is_running"] is False
        assert status["restarts_count"] == 0
        assert status["consecutive_errors"] == 0


class TestConnectionHealthMonitorMonitoringLoop:
    """Тесты для _monitoring_loop()."""

    @pytest.mark.asyncio
    async def test_monitoring_loop_stops_on_flag(self) -> None:
        """Цикл останавливается когда _should_stop=True."""
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

        async def set_stop_after_delay() -> None:
            await asyncio.sleep(0.1)
            monitor._should_stop = True

        asyncio.create_task(set_stop_after_delay())

        with patch.object(
            monitor,
            "CHECK_INTERVAL_SECONDS",
            0.05,
        ):
            await monitor._monitoring_loop()

        assert monitor._should_stop is True

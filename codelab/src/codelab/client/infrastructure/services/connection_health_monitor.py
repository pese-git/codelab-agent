"""ConnectionHealthMonitor - мониторинг здоровья соединения.

Отвечает за:
- Периодическую проверку состояния BackgroundReceiveLoop
- Публикацию событий о деградации или отказе соединения
- Предоставление статистики для диагностики

Note:
    Этот компонент готов к интеграции с EventBus, когда он будет добавлен в проект.
    Сейчас предоставляет API для получения статуса здоровья.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from codelab.client.infrastructure.services.background_receive_loop import (
        BackgroundReceiveLoop,
    )


class ConnectionHealthMonitor:
    """Мониторинг здоровья соединения через BackgroundReceiveLoop.

    Периодически проверяет состояние receive loop и предоставляет
    информацию о проблемах:
    - Деградация: loop работает, но были рестарты
    - Отказ: loop полностью остановился

    Архитектура:
    1. Запускается как фоновая задача при подключении
    2. Каждые N секунд проверяет статистику BackgroundReceiveLoop
    3. Предоставляет API для получения статуса здоровья
    4. Логирует проблемы для диагностики
    """

    # Интервал проверки состояния (секунды)
    CHECK_INTERVAL_SECONDS = 5.0

    # Пороги для обнаружения проблем
    DEGRADATION_THRESHOLD_RESTARTS = 1  # Минимальное количество рестартов для degraded
    FAILURE_THRESHOLD_CONSECUTIVE_ERRORS = 5  # Максимум последовательных ошибок

    def __init__(
        self,
        receive_loop: BackgroundReceiveLoop,
        session_id: str,
    ) -> None:
        """Инициализирует монитор здоровья.

        Args:
            receive_loop: BackgroundReceiveLoop для мониторинга
            session_id: ID текущей сессии
        """
        self._receive_loop = receive_loop
        self._session_id = session_id
        self._logger = structlog.get_logger("connection_health_monitor")

        # Фоновая задача мониторинга
        self._task: asyncio.Task[None] | None = None

        # Флаг для graceful shutdown
        self._should_stop = False

        # Отслеживание состояния
        self._degradation_detected = False
        self._failure_detected = False

    async def start(self) -> None:
        """Запускает фоновый мониторинг здоровья."""
        if self._task is not None and not self._task.done():
            self._logger.warning("health_monitor_already_running")
            return

        self._should_stop = False
        self._task = asyncio.create_task(self._monitoring_loop())
        self._logger.info(
            "connection_health_monitor_started",
            session_id=self._session_id,
            check_interval=self.CHECK_INTERVAL_SECONDS,
        )

    async def stop(self) -> None:
        """Останавливает фоновый мониторинг."""
        if self._task is None or self._task.done():
            self._logger.debug("health_monitor_not_running")
            return

        self._logger.info("stopping_connection_health_monitor")
        self._should_stop = True

        try:
            await asyncio.wait_for(self._task, timeout=5.0)
            self._logger.info("connection_health_monitor_stopped")
        except TimeoutError:
            self._logger.warning("health_monitor_timeout_cancelling")
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                self._logger.info("health_monitor_task_cancelled")

    async def _monitoring_loop(self) -> None:
        """Основной цикл мониторинга состояния."""
        self._logger.info("monitoring_loop_starting")

        try:
            while not self._should_stop:
                try:
                    await self._check_health()
                    await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)
                except asyncio.CancelledError:
                    self._logger.info("monitoring_loop_cancelled")
                    break
                except Exception as e:
                    self._logger.error(
                        "monitoring_loop_error",
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    # Продолжаем мониторинг даже при ошибке
                    await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

        finally:
            self._logger.info("monitoring_loop_stopped")

    async def _check_health(self) -> None:
        """Проверяет состояние receive loop и логирует проблемы."""
        stats = self._receive_loop.get_stats()

        is_running = stats.get("running", False)
        restarts_count = stats.get("restarts_count", 0)
        consecutive_errors = stats.get("consecutive_errors", 0)

        # Проверка на деградацию (были рестарты, но loop работает)
        if (
            is_running
            and restarts_count >= self.DEGRADATION_THRESHOLD_RESTARTS
            and not self._degradation_detected
        ):
            self._degradation_detected = True
            self._logger.warning(
                "receive_loop_degraded",
                session_id=self._session_id,
                restarts_count=restarts_count,
                consecutive_errors=consecutive_errors,
                message="Receive loop experienced restarts but is still running",
            )

        # Проверка на полный отказ (превышен лимит ошибок)
        if (
            not is_running
            and consecutive_errors >= self.FAILURE_THRESHOLD_CONSECUTIVE_ERRORS
            and not self._failure_detected
        ):
            self._failure_detected = True
            self._logger.error(
                "receive_loop_failed",
                session_id=self._session_id,
                restarts_count=restarts_count,
                consecutive_errors=consecutive_errors,
                message="Receive loop stopped after exceeding max retries",
                suggestion="Перезапустите подключение или проверьте соединение с сервером",
            )

    def get_health_status(self) -> dict[str, Any]:
        """Получить текущий статус здоровья соединения.

        Returns:
            Словарь с информацией о состоянии соединения
        """
        stats = self._receive_loop.get_stats()

        return {
            "session_id": self._session_id,
            "is_running": stats.get("running", False),
            "restarts_count": stats.get("restarts_count", 0),
            "consecutive_errors": stats.get("consecutive_errors", 0),
            "total_errors": stats.get("errors_count", 0),
            "messages_received": stats.get("messages_received", 0),
            "messages_routed": stats.get("messages_routed", 0),
            "degradation_detected": self._degradation_detected,
            "failure_detected": self._failure_detected,
        }

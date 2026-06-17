"""Очередь операций навигации с поддержкой приоритетов."""

import asyncio
import heapq
import threading
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from .operations import NavigationOperation

logger = structlog.get_logger(__name__)


class OperationQueueError(Exception):
    """Ошибка в очереди операций."""

    pass


class OperationQueue:
    """Очередь операций навигации с последовательным выполнением.

    Операции выполняются в порядке приоритета (FIFO внутри одного приоритета).
    Более высокий приоритет выполняется раньше.
    """

    def __init__(self) -> None:
        """Инициализировать очередь операций."""
        # Приоритетная очередь на основе heapq
        self._queue: list[tuple[int, int, NavigationOperation]] = []
        # Порядковый номер для стабильной сортировки (FIFO в рамках приоритета)
        self._counter: int = 0
        # Блокировка для thread-safety (используем threading.Lock для синхронного clear())
        self._thread_lock = threading.Lock()
        # Блокировка async для обработки операций
        self._async_lock = asyncio.Lock()
        # Функция для выполнения операций
        self._executor: Callable[[NavigationOperation], Awaitable[Any]] | None = None
        # Флаг для отслеживания выполнения
        self._executing = False
        # Событие для сигнала о наличии новой операции
        self._new_operation_event = asyncio.Event()

    def set_executor(
        self,
        executor: Callable[[NavigationOperation], Awaitable[Any]],
    ) -> None:
        """Установить функцию для выполнения операций.

        Args:
            executor: Async функция, которая выполняет операцию
        """
        self._executor = executor

    async def enqueue(self, operation: NavigationOperation) -> Any:
        """Добавить операцию в очередь и ждать её выполнения.

        Операции выполняются последовательно в порядке приоритета.
        Если executor не установлен, операция просто добавляется в очередь.

        Args:
            operation: Операция для добавления

        Returns:
            Результат выполнения операции

        Raises:
            OperationQueueError: Если произошла ошибка при выполнении
        """
        async with self._async_lock:
            # Добавить операцию в приоритетную очередь
            # Используем отрицательный приоритет для сортировки по убыванию
            heapq.heappush(
                self._queue,
                (-operation.priority, self._counter, operation),
            )
            self._counter += 1

            queue_depth = len(self._queue)
            logger.debug(
                "navigation_operation_enqueued",
                operation_type=operation.operation_type.value,
                priority=operation.priority,
                queue_depth=queue_depth,
                metadata=operation.metadata,
            )

            # Сигнализировать о наличии новой операции
            self._new_operation_event.set()

        # Попытаться выполнить очередь
        if self._executor:
            return await self._process_queue()

        return None

    async def _process_queue(self) -> Any:
        """Обработать все операции в очереди.

        Операции выполняются последовательно в порядке приоритета.
        """
        result = None

        while True:
            async with self._async_lock:
                # Проверить, есть ли операции в очереди
                if not self._queue:
                    self._new_operation_event.clear()
                    break

                # Получить операцию с самым высоким приоритетом
                _, _, operation = heapq.heappop(self._queue)

            # Выполнить операцию вне lock-а чтобы не блокировать добавление
            try:
                if self._executor is None:
                    raise OperationQueueError("Executor not set")
                result = await asyncio.wait_for(
                    self._executor(operation),
                    timeout=operation.timeout_seconds,
                )

                logger.debug(
                    "navigation_operation_executed",
                    operation_type=operation.operation_type.value,
                    priority=operation.priority,
                )

                # Вызвать callback успеха если установлен
                if operation.on_success:
                    operation.on_success()

            except TimeoutError as e:
                error_msg = f"Operation timeout: {operation.operation_type.value}"
                logger.warning(
                    "navigation_operation_timeout",
                    operation_type=operation.operation_type.value,
                    timeout_seconds=operation.timeout_seconds,
                )
                # Вызвать callback ошибки если установлен
                if operation.on_error:
                    operation.on_error(e)
                raise OperationQueueError(error_msg) from e

            except Exception as e:
                logger.warning(
                    "navigation_operation_failed",
                    operation_type=operation.operation_type.value,
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
                # Вызвать callback ошибки если установлен
                if operation.on_error:
                    operation.on_error(e)
                raise OperationQueueError(f"Operation failed: {e}") from e

        return result

    def clear(self) -> None:
        """Очистить очередь (отменить все ожидающие операции)."""
        with self._thread_lock:
            self._queue.clear()
            self._counter = 0
            logger.debug("navigation_queue_cleared")

    def size(self) -> int:
        """Получить количество ожидающих операций."""
        return len(self._queue)

    def is_empty(self) -> bool:
        """Проверить, пуста ли очередь."""
        return len(self._queue) == 0

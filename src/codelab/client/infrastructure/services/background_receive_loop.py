"""BackgroundReceiveLoop - фоновая задача приёма сообщений с маршрутизацией.

Решает race condition при конкурентном доступе к WebSocket.receive():
- Единственный вызов receive() на WebSocket (в background loop)
- Распределение сообщений по очередям на основе маршрутизации
- Обработка lifecycle (start, stop, error handling)
- Auto-restart при сбоях с экспоненциальным backoff
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from codelab.client.infrastructure.services.message_router import MessageRouter
from codelab.client.infrastructure.services.routing_queues import RoutingQueues
from codelab.client.infrastructure.transport import WebSocketTransport


class BackgroundReceiveLoop:
    """Фоновая задача для единственного вызова receive() на WebSocket.

    Архитектура:
    1. Запускается как asyncio.Task при подключении
    2. Непрерывно получает сообщения: message = await transport.receive()
    3. Маршрутизирует сообщение в нужную очередь:
       - response[id] → для RPC ответов
       - notification → для асинхронных уведомлений
       - permission → для запросов разрешения
    4. Обрабатывает ошибки и graceful shutdown
    5. Автоматически перезапускается при сбоях с экспоненциальным backoff

    Ключевое преимущество:
    - Все конкурентные запросы (request_with_callbacks) получают из очередей
    - Не вызывают receive() напрямую, избегая RuntimeError
    - Истинная конкурентность вместо блокировок
    - Auto-restart обеспечивает устойчивость к временным сбоям
    """

    # Константы для auto-restart
    MAX_CONSECUTIVE_RETRIES = 5
    INITIAL_BACKOFF_SECONDS = 1.0
    MAX_BACKOFF_SECONDS = 30.0
    BACKOFF_MULTIPLIER = 2.0

    def __init__(
        self,
        transport: WebSocketTransport,
        router: MessageRouter,
        queues: RoutingQueues,
    ) -> None:
        """Инициализирует background loop.

        Args:
            transport: WebSocket транспорт для receive()
            router: MessageRouter для маршрутизации сообщений
            queues: RoutingQueues для хранения сообщений
        """
        self._transport = transport
        self._router = router
        self._queues = queues
        self._logger = structlog.get_logger("background_receive_loop")

        # Текущая фоновая задача
        self._task: asyncio.Task[None] | None = None

        # Флаг для graceful shutdown
        self._should_stop = False

        # Счетчики для диагностики
        self._messages_received = 0
        self._messages_routed = 0
        self._errors_count = 0
        self._restarts_count = 0
        self._consecutive_errors = 0

    async def start(self) -> None:
        """Запускает фоновый loop приёма сообщений.

        Создает asyncio.Task, которая работает в фоне.
        Можно вызвать несколько раз - будет игнорировано если уже запущена.

        Raises:
            RuntimeError: Если loop уже запущена
        """
        if self._task is not None and not self._task.done():
            self._logger.warning("background_loop_already_running")
            return

        self._should_stop = False
        self._task = asyncio.create_task(self._receive_loop_with_restart())
        self._logger.info(
            "background_receive_loop_started",
            task_id=id(self._task),
        )

    async def stop(self) -> None:
        """Останавливает фоновый loop и дожидается его завершения.

        Graceful shutdown:
        1. Устанавливает флаг _should_stop = True
        2. Дожидается завершения задачи с таймаутом (5 сек)
        3. Если таймаут истек, отменяет задачу
        4. Логирует результат

        Note:
            Безопасно вызвать несколько раз
        """
        if self._task is None or self._task.done():
            self._logger.debug("background_loop_not_running")
            return

        self._logger.info(
            "stopping_background_receive_loop",
            task_id=id(self._task),
        )

        # Сигнализируем loop'у остановиться
        self._should_stop = True

        try:
            # Даем loop время на graceful завершение
            await asyncio.wait_for(self._task, timeout=5.0)
            self._logger.info(
                "background_receive_loop_stopped_gracefully",
                messages_received=self._messages_received,
                messages_routed=self._messages_routed,
                restarts_count=self._restarts_count,
            )
        except TimeoutError:
            # Если не завершилась, отменяем
            self._logger.warning(
                "background_receive_loop_timeout_cancelling_task"
            )
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                self._logger.info("background_receive_loop_task_cancelled")

    async def _receive_loop_with_restart(self) -> None:
        """Основной цикл с auto-restart при сбоях.

        Оборачивает _receive_loop и перезапускает его при ошибках
        с экспоненциальным backoff до достижения лимита попыток.
        """
        self._logger.info("receive_loop_with_restart_starting")

        while not self._should_stop:
            try:
                # Запускаем основной цикл
                await self._receive_loop()

                # Если _receive_loop завершился без ошибки - выходим
                break

            except asyncio.CancelledError:
                self._logger.info("receive_loop_cancelled")
                break

            except Exception as e:
                # Произошла ошибка - пытаемся перезапуститься
                self._consecutive_errors += 1
                self._restarts_count += 1

                if self._consecutive_errors > self.MAX_CONSECUTIVE_RETRIES:
                    self._logger.error(
                        "receive_loop_max_retries_exceeded",
                        consecutive_errors=self._consecutive_errors,
                        max_retries=self.MAX_CONSECUTIVE_RETRIES,
                    )
                    break

                # Вычисляем backoff с экспоненциальным ростом
                backoff = min(
                    self.INITIAL_BACKOFF_SECONDS
                    * (self.BACKOFF_MULTIPLIER ** (self._consecutive_errors - 1)),
                    self.MAX_BACKOFF_SECONDS,
                )

                self._logger.warning(
                    "receive_loop_restarting",
                    error=str(e),
                    error_type=type(e).__name__,
                    retry_attempt=self._consecutive_errors,
                    max_retries=self.MAX_CONSECUTIVE_RETRIES,
                    backoff_seconds=backoff,
                )

                # Уведомляем очереди о временной недоступности
                await self._queues.broadcast_connection_error(
                    ConnectionError(f"Receive loop error: {e}")
                )

                # Ждём backoff перед перезапуском
                try:
                    await asyncio.sleep(backoff)
                except asyncio.CancelledError:
                    self._logger.info("receive_loop_cancelled_during_backoff")
                    break

        self._logger.info(
            "receive_loop_with_restart_stopped",
            messages_received=self._messages_received,
            messages_routed=self._messages_routed,
            restarts_count=self._restarts_count,
            consecutive_errors=self._consecutive_errors,
        )

    async def _receive_loop(self) -> None:
        """Основной цикл приёма сообщений.

        КРИТИЧНО: Это единственное место, где вызывается transport.receive_text()

        Цикл:
        1. while not self._should_stop:
        2.   json_message = await self._transport.receive_text()
        3.   message = json.loads(json_message)
        4.   routing_key = self._router.route(message)
        5.   Положить сообщение в нужную очередь
        6. Обработка ошибок и graceful shutdown

        Raises:
            Exception: При критической ошибке (для перезапуска в _receive_loop_with_restart)
        """
        self._logger.info("receive_loop_starting")

        try:
            while not self._should_stop:
                try:
                    # Получаем сообщение из WebSocket
                    # КРИТИЧНО: Это единственный receive_text() на всё соединение!
                    json_message = await self._transport.receive_text()
                    message = json.loads(json_message)
                    self._messages_received += 1

                    # Успешное получение - сбрасываем счётчик ошибок
                    if self._consecutive_errors > 0:
                        self._logger.info(
                            "receive_loop_recovered",
                            previous_errors=self._consecutive_errors,
                        )
                        self._consecutive_errors = 0

                    self._logger.debug(
                        "message_received",
                        message_has_id=("id" in message),
                        message_has_method=("method" in message),
                        messages_total=self._messages_received,
                    )

                    # Определяем маршрут сообщения
                    routing_key = self._router.route(message)

                    # Распределяем по очередям в зависимости от маршрута
                    if routing_key.queue_type == "response":
                        # RPC ответ на конкретный запрос
                        request_id = routing_key.request_id
                        if request_id is not None:
                            await self._queues.put_response(request_id, message)
                            self._messages_routed += 1
                        else:
                            self._logger.error(
                                "response_routing_missing_request_id"
                            )

                    elif routing_key.queue_type == "notification":
                        # Асинхронное уведомление
                        await self._queues.put_notification(message)
                        self._messages_routed += 1

                    elif routing_key.queue_type == "permission":
                        # Запрос разрешения
                        await self._queues.put_permission_request(message)
                        self._messages_routed += 1

                    else:
                        # Неизвестный тип - логируем и игнорируем
                        self._logger.warning(
                            "unknown_message_type_skipped",
                            message_keys=list(message.keys()),
                        )

                except asyncio.CancelledError:
                    self._logger.info("receive_loop_cancelled")
                    raise

                except ConnectionError as e:
                    # Соединение потеряно - пробрасываем для перезапуска
                    self._errors_count += 1
                    self._logger.warning(
                        "connection_lost_in_receive_loop",
                        error=str(e),
                        errors_count=self._errors_count,
                    )
                    raise

                except Exception as e:
                    # Другая ошибка - пробрасываем для перезапуска
                    self._errors_count += 1
                    self._logger.error(
                        "receive_loop_error",
                        error=str(e),
                        error_type=type(e).__name__,
                        errors_count=self._errors_count,
                    )
                    raise

        finally:
            # Graceful cleanup
            self._logger.info(
                "receive_loop_stopped",
                messages_received=self._messages_received,
                messages_routed=self._messages_routed,
                errors_count=self._errors_count,
            )

    def is_running(self) -> bool:
        """Проверить, работает ли background loop.

        Returns:
            True если задача создана и еще работает
        """
        return self._task is not None and not self._task.done()

    def get_stats(self) -> dict[str, Any]:
        """Получить статистику работы loop'а.

        Returns:
            Словарь со статистикой (сообщения, ошибки, рестарты и т.д.)
        """
        return {
            "running": self.is_running(),
            "messages_received": self._messages_received,
            "messages_routed": self._messages_routed,
            "errors_count": self._errors_count,
            "restarts_count": self._restarts_count,
            "consecutive_errors": self._consecutive_errors,
        }

"""RequestCallbackCoordinator - оркестрация request/response с асинхронными событиями.

Инкапсулирует сложный жизненный цикл одного `request_with_callbacks`:
- отправка запроса и ожидание финального ответа из per-request очереди;
- параллельная обработка session/update, permission-запросов и входящих
  server->client RPC (fs/*, terminal/*) во время ожидания;
- аккуратная отмена «осиротевших» permission-задач и вычитывание оставшихся
  уведомлений после финального ответа.

Компонент не владеет транспортом и очередями: он читает актуальные очереди и
диспетчер через провайдеры, а ответы отправляет через инъектированный `send`.
Это позволяет транспорту пересоздавать очереди при реконнекте, не пересоздавая
координатор.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import structlog

from codelab.client.messages import ACPMessage

if TYPE_CHECKING:
    from codelab.client.infrastructure.services.acp_transport.client_rpc_dispatcher import (
        ClientRpcDispatcher,
    )
    from codelab.client.infrastructure.services.acp_transport.permission_responder import (
        PermissionResponder,
    )
    from codelab.client.infrastructure.services.routing_queues import RoutingQueues

SendFn = Callable[[dict[str, Any]], Awaitable[None]]
UpdateCallback = Callable[[dict[str, Any]], None]


class RequestCallbackCoordinator:
    """Оркеструет один request_with_callbacks поверх routing queues.

    Все конкурентные запросы сериализуются глобальным `request_lock`, чтобы не
    конкурировать за общую notification_queue и не терять session/update.
    """

    def __init__(
        self,
        *,
        queues_provider: Callable[[], RoutingQueues | None],
        dispatcher_provider: Callable[[], ClientRpcDispatcher | None],
        send: SendFn,
        permission_responder: PermissionResponder,
        request_lock: asyncio.Lock,
    ) -> None:
        """Инициализирует координатор.

        Аргументы:
            queues_provider: Возвращает актуальные RoutingQueues (или None до connect).
            dispatcher_provider: Возвращает актуальный ClientRpcDispatcher (или None).
            send: Callable для отправки JSON-RPC сообщения серверу.
            permission_responder: Компонент обработки session/request_permission.
            request_lock: Глобальная блокировка сериализации запросов.
        """
        self._queues_provider = queues_provider
        self._dispatcher_provider = dispatcher_provider
        self._send = send
        self._permission_responder = permission_responder
        self._request_lock = request_lock
        self._logger = structlog.get_logger("request_callback_coordinator")

    async def execute(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        on_update: UpdateCallback | None = None,
    ) -> dict[str, Any]:
        """Выполняет request с обработкой callbacks используя routing queues.

        Архитектура:
        1. Создаёт очередь для этого request_id.
        2. Отправляет request.
        3. Ждёт ответа из очереди для этого request_id.
        4. Обрабатывает асинхронные события (updates, permissions, client RPC).

        Входящие server->client RPC (fs/*, terminal/*) обрабатываются через
        ClientRpcDispatcher; permission — через PermissionResponder.

        Возвращает:
            Финальный ответ на request.
        """
        queues = self._queues_provider()
        if queues is None:
            msg = "Routing queues not initialized"
            self._logger.error("queues_not_initialized")
            raise RuntimeError(msg)

        async with self._request_lock:
            # Слушаем incoming server->client RPC всегда: даже без пользовательских
            # callbacks нужно отправить корректный response, иначе сервер зависнет
            # в ожидании и финальный ответ на запрос не придет.
            should_listen_notifications = True
            self._logger.info(
                "request_with_callbacks_start",
                method=method,
                has_callbacks=should_listen_notifications,
            )

            request: ACPMessage | None = None
            request_id: str | int | None = None
            try:
                # Создаем JSON-RPC запрос
                request = ACPMessage.request(method=method, params=params)
                if not isinstance(request.id, str | int):
                    raise RuntimeError("Generated request without valid id")
                request_id = request.id
                request_data = request.to_dict()

                # Создаем очередь для этого request_id.
                # Background loop будет класть ответы в эту очередь.
                response_queue = await queues.get_or_create_response_queue(request_id)

                # Отправляем запрос (через send с защитой переподключения).
                await self._send(request_data)

                self._logger.debug(
                    "request_sent",
                    method=method,
                    request_id=request_id,
                )

                # Создаём долгоживущие tasks ВНЕ цикла
                response_task: asyncio.Task[dict[str, Any]] = asyncio.create_task(
                    response_queue.get()
                )
                permission_task: asyncio.Task[dict[str, Any]] | None = None
                if should_listen_notifications:
                    permission_task = self._create_permission_task(queues)

                try:
                    return await self._wait_for_response_with_events(
                        response_task,
                        permission_task,
                        method=method,
                        request_id=request_id,
                        on_update=on_update,
                        queues=queues,
                    )
                finally:
                    # Очистка долгоживущих tasks при выходе из цикла
                    if not response_task.done():
                        response_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await response_task
                    if permission_task is not None and not permission_task.done():
                        permission_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await permission_task

            except Exception as e:
                self._logger.error(
                    "request_failed",
                    method=method,
                    request_id=request_id,
                    error=str(e),
                )
                raise
            finally:
                # Очищаем очередь ответов после использования.
                if request_id is not None:
                    await queues.cleanup_response_queue(request_id)

    def _create_permission_task(self, queues: RoutingQueues) -> asyncio.Task[dict[str, Any]]:
        """Создаёт новый permission task для ожидания permission request.

        Используется для гарантии что новый task создаётся сразу после обработки
        предыдущего permission request, минимизируя race conditions.
        """
        task = asyncio.create_task(queues.permission_queue.get())
        self._logger.info("permission_task_created")
        return task

    async def _wait_for_response_with_events(
        self,
        response_task: asyncio.Task[dict[str, Any]],
        permission_task: asyncio.Task[dict[str, Any]] | None,
        *,
        method: str,
        request_id: str | int,
        on_update: UpdateCallback | None,
        queues: RoutingQueues,
    ) -> dict[str, Any]:
        """Основной цикл ожидания ответа с обработкой permission и notifications."""
        self._logger.info(
            "wait_for_response_with_events_start",
            method=method,
            request_id=request_id,
            has_permission_task=permission_task is not None,
        )
        try:
            while True:
                notification_task: asyncio.Task[dict[str, Any]] | None = asyncio.create_task(
                    asyncio.wait_for(
                        queues.notification_queue.get(),
                        timeout=0.1,
                    )
                )

                tasks_to_wait: list[asyncio.Task[dict[str, Any]]] = [
                    response_task,
                    notification_task,
                ]
                if permission_task is not None:
                    tasks_to_wait.append(permission_task)

                done, pending = await asyncio.wait(
                    tasks_to_wait,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if notification_task in pending:
                    notification_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                        await notification_task
                elif notification_task in done:
                    with contextlib.suppress(TimeoutError, Exception):
                        notification_task.result()

                if permission_task is not None and permission_task in done:
                    self._logger.info(
                        "permission_task_completed_in_wait_loop",
                        method=method,
                        request_id=request_id,
                    )
                    self._handle_permission_task(
                        permission_task,
                        method=method,
                        request_id=request_id,
                    )
                    # Сразу создаём новый permission task для ожидания следующего request.
                    # Это критично для предотвращения race condition: если второй permission
                    # request придёт в очередь до создания нового task, он может быть потерян.
                    permission_task = self._create_permission_task(queues)
                    self._logger.info(
                        "new_permission_task_created_after_handling",
                        method=method,
                        request_id=request_id,
                    )

                if notification_task in done:
                    await self._handle_notification_task(
                        notification_task,
                        method=method,
                        request_id=request_id,
                        on_update=on_update,
                    )

                if response_task in done:
                    # Отменяем permission_task перед возвратом чтобы предотвратить
                    # появление осиротевших tasks, которые потребляют сообщения из
                    # permission_queue и мешают обработке следующих permission requests.
                    if permission_task is not None and not permission_task.done():
                        self._logger.info(
                            "cancelling_orphaned_permission_task",
                            method=method,
                            request_id=request_id,
                        )
                        permission_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await permission_task
                    return await self._process_response(
                        response_task,
                        method=method,
                        request_id=request_id,
                        on_update=on_update,
                        queues=queues,
                    )
        except Exception:
            # При любом исключении отменяем permission_task чтобы не оставить
            # осиротевший task, потребляющий сообщения из permission_queue.
            if permission_task is not None and not permission_task.done():
                self._logger.warning(
                    "cancelling_permission_task_on_error",
                    method=method,
                    request_id=request_id,
                )
                permission_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await permission_task
            raise

    def _handle_permission_task(
        self,
        permission_task: asyncio.Task[dict[str, Any]],
        *,
        method: str,
        request_id: str | int,
    ) -> None:
        """Обрабатывает завершённый permission task (синхронная часть)."""
        self._logger.info(
            "handle_permission_task_called",
            method=method,
            request_id=request_id,
            task_done=permission_task.done(),
            task_cancelled=permission_task.cancelled(),
        )
        try:
            permission_data = permission_task.result()
            self._logger.info(
                "tool_lifecycle_permission_request_received",
                method=method,
                request_id=request_id,
                permission_id=permission_data.get("id"),
                permission_method=permission_data.get("method"),
            )
        except Exception as e:
            self._logger.warning(
                "tool_lifecycle_permission_request_failed",
                method=method,
                request_id=request_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return

        # Запускаем async обработку отдельно чтобы не блокировать
        self._logger.info(
            "permission_task_async_handling_started",
            method=method,
            request_id=request_id,
            permission_id=permission_data.get("id"),
        )
        asyncio.ensure_future(self._permission_responder.handle(permission_data))

    async def _handle_notification_task(
        self,
        notification_task: asyncio.Task[dict[str, Any]],
        *,
        method: str,
        request_id: str | int,
        on_update: UpdateCallback | None,
    ) -> None:
        """Обрабатывает завершённый notification task."""
        try:
            notification_data = notification_task.result()
            self._logger.debug(
                "tool_lifecycle_notification_received",
                method=method,
                request_id=request_id,
                notification_id=notification_data.get("id"),
                notification_method=notification_data.get("method"),
            )
            await self._handle_notification_or_client_rpc(
                method=method,
                request_id=request_id,
                notification_data=notification_data,
                on_update=on_update,
            )
        except TimeoutError:
            pass
        except Exception as e:
            self._logger.warning(
                "tool_lifecycle_notification_failed",
                method=method,
                request_id=request_id,
                error=str(e),
            )

    async def _handle_notification_or_client_rpc(
        self,
        *,
        method: str,
        request_id: str | int,
        notification_data: dict[str, Any],
        on_update: UpdateCallback | None,
    ) -> None:
        """Обрабатывает `session/update` и incoming RPC (`fs/*`, `terminal/*`)."""
        notification = ACPMessage.from_dict(notification_data)

        if notification.method == "session/update":
            await self._handle_session_update(
                notification_data,
                method=method,
                request_id=request_id,
                on_update=on_update,
            )
            return

        rpc_method = notification.method
        if rpc_method is None or notification.id is None:
            return

        rpc_id: str | int = notification.id
        rpc_params = notification.params if isinstance(notification.params, dict) else {}
        self._logger.debug(
            "tool_lifecycle_rpc_received",
            request_id=request_id,
            method=method,
            rpc_id=rpc_id,
            rpc_method=rpc_method,
        )

        dispatcher = self._dispatcher_provider()
        if dispatcher is None:
            # Диспетчер всегда инжектится в проде; ветка защищает горячий путь
            # (пустой ответ вместо зависания сервера) в тестовых/дефолтных сборках.
            await self._handle_unknown_rpc(rpc_id)
            return

        result = await dispatcher.dispatch(rpc_method, rpc_id, rpc_params)
        if "error" in result:
            error_info = result["error"]
            await self._send(
                ACPMessage.error_response(
                    rpc_id,
                    code=error_info.get("code", -32603),
                    message=error_info.get("message", "Unknown error"),
                ).to_dict()
            )
        else:
            await self._send(ACPMessage.response(rpc_id, result).to_dict())

    async def _handle_session_update(
        self,
        notification_data: dict[str, Any],
        *,
        method: str,
        request_id: str | int,
        on_update: UpdateCallback | None,
    ) -> None:
        if on_update is not None:
            self._logger.debug(
                "handling_session_update",
                method=method,
                request_id=request_id,
                has_callback=on_update is not None,
            )
            on_update(notification_data)
        else:
            self._logger.warning(
                "session_update_received_but_no_callback",
                method=method,
                request_id=request_id,
            )

    async def _handle_unknown_rpc(self, rpc_id: str | int) -> None:
        """Отправляет пустой response на неизвестный RPC."""
        await self._send(ACPMessage.response(rpc_id, {}).to_dict())

    async def _drain_remaining_notifications(
        self,
        *,
        method: str,
        request_id: str | int,
        on_update: UpdateCallback | None,
        queues: RoutingQueues,
    ) -> int:
        """Забирает оставшиеся уведомления после финального ответа."""
        remaining_notifications = 0
        max_remaining_iterations = 10
        for _ in range(max_remaining_iterations):
            try:
                notification_data = await asyncio.wait_for(
                    queues.notification_queue.get(),
                    timeout=0.2,
                )
                notification = ACPMessage.from_dict(notification_data)
                remaining_notifications += 1

                if notification.method == "session/update" and on_update is not None:
                    self._logger.debug(
                        "handling_remaining_session_update",
                        method=method,
                        request_id=request_id,
                        remaining_count=remaining_notifications,
                    )
                    on_update(notification_data)
            except TimeoutError:
                break
            except Exception as e:
                self._logger.warning(
                    "error_processing_remaining_notification",
                    error=str(e),
                )
                break

        if remaining_notifications > 0:
            self._logger.info(
                "processed_remaining_notifications",
                method=method,
                request_id=request_id,
                count=remaining_notifications,
            )

        return remaining_notifications

    async def _process_response(
        self,
        response_task: asyncio.Task[dict[str, Any]],
        *,
        method: str,
        request_id: str | int,
        on_update: UpdateCallback | None,
        queues: RoutingQueues,
    ) -> dict[str, Any]:
        """Обрабатывает финальный ответ и оставшиеся уведомления."""
        response_data = response_task.result()
        if response_data.get("id") != request_id:
            raise RuntimeError(f"Response id mismatch: expected {request_id}")

        if isinstance(response_data.get("error"), dict):
            error_payload = response_data["error"]
            self._logger.error(
                "request_error",
                method=method,
                error_code=error_payload.get("code"),
                error_message=error_payload.get("message"),
            )

        await self._drain_remaining_notifications(
            method=method,
            request_id=request_id,
            on_update=on_update,
            queues=queues,
        )

        self._logger.info(
            "request_completed",
            method=method,
            request_id=request_id,
        )
        return response_data


__all__ = ["RequestCallbackCoordinator"]

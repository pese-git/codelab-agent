"""ACPTransportService - инфраструктурная реализация низкоуровневой коммуникации.

Инкапсулирует транспорт (WebSocket или stdio) и предоставляет interface TransportService
для остальной системы. Обрабатывает:
- Подключение/отключение
- Отправку сообщений
- Получение ответов
- Обработку асинхронных уведомлений

Архитектура:
- Background Receive Loop: единственный вызов receive() на транспорт
- Message Router: маршрутизация по типам сообщений
- Routing Queues: распределение по очередям для конкурентных запросов
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, Any

import structlog

from codelab.client.domain import TransportService
from codelab.client.infrastructure.message_parser import MessageParser
from codelab.client.infrastructure.services.background_receive_loop import (
    BackgroundReceiveLoop,
)
from codelab.client.infrastructure.services.message_router import MessageRouter
from codelab.client.infrastructure.services.routing_queues import RoutingQueues
from codelab.client.infrastructure.transport import Transport, WebSocketTransport
from codelab.client.messages import ACPMessage, RequestPermissionRequest

if TYPE_CHECKING:
    from codelab.client.application.permission_handler import PermissionHandler
    from codelab.client.infrastructure.services.acp_transport.client_rpc_dispatcher import (
        ClientRpcDispatcher,
    )


async def _call_callback(
    callback: Callable[..., Any] | None,
    *args: Any,
) -> Any:
    """Вызвать callback, поддерживая sync и async функции.

    В stdio режиме callbacks НЕ должны блокировать event loop.
    Если callback — coroutine function, он будет awaited.
    """
    if callback is None:
        return None
    if inspect.iscoroutinefunction(callback):
        return await callback(*args)
    return callback(*args)


class ACPTransportService(TransportService):
    """Реализация низкоуровневой коммуникации с ACP сервером.

    Оборачивает транспорт (WebSocket или stdio) и предоставляет чистый interface
    для отправки/получения сообщений. Используется Application слоем
    через Use Cases.

    Поддерживает async context manager для правильного управления жизненным циклом:
        async with ACPTransportService(transport) as service:
            await service.connect()
            await service.send(message)
    """

    def __init__(
        self,
        transport: Transport,
        parser: MessageParser | None = None,
        permission_handler: PermissionHandler | None = None,
        rpc_dispatcher: ClientRpcDispatcher | None = None,
    ) -> None:
        """Инициализирует сервис.

        Аргументы:
            transport: Реализация транспорта (WebSocket или stdio).
            parser: MessageParser для парсинга ответов (опционально).
            permission_handler: PermissionHandler для обработки permission requests (опционально).
            rpc_dispatcher: ClientRpcDispatcher для обработки входящих RPC (опционально).
        """
        self._transport = transport
        self.parser = parser or MessageParser()
        self._permission_handler = permission_handler
        self._rpc_dispatcher = rpc_dispatcher
        # Callback для отображения permission modal в UI
        # Будет установлен через set_permission_callback из TUI App
        # Сигнатура: (request_id, tool_call, options, on_choice) -> None
        # Типизация:
        # Callable[[request_id, tool_call, options, on_choice], None] | None
        self._permission_callback: (
            Callable[
                [str | int, Any, list[Any], Callable[[str | int, str], None]], None
            ]
            | None
        ) = None
        # Сохраняем server capabilities после инициализации
        self._server_capabilities: dict[str, Any] | None = None

        # Infrastructure для управления конкурентными вызовами receive()
        # Background Receive Loop: единственный вызов receive() на WebSocket
        self._background_loop: BackgroundReceiveLoop | None = None
        # Message Router: маршрутизация по типам сообщений
        self._router: MessageRouter | None = None
        # Routing Queues: распределение по очередям
        self._queues: RoutingQueues | None = None
        # Глобальная блокировка для request_with_callbacks.
        # Нужна, чтобы разные callback-запросы не конкурировали за
        # общую notification_queue и не теряли session/update события.
        self._callbacks_request_lock = asyncio.Lock()

        self._logger = structlog.get_logger("acp_transport_service")

    async def __aenter__(self) -> ACPTransportService:
        """Входит в контекст manager для управления жизненным циклом.

        Возвращает:
            Текущий экземпляр ACPTransportService (self)
        """
        self._logger.debug("service_context_entering")
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Выходит из контекста manager и закрывает соединение.

        Гарантирует очистку ресурсов при выходе из контекста,
        даже если произошло исключение.

        Args:
            exc_type: Тип исключения (если оно возникло)
            exc_val: Значение исключения
            exc_tb: Traceback исключения
        """
        self._logger.debug("service_context_exiting")
        try:
            await self.disconnect()
        except Exception as e:
            self._logger.warning("error_in_context_exit", error=str(e))

    async def connect(self) -> None:
        """Устанавливает соединение с сервером и запускает background receive loop.

        Открывает соединение через переданный транспорт.
        Инициализирует routing infrastructure и запускает background loop.

        Raises:
            RuntimeError: При ошибке подключения
        """
        if self.is_connected():
            self._logger.debug("already_connected")
            return

        try:
            # Входим в context manager для открытия соединения
            await self._transport.__aenter__()

            # Инициализируем routing infrastructure
            self._router = MessageRouter()
            self._queues = RoutingQueues()
            self._background_loop = BackgroundReceiveLoop(
                self._transport,
                self._router,
                self._queues,
            )

            # Запускаем background loop
            await self._background_loop.start()

            self._logger.info(
                "connected_to_server",
                transport_type=type(self._transport).__name__,
                background_loop_running=self._background_loop.is_running(),
            )
        except Exception as e:
            # При ошибке очищаем ресурсы
            self._background_loop = None
            self._queues = None
            self._router = None
            self._logger.error("connection_failed", error=str(e))
            msg = f"Failed to connect: {e}"
            raise RuntimeError(msg) from e

    async def disconnect(self) -> None:
        """Разрывает соединение с сервером.

        Graceful shutdown:
        1. Останавливает background receive loop
        2. Очищает routing infrastructure
        3. Закрывает транспорт
        4. Освобождает все ресурсы
        """
        if not self.is_connected():
            self._logger.debug("not_connected")
            return

        try:
            self._logger.debug("closing_connection")

            # Сначала останавливаем background loop - это главное
            # Иначе он будет пытаться читать из закрытого транспорта
            if self._background_loop is not None:
                self._logger.debug("stopping_background_loop")
                await self._background_loop.stop()

            # Очищаем очереди чтобы разбудить все ждущие операции
            if self._queues is not None:
                await self._queues.clear_all()

            # Потом закрываем транспорт
            # Правильно вызываем __aexit__ для корректного закрытия соединения
            # Это завершает context manager и освобождает все ресурсы
            if self._transport is not None:
                await self._transport.__aexit__(None, None, None)

            self._logger.info("connection_closed")
        except Exception as e:
            self._logger.warning("disconnect_error", error=str(e))
        finally:
            # Окончательная очистка ресурсов
            self._background_loop = None
            self._queues = None
            self._router = None

    async def send(self, message: dict[str, Any]) -> None:
        """Отправляет сообщение на сервер.

        Если соединение потеряно, автоматически переподключается.

        Аргументы:
            message: JSON-RPC сообщение для отправки

        Raises:
            RuntimeError: При ошибке отправки или переподключения
        """
        # Проверяем и восстанавливаем соединение если оно потеряно
        if not self.is_connected():
            self._logger.warning("send_connection_lost_reconnecting")
            try:
                await self.connect()
            except Exception as e:
                msg = f"Failed to reconnect to server: {e}"
                self._logger.error("send_reconnect_failed", error=str(e))
                raise RuntimeError(msg) from e

        message_id = message.get("id")
        # Проверяем тип сообщения для лучшего логирования
        is_response = "result" in message or "error" in message
        message_type = "response" if is_response else "request"
        
        # Для permission response добавляем дополнительный контекст
        extra_context = {}
        if is_response and "result" in message:
            result = message.get("result", {})
            if "outcome" in result:  # Это permission response
                extra_context = {
                    "outcome": result.get("outcome"),
                    "option_id": result.get("optionId"),
                }
        
        self._logger.debug(
            "sending_message",
            message_id=message_id,
            message_type=message_type,
            **extra_context,
        )

        try:
            # Преобразуем сообщение в JSON и отправляем через транспорт
            json_message = json.dumps(message)
            assert self._transport is not None
            await self._transport.send_str(json_message)
            
            # Логируем успешную отправку с дополнительным контекстом
            if extra_context:  # Это permission response
                self._logger.info(
                    "permission_response_sent_via_transport",
                    message_id=message_id,
                    outcome=extra_context.get("outcome"),
                    option_id=extra_context.get("option_id"),
                )
            else:
                self._logger.debug(
                    "message_sent",
                    message_id=message_id,
                    message_type=message_type,
                )
        except Exception as e:
            self._logger.error(
                "send_failed",
                message_id=message_id,
                message_type=message_type,
                error=str(e),
                error_type=type(e).__name__,
            )
            msg = f"Failed to send message: {e}"
            raise RuntimeError(msg) from e

    async def receive(self, request_id: str | int | None = None) -> dict[str, Any]:
        """Получает одно сообщение с сервера из очереди RPC ответов.

        Архитектура:
        - Background loop единственный получает из transport.receive_text()
        - Маршрутизирует в очереди на основе Message Router
        - receive() получает из соответствующей очереди

        Поддерживает две режима:
        1. С request_id: получает RPC ответ на конкретный запрос из response_queues[request_id]
        2. Без request_id: получает асинхронное уведомление из notification_queue

        Использует Message Router и Routing Queues для распределения
        конкурентных запросов на одном WebSocket соединении.

        Аргументы:
            request_id: ID конкретного RPC запроса (опционально)

        Возвращает:
            JSON-RPC сообщение из сервера

        Raises:
            RuntimeError: При ошибке получения или потере соединения
        """
        if not self.is_connected():
            msg = "Not connected to server"
            self._logger.error("not_connected")
            raise RuntimeError(msg)

        if self._queues is None:
            msg = "Routing queues not initialized"
            self._logger.error("queues_not_initialized")
            raise RuntimeError(msg)

        try:
            # Выбираем очередь в зависимости от request_id
            if request_id is not None:
                # Получаем ответ на конкретный RPC запрос
                self._logger.debug("waiting_for_rpc_response", request_id=request_id)
                # Получаем или создаем очередь для этого request_id
                response_queue = await self._queues.get_or_create_response_queue(request_id)
                message = await asyncio.wait_for(
                    response_queue.get(),
                    timeout=300.0,
                )
            else:
                # Получаем асинхронное уведомление
                self._logger.debug("waiting_for_notification")
                message = await asyncio.wait_for(
                    self._queues.notification_queue.get(),
                    timeout=300.0,
                )

            message_id = message.get("id")
            self._logger.debug(
                "message_received_from_queue",
                message_id=message_id,
                request_id=request_id,
                has_result="result" in message,
                has_error="error" in message,
            )
            return message
        except TimeoutError:
            self._logger.error("receive_timeout", request_id=request_id)
            msg = "Timeout waiting for message from server"
            raise RuntimeError(msg) from None
        except Exception as e:
            self._logger.error(
                "receive_failed",
                error=str(e),
                error_type=type(e).__name__,
                request_id=request_id,
            )
            msg = f"Failed to receive message: {e}"
            raise RuntimeError(msg) from e

    def listen(self) -> AsyncIterator[dict[str, Any]]:
        """Слушает входящие сообщения с сервера.

        Возвращает асинхронный итератор, который выдает
        сообщения по мере их поступления с сервера.

        Yields:
            JSON-RPC сообщения из сервера
        """

        async def _message_stream() -> AsyncIterator[dict[str, Any]]:
            if not self.is_connected():
                msg = "Not connected to server"
                self._logger.error("not_connected")
                raise RuntimeError(msg)

            self._logger.info("listening_for_messages")

            try:
                while self.is_connected():
                    try:
                        message = await self.receive()
                        if message:
                            yield message
                    except RuntimeError as e:
                        self._logger.warning("receive_error_in_listen", error=str(e))
                        break
            except Exception as e:
                self._logger.error("listen_error", error=str(e))
                raise
            finally:
                self._logger.info("stopped_listening")

        return _message_stream()

    def is_connected(self) -> bool:
        """Проверяет наличие активного соединения.

        Возвращает:
            True если соединение активно и готово к использованию
        """
        if self._transport is None:
            return False

        connected = self._transport.is_connected()

        if not connected:
            self._logger.debug(
                "transport_connection_lost",
                transport_type=type(self._transport).__name__,
            )

        return connected

    def set_server_capabilities(self, capabilities: dict[str, Any]) -> None:
        """Сохраняет capabilities сервера после инициализации.

        Аргументы:
            capabilities: Словарь с возможностями сервера
        """
        self._server_capabilities = capabilities
        self._logger.info("server_capabilities_saved", capabilities=capabilities)

    def get_server_capabilities(self) -> dict[str, Any]:
        """Возвращает сохраненные capabilities сервера.

        Возвращает:
            Словарь с возможностями сервера

        Raises:
            RuntimeError: Если сервер не инициализирован
        """
        if self._server_capabilities is None:
            msg = "Server not initialized. Call InitializeUseCase first."
            raise RuntimeError(msg)
        return self._server_capabilities

    def set_permission_callback(
        self,
        callback: Callable[[str | int, Any, list[Any], Callable[[str | int, str], None]], None],
    ) -> None:
        """Устанавливает callback для отображения permission modal в UI.

        Callback будет вызван при получении session/request_permission от сервера
        для показа модального окна пользователю с выбором разрешения.

        Аргументы:
            callback: Функция с сигнатурой (request_id, tool_call, options, on_choice).
                     - request_id: ID permission request
                     - tool_call: Информация о tool call
                     - options: Доступные опции разрешения
                     - on_choice: Callback функция (option_id) -> None для обработки выбора
        """
        self._permission_callback = callback
        self._logger.info(
            "permission_callback_set",
            callback_name=getattr(callback, "__name__", "unknown"),
        )

    def set_permission_handler(self, handler: PermissionHandler) -> None:
        """Установить PermissionHandler для обработки permission requests.

        Args:
            handler: PermissionHandler instance
        """
        self._permission_handler = handler

    def is_initialized(self) -> bool:
        """Проверяет, была ли выполнена инициализация.

        Возвращает:
            True если сервер инициализирован и capabilities сохранены
        """
        return self._server_capabilities is not None

    async def cancel_prompt(self, session_id: str) -> None:
        """Send session/cancel bypassing the callback lock.

        Uses the per-request response queue directly so the cancel is sent
        immediately, even while session/prompt holds _callbacks_request_lock.
        """
        if not self.is_connected() or self._queues is None:
            return

        request = ACPMessage.request(
            method="session/cancel",
            params={"sessionId": session_id},
        )
        request_id = request.id
        if request_id is None:
            return
        response_queue = await self._queues.get_or_create_response_queue(request_id)
        await self.send(request.to_dict())
        try:
            await asyncio.wait_for(response_queue.get(), timeout=5.0)
        except (TimeoutError, Exception):
            pass
        finally:
            await self._queues.cleanup_response_queue(request_id)

    async def _ensure_connected(self) -> None:
        """Проверяет соединение и восстанавливает при необходимости."""
        if not self.is_connected():
            self._logger.warning("request_with_callbacks_connection_lost_reconnecting")
            try:
                await self.connect()
            except Exception as e:
                msg = f"Failed to reconnect to server: {e}"
                self._logger.error("request_with_callbacks_reconnect_failed", error=str(e))
                raise RuntimeError(msg) from e

    async def _validate_request_setup(self) -> None:
        """Валидирует что транспорт готов к запросу."""
        if self._queues is None:
            msg = "Routing queues not initialized"
            self._logger.error("queues_not_initialized")
            raise RuntimeError(msg)

    async def _drain_remaining_notifications(
        self,
        *,
        method: str,
        request_id: str | int,
        on_update: Callable[[dict[str, Any]], None] | None,
    ) -> int:
        """Забирает оставшиеся уведомления после финального ответа."""
        remaining_notifications = 0
        max_remaining_iterations = 10
        for _ in range(max_remaining_iterations):
            try:
                notification_data = await asyncio.wait_for(
                    self._queues.notification_queue.get(),
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
        on_update: Callable[[dict[str, Any]], None] | None,
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
        )

        self._logger.info(
            "request_completed",
            method=method,
            request_id=request_id,
        )
        return response_data

    async def _wait_for_response_with_events(
        self,
        response_task: asyncio.Task[dict[str, Any]],
        permission_task: asyncio.Task[dict[str, Any]] | None,
        *,
        method: str,
        request_id: str | int,
        on_update: Callable[[dict[str, Any]], None] | None,
        on_fs_read: Callable[[str], Any] | None,
        on_fs_write: Callable[[str, str], Any] | None,
        on_terminal_create: Callable[[str], Any] | None,
        on_terminal_output: Callable[[str], Any] | None,
        on_terminal_wait: Callable[[str], Any] | None,
        on_terminal_release: Callable[[str], Any] | None,
        on_terminal_kill: Callable[[str], Any] | None,
    ) -> dict[str, Any]:
        """Основной цикл ожидания ответа с обработкой permission и notifications."""
        self._logger.info(
            "wait_for_response_with_events_start",
            method=method,
            request_id=request_id,
            has_permission_task=permission_task is not None,
        )
        while True:
            notification_task: asyncio.Task[dict[str, Any]] | None = asyncio.create_task(
                asyncio.wait_for(
                    self._queues.notification_queue.get(),
                    timeout=0.1,
                )
            )

            tasks_to_wait: list[asyncio.Task[dict[str, Any]]] = [response_task, notification_task]
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

            if permission_task is not None and permission_task in done:
                self._logger.info(
                    "permission_task_completed_in_wait_loop",
                    method=method,
                    request_id=request_id,
                )
                self._handle_permission_task(
                    permission_task, method=method, request_id=request_id,
                )
                permission_task = asyncio.create_task(
                    self._queues.permission_queue.get()
                )

            if notification_task in done:
                await self._handle_notification_task(
                    notification_task,
                    method=method,
                    request_id=request_id,
                    on_update=on_update,
                    on_fs_read=on_fs_read,
                    on_fs_write=on_fs_write,
                    on_terminal_create=on_terminal_create,
                    on_terminal_output=on_terminal_output,
                    on_terminal_wait=on_terminal_wait,
                    on_terminal_release=on_terminal_release,
                    on_terminal_kill=on_terminal_kill,
                )

            if response_task in done:
                return await self._process_response(
                    response_task,
                    method=method,
                    request_id=request_id,
                    on_update=on_update,
                )

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
        asyncio.ensure_future(
            self._handle_permission_request_with_handler(permission_data)
        )

    async def _handle_notification_task(
        self,
        notification_task: asyncio.Task[dict[str, Any]],
        *,
        method: str,
        request_id: str | int,
        on_update: Callable[[dict[str, Any]], None] | None,
        on_fs_read: Callable[[str], Any] | None,
        on_fs_write: Callable[[str, str], Any] | None,
        on_terminal_create: Callable[[str], Any] | None,
        on_terminal_output: Callable[[str], Any] | None,
        on_terminal_wait: Callable[[str], Any] | None,
        on_terminal_release: Callable[[str], Any] | None,
        on_terminal_kill: Callable[[str], Any] | None,
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
                on_fs_read=on_fs_read,
                on_fs_write=on_fs_write,
                on_terminal_create=on_terminal_create,
                on_terminal_output=on_terminal_output,
                on_terminal_wait=on_terminal_wait,
                on_terminal_release=on_terminal_release,
                on_terminal_kill=on_terminal_kill,
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

    async def request_with_callbacks(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        on_update: Callable[[dict[str, Any]], None] | None = None,
        on_fs_read: Callable[[str], Any] | None = None,
        on_fs_write: Callable[[str, str], Any] | None = None,
        on_terminal_create: Callable[[str], Any] | None = None,
        on_terminal_output: Callable[[str], Any] | None = None,
        on_terminal_wait: Callable[[str], Any] | None = None,
        on_terminal_release: Callable[[str], Any] | None = None,
        on_terminal_kill: Callable[[str], Any] | None = None,
    ) -> dict[str, Any]:
        """Выполняет request с обработкой callbacks используя routing queues.

        Архитектура:
        1. Создает очередь для этого request_id (или использует существующую)
        2. Отправляет request
        3. Ждет ответа из очереди для этого request_id
        4. Обрабатывает асинхронные события (updates, permissions)
        5. Несколько конкурентных запросов могут работать параллельно

        Аргументы:
            method: Метод для вызова
            params: Параметры метода
            on_update: Callback для session/update
            on_permission: Callback для session/request_permission
            on_fs_read: Callback для fs/read
            on_fs_write: Callback для fs/write
            on_terminal_create: Callback для terminal/create
            on_terminal_output: Callback для terminal/output
            on_terminal_wait: Callback для terminal/wait_for_exit
            on_terminal_release: Callback для terminal/release
            on_terminal_kill: Callback для terminal/kill

        Возвращает:
            Финальный ответ на request
        """
        # Проверяем и восстанавливаем соединение если оно потеряно
        await self._ensure_connected()
        await self._validate_request_setup()

        async with self._callbacks_request_lock:
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
                response_queue = await self._queues.get_or_create_response_queue(request_id)

                # Отправляем запрос (через send с защитой переподключения).
                await self.send(request_data)

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
                    permission_task = asyncio.create_task(
                        self._queues.permission_queue.get()
                    )

                try:
                    return await self._wait_for_response_with_events(
                        response_task,
                        permission_task,
                        method=method,
                        request_id=request_id,
                        on_update=on_update,
                        on_fs_read=on_fs_read,
                        on_fs_write=on_fs_write,
                        on_terminal_create=on_terminal_create,
                        on_terminal_output=on_terminal_output,
                        on_terminal_wait=on_terminal_wait,
                        on_terminal_release=on_terminal_release,
                        on_terminal_kill=on_terminal_kill,
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
                if request_id is not None and self._queues is not None:
                    cleanup_request_id: str | int = request_id
                    await self._queues.cleanup_response_queue(cleanup_request_id)

    async def _handle_permission_request_with_handler(
        self,
        message: dict[str, Any],
    ) -> None:
        """Обрабатывает session/request_permission через PermissionHandler.

        Интегрирует permission request с полным lifecycle:
        1. Парсинг request
        2. Обработка через PermissionHandler
        3. Формирование и отправка response

        Args:
            message: JSON-RPC сообщение с permission request
        """
        self._logger.info(
            "handle_permission_request_with_handler_called",
            message_id=message.get("id"),
            method=message.get("method"),
            has_permission_handler=self._permission_handler is not None,
            has_permission_callback=self._permission_callback is not None,
        )

        if self._permission_handler is None:
            self._logger.warning("permission_handler_not_configured_skipping")
            # Отправить cancel response чтобы сервер не завис
            try:
                cancel_response = {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "result": {"outcome": "cancelled"},
                }
                await self.send(cancel_response)
                self._logger.debug("cancel_response_sent_for_missing_handler")
            except Exception as send_error:
                self._logger.error(
                    "failed_to_send_cancel_response",
                    error=str(send_error),
                )
            return

        try:
            # Парсинг request
            request = RequestPermissionRequest.model_validate(message)

            self._logger.info(
                "handling_permission_request_with_handler",
                request_id=request.id,
                session_id=request.params.sessionId,
                tool_call_id=request.params.toolCall.toolCallId,
                has_ui_callback=self._permission_callback is not None,
            )

            # Обработка через handler с callback если он установлен
            # Если callback=None, PermissionHandler вернет CancelledPermissionOutcome
            outcome = await self._permission_handler.handle_request(
                request=request,
                callback=self._permission_callback,
            )

            self._logger.info(
                "permission_request_handled_successfully",
                request_id=request.id,
                outcome=outcome.outcome,
            )

        except Exception as e:
            self._logger.error(
                "permission_request_handling_error",
                error=str(e),
                error_type=type(e).__name__,
                message_id=message.get("id"),
            )
            # Отправить error response
            try:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "error": {
                        "code": -32603,
                        "message": f"Internal error: {e}",
                    },
                }
                await self.send(error_response)
                self._logger.debug(
                    "error_response_sent",
                    message_id=message.get("id"),
                )
            except Exception as send_error:
                self._logger.error(
                    "failed_to_send_error_response",
                    error=str(send_error),
                )

    async def _handle_notification_or_client_rpc(
        self,
        *,
        method: str,
        request_id: str | int,
        notification_data: dict[str, Any],
        on_update: Callable[[dict[str, Any]], None] | None,
        on_fs_read: Callable[[str], Any] | None,
        on_fs_write: Callable[[str, str], Any] | None,
        on_terminal_create: Callable[[str], Any] | None,
        on_terminal_output: Callable[[str], Any] | None,
        on_terminal_wait: Callable[[str], Any] | None,
        on_terminal_release: Callable[[str], Any] | None,
        on_terminal_kill: Callable[[str], Any] | None,
    ) -> None:
        """Обрабатывает `session/update` и incoming RPC (`fs/*`, `terminal/*`)."""
        notification = ACPMessage.from_dict(notification_data)

        if notification.method == "session/update":
            await self._handle_session_update(
                notification_data, method=method, request_id=request_id, on_update=on_update,
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

        if self._rpc_dispatcher is not None:
            result = await self._rpc_dispatcher.dispatch(rpc_method, rpc_id, rpc_params)
            if "error" in result:
                error_info = result["error"]
                await self.send(
                    ACPMessage.error_response(
                        rpc_id,
                        code=error_info.get("code", -32603),
                        message=error_info.get("message", "Unknown error"),
                    ).to_dict()
                )
            else:
                await self.send(ACPMessage.response(rpc_id, result).to_dict())
            return

        handlers: dict[str, Callable[[], Any]] = {
            "fs/read_text_file": lambda: self._handle_fs_read(
                rpc_id, rpc_params, on_fs_read,
            ),
            "fs/write_text_file": lambda: self._handle_fs_write(
                rpc_id, rpc_params, on_fs_write,
            ),
            "terminal/create": lambda: self._handle_terminal_create(
                rpc_id, rpc_params, on_terminal_create,
            ),
            "terminal/output": lambda: self._handle_terminal_output(
                rpc_id, rpc_params, on_terminal_output,
            ),
            "terminal/wait_for_exit": lambda: self._handle_terminal_wait(
                rpc_id, rpc_params, on_terminal_wait,
            ),
            "terminal/release": lambda: self._handle_terminal_release(
                rpc_id, rpc_params, on_terminal_release,
            ),
            "terminal/kill": lambda: self._handle_terminal_kill(
                rpc_id, rpc_params, on_terminal_kill,
            ),
        }

        handler = handlers.get(rpc_method)
        if handler is not None:
            await handler()
        else:
            await self._handle_unknown_rpc(notification.id)

    async def _handle_session_update(
        self,
        notification_data: dict[str, Any],
        *,
        method: str,
        request_id: str | int,
        on_update: Callable[[dict[str, Any]], None] | None,
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

    async def _handle_fs_read(
        self,
        rpc_id: str | int,
        rpc_params: dict[str, Any],
        on_fs_read: Callable[[str], Any] | None,
    ) -> None:
        path = rpc_params.get("path")
        self._logger.info(
            "fs_read_rpc_start",
            rpc_id=rpc_id,
            path=path,
            has_callback=on_fs_read is not None,
        )
        try:
            content = (
                await _call_callback(on_fs_read, path)
                if on_fs_read is not None and isinstance(path, str)
                else ""
            )
            self._logger.info(
                "fs_read_rpc_callback_done",
                rpc_id=rpc_id,
                content_size=len(content),
            )
            response_msg = ACPMessage.response(rpc_id, {"content": content}).to_dict()
            self._logger.info(
                "fs_read_rpc_sending_response",
                rpc_id=rpc_id,
            )
            await self.send(response_msg)
            self._logger.info(
                "fs_read_rpc_response_sent",
                rpc_id=rpc_id,
            )
        except Exception as e:
            self._logger.error(
                "fs_read_rpc_error",
                rpc_id=rpc_id,
                path=path,
                error=str(e),
                error_type=type(e).__name__,
            )
            error_response = {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32603, "message": str(e)},
            }
            await self.send(error_response)

    async def _handle_fs_write(
        self,
        rpc_id: str | int,
        rpc_params: dict[str, Any],
        on_fs_write: Callable[[str, str], Any] | None,
    ) -> None:
        path = rpc_params.get("path")
        text = rpc_params.get("content")
        self._logger.debug(
            "tool_lifecycle_callback_start",
            rpc_id=rpc_id,
            rpc_method="fs/write_text_file",
            path=path,
            text_size=len(text) if isinstance(text, str) else 0,
            has_callback=on_fs_write is not None,
        )
        try:
            if on_fs_write is not None and isinstance(path, str) and isinstance(text, str):
                await _call_callback(on_fs_write, path, text)
            await self.send(ACPMessage.response(rpc_id, {}).to_dict())
        except Exception as e:
            self._logger.error(
                "fs_write_rpc_error",
                rpc_id=rpc_id,
                path=path,
                error=str(e),
                error_type=type(e).__name__,
            )
            await self.send({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32603, "message": str(e)},
            })

    async def _handle_terminal_create(
        self,
        rpc_id: str | int,
        rpc_params: dict[str, Any],
        on_terminal_create: Callable[[str], Any] | None,
    ) -> None:
        command = rpc_params.get("command")
        terminal_id = (
            await _call_callback(on_terminal_create, command)
            if on_terminal_create is not None and isinstance(command, str)
            else None
        )
        if terminal_id is None:
            await self.send(
                ACPMessage.error_response(
                    rpc_id,
                    code=-32000,
                    message="terminal/create callback not configured",
                ).to_dict()
            )
        else:
            await self.send(
                ACPMessage.response(rpc_id, {"terminalId": terminal_id}).to_dict()
            )

    async def _handle_terminal_output(
        self,
        rpc_id: str | int,
        rpc_params: dict[str, Any],
        on_terminal_output: Callable[[str], Any] | None,
    ) -> None:
        terminal_id = rpc_params.get("terminalId")
        output_data: dict[str, Any] | None = (
            await _call_callback(on_terminal_output, terminal_id)
            if on_terminal_output is not None and isinstance(terminal_id, str)
            else None
        )
        if output_data is None:
            await self.send(
                ACPMessage.error_response(
                    rpc_id,
                    code=-32000,
                    message="terminal/output callback not configured",
                ).to_dict()
            )
        else:
            await self.send(ACPMessage.response(rpc_id, output_data).to_dict())

    async def _handle_terminal_wait(
        self,
        rpc_id: str | int,
        rpc_params: dict[str, Any],
        on_terminal_wait: Callable[[str], Any] | None,
    ) -> None:
        terminal_id = rpc_params.get("terminalId")
        exit_code: int | None = None
        output: str | None = None
        if on_terminal_wait is not None and isinstance(terminal_id, str):
            wait_result = await _call_callback(on_terminal_wait, terminal_id)
            if isinstance(wait_result, tuple):
                candidate_exit_code, candidate_output = wait_result
                exit_code = candidate_exit_code if isinstance(candidate_exit_code, int) else None
                output = candidate_output if isinstance(candidate_output, str) else None
            elif isinstance(wait_result, int):
                exit_code = wait_result

        result_payload: dict[str, Any] = {}
        if exit_code is not None:
            result_payload["exitCode"] = exit_code
        if output is not None:
            result_payload["output"] = output
        await self.send(ACPMessage.response(rpc_id, result_payload).to_dict())

    async def _handle_terminal_release(
        self,
        rpc_id: str | int,
        rpc_params: dict[str, Any],
        on_terminal_release: Callable[[str], Any] | None,
    ) -> None:
        terminal_id = rpc_params.get("terminalId")
        if on_terminal_release is not None and isinstance(terminal_id, str):
            await _call_callback(on_terminal_release, terminal_id)
        await self.send(ACPMessage.response(rpc_id, {}).to_dict())

    async def _handle_terminal_kill(
        self,
        rpc_id: str | int,
        rpc_params: dict[str, Any],
        on_terminal_kill: Callable[[str], Any] | None,
    ) -> None:
        terminal_id = rpc_params.get("terminalId")
        killed = (
            await _call_callback(on_terminal_kill, terminal_id)
            if on_terminal_kill is not None and isinstance(terminal_id, str)
            else False
        )
        await self.send(ACPMessage.response(rpc_id, {"killed": killed}).to_dict())

    async def _handle_unknown_rpc(self, rpc_id: str | int) -> None:
        """Отправляет пустой response на неизвестный RPC."""
        await self.send(ACPMessage.response(rpc_id, {}).to_dict())

    def cleanup(self) -> None:
        """Очищает ресурсы синхронно (вызывается DI контейнером).

        Это вспомогательный метод для синхронной очистки.
        Для асинхронной очистки используйте disconnect().
        """
        self._logger.debug("cleanup_called")
        # Синхронная очистка - просто отмечаем что ресурсы больше не используются
        # Асинхронное закрытие соединения должно происходить через disconnect()

    def close(self) -> None:
        """Закрывает ресурсы синхронно (вызывается DI контейнером).

        Это вспомогательный метод для синхронного закрытия.
        Для асинхронного закрытия используйте disconnect().
        """
        self._logger.debug("close_called")
        # Синхронное закрытие - просто отмечаем что ресурсы больше не используются
        # Асинхронное закрытие соединения должно происходить через disconnect()


def create_websocket_transport_service(
    host: str,
    port: int,
    parser: MessageParser | None = None,
    permission_handler: PermissionHandler | None = None,
) -> ACPTransportService:
    """Factory функция для создания ACPTransportService с WebSocket транспортом.

    Обеспечивает обратную совместимость для кода, который создавал
    ACPTransportService напрямую с host/port.

    Args:
        host: Адрес ACP сервера.
        port: Порт ACP сервера.
        parser: MessageParser для парсинга ответов.
        permission_handler: PermissionHandler для обработки permission requests.

    Returns:
        Настроенный ACPTransportService с WebSocket транспортом.
    """
    transport = WebSocketTransport(host=host, port=port)
    return ACPTransportService(
        transport=transport,
        parser=parser,
        permission_handler=permission_handler,
    )

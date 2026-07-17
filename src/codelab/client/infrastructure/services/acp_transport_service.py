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
import json
from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, Any

import structlog

from codelab.client.domain import TransportService
from codelab.client.infrastructure.message_parser import MessageParser
from codelab.client.infrastructure.services.acp_transport import (
    PermissionResponder,
    RequestCallbackCoordinator,
)
from codelab.client.infrastructure.services.background_receive_loop import (
    BackgroundReceiveLoop,
)
from codelab.client.infrastructure.services.message_router import MessageRouter
from codelab.client.infrastructure.services.routing_queues import RoutingQueues
from codelab.client.infrastructure.transport import Transport, WebSocketTransport
from codelab.client.messages import ACPMessage

if TYPE_CHECKING:
    from codelab.client.application.permission_handler import PermissionHandler
    from codelab.client.infrastructure.services.acp_transport.client_rpc_dispatcher import (
        ClientRpcDispatcher,
    )


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
        self._rpc_dispatcher = rpc_dispatcher
        # Обработка session/request_permission вынесена в отдельный компонент.
        # UI-callback появляется позже (после инициализации TUI) и ставится
        # через set_permission_callback.
        self._permission_responder = PermissionResponder(
            send=lambda message: self.send(message),
            handler=permission_handler,
        )
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

        # Оркестрация request/response с асинхронными событиями вынесена в
        # отдельный компонент. Он читает актуальные очереди/диспетчер через
        # провайдеры, поэтому переживает пересоздание очередей при реконнекте.
        self._coordinator = RequestCallbackCoordinator(
            queues_provider=lambda: self._queues,
            dispatcher_provider=lambda: self._rpc_dispatcher,
            send=lambda message: self.send(message),
            permission_responder=self._permission_responder,
            request_lock=self._callbacks_request_lock,
        )

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
                message = await response_queue.get()
            else:
                # Получаем асинхронное уведомление
                self._logger.debug("waiting_for_notification")
                message = await self._queues.notification_queue.get()

            message_id = message.get("id")
            self._logger.debug(
                "message_received_from_queue",
                message_id=message_id,
                request_id=request_id,
                has_result="result" in message,
                has_error="error" in message,
            )
            return message
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
        self._permission_responder.set_callback(callback)

    def set_permission_handler(self, handler: PermissionHandler) -> None:
        """Установить PermissionHandler для обработки permission requests.

        Args:
            handler: PermissionHandler instance
        """
        self._permission_responder.set_handler(handler)

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

    async def request_with_callbacks(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        on_update: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Выполняет request с обработкой session/update и входящих server->client RPC.

        Оркестрация вынесена в RequestCallbackCoordinator; перед делегированием
        при необходимости восстанавливается соединение.

        Аргументы:
            method: Метод для вызова.
            params: Параметры метода.
            on_update: Callback для session/update.

        Возвращает:
            Финальный ответ на request.
        """
        await self._ensure_connected()
        return await self._coordinator.execute(method, params, on_update)


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

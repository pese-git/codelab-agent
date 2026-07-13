"""SseTransport — MCP через Server-Sent Events (deprecated)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from typing import Any

import aiohttp

from .base import MCPTransportError
from .http_transport import HttpTransport
from .models import MCPNotification, MCPRequest, MCPResponse

logger = logging.getLogger(__name__)


class SseTransportError(MCPTransportError):
    """Базовое исключение для ошибок SSE транспорта."""

    pass


class SseTransport:
    """SSE (Server-Sent Events) транспорт для MCP серверов.

    Поддерживает SSE connection для получения событий от MCP сервера.
    Данный транспорт deprecated в MCP spec и поддерживается только
    для обратной совместимости.

    Attributes:
        url: URL SSE endpoint MCP сервера.
        headers: HTTP headers для запросов.
        timeout: Таймаут запросов в секундах.

    Example:
        >>> config = SseTransportConfig(url="http://localhost:8080/sse")
        >>> transport = SseTransport(config)
        >>> await transport.connect()
        >>> response = await transport.send_request("initialize", {...})
        >>> await transport.close()
    """

    def __init__(
        self,
        url: str,
        headers: list[dict[str, str]] | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Инициализация SSE транспорта.

        Args:
            url: URL SSE endpoint.
            headers: Список HTTP headers [{name: value}].
            timeout: Таймаут запросов в секундах.
        """
        self._url = url
        self._headers = HttpTransport._build_headers(headers)
        self._timeout = timeout
        self._session: aiohttp.ClientSession | None = None
        self._sse_response: aiohttp.ClientResponse | None = None
        self._request_id: int = 0
        self._pending_requests: dict[int | str, asyncio.Future[MCPResponse]] = {}
        self._closed: bool = False
        self._lock: asyncio.Lock = asyncio.Lock()
        self._notification_queue: asyncio.Queue = asyncio.Queue()
        self._notification_handlers: dict[str, list[Callable]] = {}
        self._request_handlers: dict[str, Callable] = {}
        self._read_task: asyncio.Task[None] | None = None

        # Логируем warning о deprecated статусе
        logger.warning(
            "SSE transport is deprecated in MCP spec. Consider using HTTP transport instead."
        )

    @property
    def is_connected(self) -> bool:
        """Проверить, установлено ли соединение."""
        return (
            self._session is not None
            and not self._session.closed
            and self._sse_response is not None
            and not self._closed
        )

    async def connect(self) -> None:
        """Установить SSE соединение с MCP сервером.

        Создаёт SSE connection и запускает фоновую задачу чтения событий.

        Raises:
            SseTransportError: Если не удалось подключиться.
        """
        if self._session is not None:
            raise SseTransportError("Transport already connected")

        logger.debug("Connecting to MCP SSE server: %s", self._url)

        try:
            timeout = aiohttp.ClientTimeout(total=self._timeout)
            self._session = aiohttp.ClientSession(
                headers=self._headers,
                timeout=timeout,
            )

            # Устанавливаем SSE соединение
            self._sse_response = await self._session.get(
                self._url,
                headers={
                    **self._headers,
                    "Accept": "text/event-stream",
                },
            )

            # Запускаем фоновую задачу чтения SSE событий
            self._read_task = asyncio.create_task(self._read_sse_loop(), name="mcp_sse_reader")

            logger.info("Connected to MCP SSE server: %s", self._url)

        except aiohttp.ClientError as e:
            self._session = None
            raise SseTransportError(f"Failed to connect to MCP SSE server: {e}") from e

    async def send_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Отправить JSON-RPC запрос и дождаться ответа.

        Для SSE транспорта запросы отправляются через HTTP POST,
        а ответы приходят через SSE events.

        Args:
            method: Имя вызываемого метода.
            params: Параметры запроса.
            timeout: Таймаут ожидания ответа в секундах.

        Returns:
            Результат из ответа (поле result).

        Raises:
            SseTransportError: Если соединение не установлено.
        """
        if not self.is_connected:
            raise SseTransportError("Not connected to MCP server")

        if not self._session:
            raise SseTransportError("Session not initialized")

        # Генерируем уникальный ID запроса
        async with self._lock:
            self._request_id += 1
            request_id = self._request_id

        # Создаём запрос
        request = MCPRequest(id=request_id, method=method, params=params)

        # Создаём Future для ожидания ответа
        loop = asyncio.get_running_loop()
        future: asyncio.Future[MCPResponse] = loop.create_future()
        self._pending_requests[request_id] = future

        request_timeout = timeout or self._timeout

        try:
            # Отправляем HTTP POST запрос (SSE использует POST для запросов)
            async with self._session.post(
                self._url,
                json=request.model_dump(by_alias=True, exclude_none=True),
                headers=self._headers,
            ) as response:
                logger.debug(
                    "SSE HTTP response status: %d for method=%s id=%d",
                    response.status,
                    method,
                    request_id,
                )

                if response.status >= 400:
                    raise SseTransportError(f"HTTP error: status {response.status}")

            # Ожидаем ответ через SSE events
            try:
                mcp_response = await asyncio.wait_for(future, timeout=request_timeout)
            except TimeoutError:
                raise SseTransportError(
                    f"Request timeout after {request_timeout}s: method={method}"
                ) from None

            # Проверяем на ошибку
            if mcp_response.error:
                raise SseTransportError(
                    f"MCP error {mcp_response.error.code}: {mcp_response.error.message}"
                )

            return mcp_response.result or {}

        finally:
            self._pending_requests.pop(request_id, None)

    async def send_notification(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Отправить JSON-RPC нотификацию.

        Args:
            method: Имя метода нотификации.
            params: Параметры нотификации.

        Raises:
            SseTransportError: Если соединение не установлено.
        """
        if not self.is_connected:
            raise SseTransportError("Not connected to MCP server")

        if not self._session:
            raise SseTransportError("Session not initialized")

        notification = MCPNotification(method=method, params=params)

        try:
            async with self._session.post(
                self._url,
                json=notification.model_dump(by_alias=True, exclude_none=True),
                headers=self._headers,
            ) as response:
                logger.debug("Sent SSE notification: method=%s status=%d", method, response.status)
        except aiohttp.ClientError as e:
            raise SseTransportError(f"Failed to send notification: {e}") from e

    async def close(self) -> None:
        """Закрыть SSE соединение.

        Отменяет все ожидающие запросы и закрывает SSE connection.
        """
        if self._closed:
            return

        self._closed = True

        logger.debug("Closing SSE MCP transport")

        # Отменяем все ожидающие запросы
        for _request_id, future in self._pending_requests.items():
            if not future.done():
                future.set_exception(SseTransportError("Transport closed"))
        self._pending_requests.clear()

        # Останавливаем задачу чтения
        if self._read_task:
            self._read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._read_task

        # Закрываем SSE response
        if self._sse_response and not self._sse_response.closed:
            await self._sse_response.release()

        # Закрываем session
        if self._session and not self._session.closed:
            await self._session.close()

        self._session = None
        self._sse_response = None
        logger.debug("SSE MCP transport closed")

    async def _read_sse_loop(self) -> None:
        """Фоновая задача чтения SSE событий.

        Парсит SSE events (data:, event:, id: lines) и диспетчеризирует их.
        """
        if not self._sse_response:
            return

        current_event = "message"  # default SSE event type
        current_data = []
        current_id = None

        try:
            async for line in self._sse_response.content:
                text = line.decode("utf-8").rstrip("\n")

                if not text:
                    # Пустая строка — конец события
                    if current_data:
                        await self._handle_sse_event(
                            event=current_event, data="\n".join(current_data), event_id=current_id
                        )
                        current_data = []
                        current_event = "message"
                        current_id = None
                    continue

                if text.startswith(":"):
                    # Комментарий — игнорируем
                    continue

                if ":" in text:
                    field, value = text.split(":", 1)
                    value = value.lstrip(" ")
                else:
                    field = text
                    value = ""

                if field == "event":
                    current_event = value
                elif field == "data":
                    current_data.append(value)
                elif field == "id":
                    current_id = value

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Error reading SSE events: %s", e)
            # Отменяем все ожидающие запросы
            for future in self._pending_requests.values():
                if not future.done():
                    future.set_exception(SseTransportError(f"SSE read error: {e}"))

    async def _handle_sse_event(
        self,
        event: str,
        data: str,
        event_id: str | None = None,
    ) -> None:
        """Обработать SSE событие.

        Согласно JSON-RPC 2.0 спецификации, правильно классифицирует сообщения:
        - Request: method + id
        - Response: result/error + id
        - Notification: method без id

        Args:
            event: Тип события.
            data: Данные события.
            event_id: ID события.
        """
        logger.debug("Received SSE event: type=%s id=%s", event, event_id)

        try:
            json_data = json.loads(data)
        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON in SSE event: %s", e)
            return

        # Правильная классификация согласно JSON-RPC 2.0
        message_id = json_data.get("id")
        method = json_data.get("method")
        has_result = "result" in json_data
        has_error = "error" in json_data

        if method is not None and message_id is not None:
            # Входящий Request от сервера
            await self._handle_incoming_request(json_data)
        elif message_id is not None and (has_result or has_error):
            # Response на наш запрос
            await self._handle_response_message(json_data)
        elif method is not None and message_id is None:
            # Notification от сервера
            await self._handle_notification(json_data)
        else:
            logger.warning("Unknown SSE message format: %s", json_data)

    async def _handle_response_message(self, data: dict[str, Any]) -> None:
        """Обработать ответ на наш запрос.

        Args:
            data: Распарсенное JSON сообщение (response).
        """
        message_id = data.get("id")

        # message_id обязателен для ответов
        if message_id is None:
            logger.warning("Received response without id")
            return

        future = self._pending_requests.get(message_id)

        if future and not future.done():
            try:
                response = MCPResponse.model_validate(data)
                future.set_result(response)
            except Exception as e:
                future.set_exception(SseTransportError(f"Invalid response: {e}"))
        else:
            logger.warning("Received response for unknown request id=%s", message_id)

    async def _handle_notification(self, data: dict[str, Any]) -> None:
        """Обработать notification от сервера.

        Args:
            data: Распарсенное JSON сообщение (notification).
        """
        method = data.get("method", "unknown")
        logger.debug("Received MCP notification via SSE: method=%s", method)

        # Помещаем в очередь notifications
        await self._notification_queue.put(data)

        # Вызываем зарегистрированные handlers
        handlers = self._notification_handlers.get(method, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error("Error in SSE notification handler: %s", e)

    async def _handle_incoming_request(self, data: dict[str, Any]) -> None:
        """Обработать входящий запрос от сервера.

        Согласно MCP спецификации, сервер может отправлять запросы клиенту
        (например, roots/list). Клиент должен обработать запрос и отправить ответ.

        Args:
            data: Распарсенное JSON сообщение (request).
        """
        method = data.get("method", "unknown")
        request_id = data.get("id")
        params = data.get("params", {})

        # request_id обязателен для запросов
        if request_id is None:
            logger.warning("Received incoming request without id: method=%s", method)
            return

        logger.debug(
            "Received incoming request from MCP server via SSE: method=%s id=%s", method, request_id
        )

        handler = self._request_handlers.get(method)
        if handler:
            try:
                result = await handler(params)
                await self.send_response(request_id, result)
                logger.debug(
                    "Successfully handled incoming request: method=%s id=%s", method, request_id
                )
            except Exception as e:
                logger.error("Error handling incoming request %s: %s", method, e)
                await self.send_error(request_id, -32603, f"Internal error: {str(e)}")
        else:
            logger.warning("No handler registered for incoming request method: %s", method)
            await self.send_error(request_id, -32601, f"Method not found: {method}")

    def register_notification_handler(
        self,
        method: str,
        handler: Callable,
    ) -> None:
        """Зарегистрировать обработчик для конкретного типа notification.

        Args:
            method: Имя метода notification.
            handler: Функция для обработки.
        """
        if method not in self._notification_handlers:
            self._notification_handlers[method] = []
        self._notification_handlers[method].append(handler)

    def register_request_handler(self, method: str, handler: Callable) -> None:
        """Зарегистрировать обработчик входящего запроса от сервера.

        Согласно MCP спецификации, сервер может отправлять запросы клиенту
        (например, roots/list). Этот метод позволяет зарегистрировать обработчик
        для таких запросов.

        Args:
            method: Имя метода запроса (например, "roots/list").
            handler: Async функция-обработчик, принимающая params и возвращающая result.
        """
        self._request_handlers[method] = handler
        logger.debug("Registered request handler for: %s", method)

    async def send_response(self, request_id: int | str, result: Any) -> None:
        """Отправить ответ на входящий запрос от сервера.

        Args:
            request_id: ID запроса, на который отправляем ответ.
            result: Результат выполнения запроса.
        """
        if not self.is_connected:
            raise SseTransportError("Not connected to MCP server")

        if not self._session:
            raise SseTransportError("Session not initialized")

        response = {"jsonrpc": "2.0", "id": request_id, "result": result}

        try:
            async with self._session.post(
                self._url,
                json=response,
                headers=self._headers,
            ) as response_obj:
                logger.debug(
                    "Sent response to MCP server via SSE: id=%s status=%d",
                    request_id,
                    response_obj.status,
                )
        except aiohttp.ClientError as e:
            raise SseTransportError(f"Failed to send response: {e}") from e

    async def send_error(
        self, request_id: int | str, code: int, message: str, data: Any = None
    ) -> None:
        """Отправить ошибку на входящий запрос от сервера.

        Args:
            request_id: ID запроса, на который отправляем ошибку.
            code: Код ошибки согласно JSON-RPC 2.0.
            message: Сообщение об ошибке.
            data: Дополнительные данные об ошибке (опционально).
        """
        if not self.is_connected:
            raise SseTransportError("Not connected to MCP server")

        if not self._session:
            raise SseTransportError("Session not initialized")

        error_response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

        if data is not None:
            error_response["error"]["data"] = data

        try:
            async with self._session.post(
                self._url,
                json=error_response,
                headers=self._headers,
            ) as response_obj:
                logger.debug(
                    "Sent error response to MCP server via SSE: id=%s code=%s status=%d",
                    request_id,
                    code,
                    response_obj.status,
                )
        except aiohttp.ClientError as e:
            raise SseTransportError(f"Failed to send error response: {e}") from e

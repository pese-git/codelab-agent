"""HttpTransport — MCP через HTTP POST с JSON-RPC."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import aiohttp

from .base import MCPTransportError
from .models import MCPNotification, MCPRequest, MCPResponse

logger = logging.getLogger(__name__)


class HttpTransportError(MCPTransportError):
    """Базовое исключение для ошибок HTTP транспорта."""

    pass


class HttpConnectionError(HttpTransportError):
    """Ошибка подключения к HTTP серверу."""

    pass


class HttpTimeoutError(HttpTransportError):
    """Таймаут HTTP запроса."""

    pass


class HttpTransport:
    """HTTP транспорт для коммуникации с MCP серверами.

    Использует HTTP POST запросы для отправки JSON-RPC сообщений
    к MCP серверу через HTTP endpoint.

    Attributes:
        url: URL MCP сервера.
        headers: HTTP headers для запросов.
        timeout: Таймаут запросов в секундах.

    Example:
        >>> config = HttpTransportConfig(url="http://localhost:8080")
        >>> transport = HttpTransport(config)
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
        """Инициализация HTTP транспорта.

        Args:
            url: URL MCP сервера.
            headers: Список HTTP headers [{name: value}].
            timeout: Таймаут запросов в секундах.
        """
        self._url = url
        self._headers = self._build_headers(headers)
        self._timeout = timeout
        self._session: aiohttp.ClientSession | None = None
        self._request_id: int = 0
        self._pending_requests: dict[int | str, asyncio.Future[MCPResponse]] = {}
        self._closed: bool = False
        self._lock: asyncio.Lock = asyncio.Lock()
        # Обработчики notifications: dict[method] -> list[handler]
        self._notification_handlers: dict[str, list[Callable]] = {}
        # Обработчики входящих запросов от сервера
        self._request_handlers: dict[str, Callable] = {}

    @staticmethod
    def _build_headers(headers: list[dict[str, str]] | None) -> dict[str, str]:
        """Преобразовать список headers в словарь.

        Args:
            headers: Список [{name: value}] или None.

        Returns:
            Словарь HTTP headers.
        """
        if not headers:
            return {}

        result = {}
        for item in headers:
            if "name" in item and "value" in item:
                result[item["name"]] = item["value"]
            else:
                result.update(item)
        return result

    @property
    def is_connected(self) -> bool:
        """Проверить, установлено ли соединение."""
        return self._session is not None and not self._session.closed and not self._closed

    async def connect(self) -> None:
        """Установить HTTP соединение с MCP сервером.

        Создаёт aiohttp.ClientSession с настроенными headers.

        Raises:
            HttpConnectionError: Если не удалось подключиться.
        """
        if self._session is not None:
            raise HttpTransportError("Transport already connected")

        logger.debug("Connecting to MCP HTTP server: %s", self._url)

        try:
            timeout = aiohttp.ClientTimeout(total=self._timeout)
            self._session = aiohttp.ClientSession(
                headers=self._headers,
                timeout=timeout,
            )

            # Проверяем соединение, отправляя простой запрос
            async with self._session.head(self._url) as response:
                if response.status >= 400:
                    logger.warning("MCP HTTP server returned status %d on connect", response.status)

            logger.info("Connected to MCP HTTP server: %s", self._url)

        except aiohttp.ClientError as e:
            self._session = None
            raise HttpConnectionError(f"Failed to connect to MCP HTTP server: {e}") from e

    async def send_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Отправить JSON-RPC запрос и дождаться ответа.

        Args:
            method: Имя вызываемого метода.
            params: Параметры запроса.
            timeout: Таймаут ожидания ответа в секундах.

        Returns:
            Результат из ответа (поле result).

        Raises:
            HttpConnectionError: Если соединение не установлено.
            HttpTimeoutError: Если истёк таймаут.
            HttpTransportError: При ошибке в ответе.
        """
        if not self.is_connected:
            raise HttpConnectionError("Not connected to MCP server")

        if not self._session:
            raise HttpConnectionError("Session not initialized")

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
            # Отправляем HTTP POST запрос
            async with self._session.post(
                self._url,
                json=request.model_dump(by_alias=True, exclude_none=True),
                headers=self._headers,
            ) as response:
                logger.debug(
                    "HTTP response status: %d for method=%s id=%d",
                    response.status,
                    method,
                    request_id,
                )

                if response.status == 408 or response.status == 504:
                    raise HttpTimeoutError(f"HTTP timeout: status {response.status}")

                if response.status >= 500:
                    raise HttpTransportError(f"HTTP server error: status {response.status}")

                if response.status >= 400:
                    raise HttpTransportError(f"HTTP client error: status {response.status}")

                # Парсим JSON ответ
                try:
                    data = await response.json()
                except json.JSONDecodeError as e:
                    raise HttpTransportError(f"Invalid JSON response: {e}") from e

                # Обрабатываем ответ
                await self._handle_response(data)

            # Ожидаем ответ с таймаутом
            try:
                mcp_response = await asyncio.wait_for(future, timeout=request_timeout)
            except TimeoutError:
                raise HttpTimeoutError(
                    f"Request timeout after {request_timeout}s: method={method}"
                ) from None

            # Проверяем на ошибку
            if mcp_response.error:
                raise HttpTransportError(
                    f"MCP error {mcp_response.error.code}: {mcp_response.error.message}"
                )

            return mcp_response.result or {}

        finally:
            # Удаляем из ожидающих
            self._pending_requests.pop(request_id, None)

    async def send_notification(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Отправить JSON-RPC нотификацию без ожидания ответа.

        Args:
            method: Имя метода нотификации.
            params: Параметры нотификации.

        Raises:
            HttpConnectionError: Если соединение не установлено.
        """
        if not self.is_connected:
            raise HttpConnectionError("Not connected to MCP server")

        if not self._session:
            raise HttpConnectionError("Session not initialized")

        notification = MCPNotification(method=method, params=params)

        try:
            async with self._session.post(
                self._url,
                json=notification.model_dump(by_alias=True, exclude_none=True),
                headers=self._headers,
            ) as response:
                logger.debug("Sent HTTP notification: method=%s status=%d", method, response.status)
        except aiohttp.ClientError as e:
            raise HttpTransportError(f"Failed to send notification: {e}") from e

    async def close(self) -> None:
        """Закрыть HTTP соединение.

        Отменяет все ожидающие запросы и закрывает aiohttp session.
        """
        if self._closed:
            return

        self._closed = True

        logger.debug("Closing HTTP MCP transport")

        # Отменяем все ожидающие запросы
        for _request_id, future in self._pending_requests.items():
            if not future.done():
                future.set_exception(HttpTransportError("Transport closed"))
        self._pending_requests.clear()

        # Закрываем session
        if self._session and not self._session.closed:
            await self._session.close()

        self._session = None
        logger.debug("HTTP MCP transport closed")

    async def _handle_response(self, data: dict[str, Any]) -> None:
        """Обработать входящее JSON-RPC сообщение.

        Согласно JSON-RPC 2.0 спецификации, правильно классифицирует сообщения:
        - Request: method + id
        - Response: result/error + id
        - Notification: method без id

        Args:
            data: Распарсенное JSON сообщение.
        """
        message_id = data.get("id")
        method = data.get("method")
        has_result = "result" in data
        has_error = "error" in data

        # Правильная классификация согласно JSON-RPC 2.0
        if method is not None and message_id is not None:
            # Входящий Request от сервера
            await self._handle_incoming_request(data)
        elif message_id is not None and (has_result or has_error):
            # Response на наш запрос
            await self._handle_response_message(data)
        elif method is not None and message_id is None:
            # Notification от сервера
            await self._handle_notification(data)
        else:
            logger.warning("Unknown message format: %s", data)

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
                future.set_exception(HttpTransportError(f"Invalid response: {e}"))
        else:
            logger.warning("Received response for unknown request id=%s", message_id)

    async def _handle_notification(self, data: dict[str, Any]) -> None:
        """Обработать notification от сервера.

        Args:
            data: Распарсенное JSON сообщение (notification).
        """
        method = data.get("method", "unknown")
        logger.debug("Received MCP notification: method=%s", method)
        # Вызываем обработчики для конкретного метода
        handlers = self._notification_handlers.get(method, [])
        # Также вызываем wildcard handlers (для всех notifications)
        handlers += self._notification_handlers.get("*", [])

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error("Error in notification handler for %s: %s", method, e)

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
            "Received incoming request from MCP server: method=%s id=%s", method, request_id
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

    def register_notification_handler(self, method: str, handler: Callable) -> None:
        """Зарегистрировать обработчик notification.

        Args:
            method: Имя метода notification (или "*" для всех).
            handler: Функция-обработчик (async или sync).
        """
        if method not in self._notification_handlers:
            self._notification_handlers[method] = []
        self._notification_handlers[method].append(handler)
        logger.debug("Registered notification handler for: %s", method)

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
            raise HttpConnectionError("Not connected to MCP server")

        if not self._session:
            raise HttpConnectionError("Session not initialized")

        response = {"jsonrpc": "2.0", "id": request_id, "result": result}

        try:
            async with self._session.post(
                self._url,
                json=response,
                headers=self._headers,
            ) as response_obj:
                logger.debug(
                    "Sent response to MCP server: id=%s status=%d", request_id, response_obj.status
                )
        except aiohttp.ClientError as e:
            raise HttpTransportError(f"Failed to send response: {e}") from e

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
            raise HttpConnectionError("Not connected to MCP server")

        if not self._session:
            raise HttpConnectionError("Session not initialized")

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
                    "Sent error response to MCP server: id=%s code=%s status=%d",
                    request_id,
                    code,
                    response_obj.status,
                )
        except aiohttp.ClientError as e:
            raise HttpTransportError(f"Failed to send error response: {e}") from e

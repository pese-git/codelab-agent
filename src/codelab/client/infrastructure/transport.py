"""Абстракция и реализации транспортного слоя для ACP-клиента.

Модуль предоставляет:
- Transport протокол (интерфейс) для любых транспортов
- WebSocketTransport реализация на основе aiohttp
- Единый асинхронный API для клиентского транспорта

Пример использования:
    transport = WebSocketTransport(host="127.0.0.1", port=8765)
    async with transport:
        await transport.send_str(json_message)
        response = await transport.receive_text()
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any, Protocol

import structlog
from aiohttp import ClientSession, WSMsgType


class Transport(Protocol):
    """Интерфейс транспортного уровня для отправки/получения сообщений.

    Любая реализация транспорта должна поддерживать async context manager
    и методы send_str/receive_text для работы с JSON-сообщениями.

    Пример реализации:
        class MyTransport:
            async def __aenter__(self) -> MyTransport:
                ...
            async def __aexit__(self, *args) -> None:
                ...
            async def send_str(self, data: str) -> None:
                ...
            async def receive_text(self) -> str:
                ...
    """

    async def __aenter__(self) -> Transport:
        """Открывает транспортное соединение."""
        ...

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Закрывает транспортное соединение."""
        ...

    async def send_str(self, data: str) -> None:
        """Отправляет строку через транспорт.

        Args:
            data: JSON-строка для отправки

        Raises:
            RuntimeError: Если соединение закрыто или ошибка отправки
        """
        ...

    async def receive_text(self) -> str:
        """Получает строку из транспорта.

        Returns:
            JSON-строка от сервера

        Raises:
            RuntimeError: Если соединение закрыто или ошибка приема
        """
        ...


class WebSocketTransport:
    """WebSocket транспорт для ACP-клиента.

    Класс управляет WebSocket соединением через aiohttp и предоставляет
    унифицированный интерфейс отправки/получения сообщений.

    Пример использования:
        transport = WebSocketTransport(host="127.0.0.1", port=8765)
        async with transport:
            await transport.send_str('{"jsonrpc": "2.0", "id": 1, ...}')
            response = await transport.receive_text()
    """

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        path: str = "/acp/ws",
    ) -> None:
        """Инициализирует WebSocket транспорт с параметрами сервера.

        Args:
            host: IP-адрес или hostname сервера
            port: Порт сервера
            path: WebSocket путь на сервере (по умолчанию /acp/ws)

        Пример:
            transport = WebSocketTransport(host="localhost", port=8765)
        """
        self.host = host
        self.port = port
        self.path = path
        self.logger = structlog.get_logger("acp_client.transport.websocket")

        self._http_session: ClientSession | None = None
        self._ws: Any | None = None

    async def __aenter__(self) -> WebSocketTransport:
        """Открывает WebSocket соединение и возвращает сам транспорт.

        ВАЖНО: Если вызывается повторно на том же объекте (для переподключения),
        закрывает старую сессию перед созданием новой.

        Returns:
            Текущий экземпляр транспорта (self)

        Raises:
            RuntimeError: Если соединение не может быть установлено
        """
        url = f"ws://{self.host}:{self.port}{self.path}"
        try:
            # КРИТИЧНАЯ ЗАЩИТА: Закрываем старую сессию перед переподключением
            # Это предотвращает утечку ресурсов при повторном вызове __aenter__()
            if self._http_session is not None:
                try:
                    await self._http_session.close()
                    self.logger.debug("old_http_session_closed")
                except Exception as e:
                    self.logger.warning("error_closing_old_session", error=str(e))
                self._http_session = None

            # Если есть открытое WebSocket - закрываем его
            if self._ws is not None:
                try:
                    await self._ws.close()
                    self.logger.debug("old_websocket_closed")
                except Exception as e:
                    self.logger.warning("error_closing_old_websocket", error=str(e))
                self._ws = None

            # Создаем новую сессию и подключаемся
            self._http_session = ClientSession()
            self._ws = await self._http_session.ws_connect(url)
            self.logger.debug("websocket_connected", url=url)
        except Exception as e:
            # Очищаем ресурсы в случае ошибки
            if self._http_session is not None:
                with suppress(Exception):
                    await self._http_session.close()
                self._http_session = None
            self._ws = None
            msg = f"Failed to connect to WebSocket at {url}: {e}"
            self.logger.error("websocket_connection_failed", error=str(e), url=url)
            raise RuntimeError(msg) from e
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Закрывает WebSocket и HTTP-сессию.

        Гарантирует очистку ресурсов даже при возникновении исключений
        во время работы с соединением.

        Args:
            exc_type: Тип исключения (если оно возникло)
            exc_val: Значение исключения
            exc_tb: Traceback исключения
        """
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception as e:
                self.logger.warning("websocket_close_error", error=str(e))
            self._ws = None

        if self._http_session is not None:
            try:
                await self._http_session.close()
            except Exception as e:
                self.logger.warning("http_session_close_error", error=str(e))
            self._http_session = None

        self.logger.debug("websocket_disconnected")

    async def send_str(self, data: str) -> None:
        """Отправляет строку (JSON) через WebSocket.

        Args:
            data: JSON-строка для отправки

        Raises:
            RuntimeError: Если соединение не открыто или произошла ошибка отправки
        """
        if self._ws is None:
            raise RuntimeError("WebSocket connection is not open")

        try:
            await self._ws.send_str(data)
            self.logger.debug("message_sent", length=len(data))
        except Exception as e:
            msg = f"Failed to send message: {e}"
            self.logger.error("message_send_error", error=str(e))
            raise RuntimeError(msg) from e

    async def receive_text(self) -> str:
        """Получает строку (JSON) из WebSocket.

        Метод блокирует до получения текстового сообщения.
        Автоматически пропускает non-TEXT сообщения типа PING/PONG.

        Returns:
            JSON-строка от сервера

        Raises:
            RuntimeError: Если соединение не открыто, получено non-text сообщение
                         или произошла ошибка приема
        """
        if self._ws is None:
            raise RuntimeError("WebSocket connection is not open")

        try:
            message = await self._ws.receive()

            # Проверяем тип сообщения
            if message.type != WSMsgType.TEXT:
                msg = f"Unexpected WebSocket message type: {message.type}"
                self.logger.error("unexpected_message_type", type=message.type)
                raise RuntimeError(msg)

            self.logger.debug("message_received", length=len(message.data))
            return message.data
        except RuntimeError:
            raise
        except Exception as e:
            msg = f"Failed to receive message: {e}"
            self.logger.error("message_receive_error", error=str(e))
            raise RuntimeError(msg) from e

    def is_connected(self) -> bool:
        """Проверяет, открыто ли соединение.

        Returns:
            True если соединение активно, False иначе
        """
        connected = self._ws is not None and not self._ws.closed
        # Логируем только при обнаружении закрытого соединения для отладки disconnect проблем
        if not connected and self._ws is not None:
            self.logger.debug(
                "connection_check_failed",
                ws_exists=self._ws is not None,
                ws_closed=self._ws.closed if self._ws else None,
            )
        return connected

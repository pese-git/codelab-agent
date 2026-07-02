"""Абстракция WebSocket соединения.

Модуль определяет Protocol для WebSocket соединения и адаптер для aiohttp.
Это позволяет абстрагироваться от конкретной реализации WebSocket и упрощает
тестирование транспорта.

Пример использования:
    # В production коде
    connection = AiohttpWebSocketConnection(ws)
    transport = WebSocketTransport(connection, ...)

    # В тестах
    mock_connection = MockWebSocketConnection()
    transport = WebSocketTransport(mock_connection, ...)
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from aiohttp import WSMessage, web


@runtime_checkable
class WebSocketConnection(Protocol):
    """Протокол WebSocket соединения.

    Абстрагирует операции WebSocket, необходимые для транспорта.
    Позволяет использовать разные реализации (aiohttp, тестовые моки).
    """

    @property
    def closed(self) -> bool:
        """Проверяет, закрыто ли соединение."""
        ...

    async def send_str(self, data: str) -> None:
        """Отправляет строку через WebSocket."""
        ...

    async def send_json(self, data: dict) -> None:
        """Отправляет JSON через WebSocket."""
        ...

    async def close(self) -> None:
        """Закрывает WebSocket соединение."""
        ...

    def exception(self) -> BaseException | None:
        """Возвращает исключение соединения, если есть."""
        ...

    def __aiter__(self) -> AsyncIterator[WSMessage]:
        """Итератор по входящим сообщениям."""
        ...


class AiohttpWebSocketConnection:
    """Адаптер aiohttp.WebSocketResponse → WebSocketConnection.

    Обёртка над aiohttp WebSocket для использования в WebSocketTransport.
    Делегирует все операции базовому WebSocketResponse.
    """

    def __init__(self, ws: web.WebSocketResponse) -> None:
        """Инициализирует адаптер.

        Args:
            ws: aiohttp WebSocketResponse (уже prepared)
        """
        self._ws = ws

    @property
    def closed(self) -> bool:
        """Проверяет, закрыто ли соединение."""
        return self._ws.closed

    async def send_str(self, data: str) -> None:
        """Отправляет строку через WebSocket."""
        await self._ws.send_str(data)

    async def send_json(self, data: dict) -> None:
        """Отправляет JSON через WebSocket."""
        await self._ws.send_json(data)

    async def close(self) -> None:
        """Закрывает WebSocket соединение."""
        await self._ws.close()

    def exception(self) -> BaseException | None:
        """Возвращает исключение соединения, если есть."""
        return self._ws.exception()

    def __aiter__(self) -> AsyncIterator[WSMessage]:
        """Итератор по входящим сообщениям."""
        return self._ws.__aiter__()

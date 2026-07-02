"""Транспортный слой ACP-сервера.

Пакет предоставляет абстракцию транспорта и реализации для различных
механизмов коммуникации (WebSocket, stdio).

Архитектура:
- AcpServerTransport — протокол (интерфейс) транспорта
- WebSocketConnection — протокол WebSocket соединения
- AiohttpWebSocketConnection — адаптер aiohttp WebSocket
- WebSocketTransport — реализация поверх WebSocketConnection
- StdioServerTransport — реализация поверх stdin/stdout
- stdio_runner — функция запуска сервера в stdio режиме

Пример использования:
    # WebSocket транспорт
    connection = AiohttpWebSocketConnection(ws)
    transport = WebSocketTransport(connection, ...)
    await transport.run(on_message=protocol.handle)

    # Stdio транспорт
    transport = StdioServerTransport()
    await transport.run(on_message=protocol.handle)
"""

from .base import AcpServerTransport
from .stdio import StdioServerTransport
from .websocket import WebSocketTransport
from .websocket_connection import AiohttpWebSocketConnection, WebSocketConnection

__all__ = [
    "AcpServerTransport",
    "AiohttpWebSocketConnection",
    "StdioServerTransport",
    "WebSocketConnection",
    "WebSocketTransport",
]

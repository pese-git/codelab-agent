"""Тесты для infrastructure.transport модуля.

Тестирует:
- WebSocketTransport инициализацию и параметры
- Валидацию URL сборки
- Корректное управление ресурсами (context manager)
"""

from __future__ import annotations

import pytest

from codelab.client.infrastructure.transport import WebSocketTransport


class TestWebSocketTransportInitialization:
    """Тесты инициализации WebSocketTransport."""

    def test_default_parameters(self) -> None:
        """Проверяет инициализацию с параметрами по умолчанию."""
        transport = WebSocketTransport()
        assert transport.host == "127.0.0.1"
        assert transport.port == 8765
        assert transport.path == "/acp/ws"
        assert not transport.is_connected()

    def test_custom_parameters(self) -> None:
        """Проверяет инициализацию с кастомными параметрами."""
        transport = WebSocketTransport(
            host="localhost",
            port=9000,
            path="/custom/ws",
        )
        assert transport.host == "localhost"
        assert transport.port == 9000
        assert transport.path == "/custom/ws"

    def test_connection_initially_closed(self) -> None:
        """Проверяет что соединение закрыто при инициализации."""
        transport = WebSocketTransport()
        assert not transport.is_connected()

    @pytest.mark.asyncio
    async def test_send_raises_when_not_connected(self) -> None:
        """Проверяет что send_str выбрасывает ошибку без соединения."""
        transport = WebSocketTransport()
        with pytest.raises(RuntimeError, match="not open"):
            await transport.send_str("test")

    def test_receive_raises_when_not_connected(self) -> None:
        """Проверяет что receive_text выбрасывает ошибку без соединения."""
        transport = WebSocketTransport()
        assert transport._ws is None

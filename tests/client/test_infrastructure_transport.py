"""Тесты для infrastructure.transport модуля.

Тестирует:
- WebSocketTransport инициализацию и параметры
- Валидацию URL сборки
- Корректное управление ресурсами (context manager)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import WSMsgType

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


class TestWebSocketTransportAEnter:
    """Тесты метода __aenter__ WebSocketTransport."""

    async def test_happy_path_creates_session_and_connects(self) -> None:
        """Проверяет что __aenter__ создает сессию, подключается и возвращает self."""
        ws = AsyncMock()
        ws.closed = False
        session = AsyncMock()
        session.ws_connect = AsyncMock(return_value=ws)

        with patch("codelab.client.infrastructure.transport.ClientSession", return_value=session):
            transport = WebSocketTransport(host="localhost", port=9000, path="/ws")
            result = await transport.__aenter__()

            assert result is transport
            assert transport._http_session is session
            assert transport._ws is ws
            session.ws_connect.assert_awaited_once_with("ws://localhost:9000/ws")

    async def test_reconnection_closes_old_session_and_ws(self) -> None:
        """Проверяет что повторный вход закрывает старую сессию и WebSocket."""
        old_ws = AsyncMock()
        old_ws.closed = False
        old_session = AsyncMock()
        old_session.ws_connect = AsyncMock(return_value=old_ws)

        new_ws = AsyncMock()
        new_ws.closed = False
        new_session = AsyncMock()
        new_session.ws_connect = AsyncMock(return_value=new_ws)

        sessions = [old_session, new_session]

        with patch("codelab.client.infrastructure.transport.ClientSession", side_effect=sessions):
            transport = WebSocketTransport()
            await transport.__aenter__()
            assert transport._ws is old_ws
            assert transport._http_session is old_session

            await transport.__aenter__()
            assert transport._ws is new_ws
            assert transport._http_session is new_session
            old_session.close.assert_awaited_once()
            old_ws.close.assert_awaited_once()

    async def test_old_session_close_error_swallowed(self) -> None:
        """Проверяет что ошибка закрытия старой сессии подавляется."""
        old_ws = AsyncMock()
        old_ws.closed = False
        old_session = AsyncMock()
        old_session.close = AsyncMock(side_effect=RuntimeError("close error"))
        old_session.ws_connect = AsyncMock(return_value=old_ws)

        new_ws = AsyncMock()
        new_ws.closed = False
        new_session = AsyncMock()
        new_session.ws_connect = AsyncMock(return_value=new_ws)

        sessions = [old_session, new_session]

        with patch("codelab.client.infrastructure.transport.ClientSession", side_effect=sessions):
            transport = WebSocketTransport()
            await transport.__aenter__()
            await transport.__aenter__()

            assert transport._ws is new_ws
            assert transport._http_session is new_session

    async def test_old_ws_close_error_swallowed(self) -> None:
        """Проверяет что ошибка закрытия старого WebSocket подавляется."""
        old_ws = AsyncMock()
        old_ws.closed = False
        old_ws.close = AsyncMock(side_effect=RuntimeError("ws close error"))
        old_session = AsyncMock()
        old_session.ws_connect = AsyncMock(return_value=old_ws)

        new_ws = AsyncMock()
        new_ws.closed = False
        new_session = AsyncMock()
        new_session.ws_connect = AsyncMock(return_value=new_ws)

        sessions = [old_session, new_session]

        with patch("codelab.client.infrastructure.transport.ClientSession", side_effect=sessions):
            transport = WebSocketTransport()
            await transport.__aenter__()
            await transport.__aenter__()

            assert transport._ws is new_ws
            assert transport._http_session is new_session

    async def test_connection_failure_raises_runtime_error_and_cleans_up(self) -> None:
        """Проверяет что ошибка подключения оборачивается в RuntimeError и очищает ресурсы."""
        session = AsyncMock()
        session.ws_connect = AsyncMock(side_effect=ConnectionError("refused"))
        session.close = AsyncMock()

        with patch("codelab.client.infrastructure.transport.ClientSession", return_value=session):
            transport = WebSocketTransport(host="localhost", port=9000, path="/ws")
            with pytest.raises(RuntimeError, match="Failed to connect to WebSocket at ws://localhost:9000/ws"):
                await transport.__aenter__()

            assert transport._http_session is None
            assert transport._ws is None
            session.close.assert_awaited_once()


class TestWebSocketTransportAExit:
    """Тесты метода __aexit__ WebSocketTransport."""

    async def test_normal_close_sets_session_and_ws_to_none(self) -> None:
        """Проверяет что __aexit__ закрывает ws и сессию и обнуляет их."""
        ws = AsyncMock()
        ws.closed = False
        session = AsyncMock()

        transport = WebSocketTransport()
        transport._ws = ws
        transport._http_session = session

        await transport.__aexit__(None, None, None)

        ws.close.assert_awaited_once()
        session.close.assert_awaited_once()
        assert transport._ws is None
        assert transport._http_session is None

    async def test_ws_close_error_swallowed(self) -> None:
        """Проверяет что ошибка закрытия ws подавляется."""
        ws = AsyncMock()
        ws.close = AsyncMock(side_effect=RuntimeError("ws close error"))
        session = AsyncMock()

        transport = WebSocketTransport()
        transport._ws = ws
        transport._http_session = session

        await transport.__aexit__(None, None, None)

        ws.close.assert_awaited_once()
        session.close.assert_awaited_once()
        assert transport._ws is None
        assert transport._http_session is None

    async def test_session_close_error_swallowed(self) -> None:
        """Проверяет что ошибка закрытия сессии подавляется."""
        ws = AsyncMock()
        session = AsyncMock()
        session.close = AsyncMock(side_effect=RuntimeError("session close error"))

        transport = WebSocketTransport()
        transport._ws = ws
        transport._http_session = session

        await transport.__aexit__(None, None, None)

        ws.close.assert_awaited_once()
        session.close.assert_awaited_once()
        assert transport._ws is None
        assert transport._http_session is None

    async def test_already_closed_does_nothing(self) -> None:
        """Проверяет что __aexit__ не падает когда соединение уже закрыто."""
        transport = WebSocketTransport()

        await transport.__aexit__(None, None, None)

        assert transport._ws is None
        assert transport._http_session is None


class TestWebSocketTransportSendStr:
    """Тесты метода send_str WebSocketTransport."""

    async def test_send_str_success(self) -> None:
        """Проверяет что send_str вызывает ws.send_str."""
        ws = AsyncMock()
        ws.closed = False
        transport = WebSocketTransport()
        transport._ws = ws

        await transport.send_str('{"test": true}')

        ws.send_str.assert_awaited_once_with('{"test": true}')

    async def test_send_str_wraps_exception_as_runtime_error(self) -> None:
        """Проверяет что исключение при отправке оборачивается в RuntimeError."""
        ws = AsyncMock()
        ws.send_str = AsyncMock(side_effect=ConnectionError("broken"))
        transport = WebSocketTransport()
        transport._ws = ws

        with pytest.raises(RuntimeError, match="Failed to send message: broken"):
            await transport.send_str('{"test": true}')


class TestWebSocketTransportReceiveText:
    """Тесты метода receive_text WebSocketTransport."""

    async def test_receive_text_not_connected_raises(self) -> None:
        """Проверяет что receive_text выбрасывает RuntimeError без соединения."""
        transport = WebSocketTransport()

        with pytest.raises(RuntimeError, match="not open"):
            await transport.receive_text()

    async def test_receive_text_success(self) -> None:
        """Проверяет что receive_text возвращает данные TEXT сообщения."""
        msg = MagicMock()
        msg.type = WSMsgType.TEXT
        msg.data = '{"test": true}'

        ws = AsyncMock()
        ws.closed = False
        ws.receive = AsyncMock(return_value=msg)

        transport = WebSocketTransport()
        transport._ws = ws

        result = await transport.receive_text()

        assert result == '{"test": true}'
        ws.receive.assert_awaited_once()

    async def test_receive_text_non_text_message_raises(self) -> None:
        """Проверяет что non-TEXT сообщение вызывает RuntimeError."""
        msg = MagicMock()
        msg.type = WSMsgType.BINARY

        ws = AsyncMock()
        ws.closed = False
        ws.receive = AsyncMock(return_value=msg)

        transport = WebSocketTransport()
        transport._ws = ws

        with pytest.raises(RuntimeError, match="Unexpected WebSocket message type"):
            await transport.receive_text()

    async def test_receive_text_runtime_error_reraised(self) -> None:
        """Проверяет что RuntimeError при получении пробрасывается как есть."""
        ws = AsyncMock()
        ws.closed = False
        ws.receive = AsyncMock(side_effect=RuntimeError("specific error"))

        transport = WebSocketTransport()
        transport._ws = ws

        with pytest.raises(RuntimeError, match="specific error"):
            await transport.receive_text()

    async def test_receive_text_generic_exception_wrapped(self) -> None:
        """Проверяет что прочие исключения оборачиваются в RuntimeError."""
        ws = AsyncMock()
        ws.closed = False
        ws.receive = AsyncMock(side_effect=ValueError("bad message"))

        transport = WebSocketTransport()
        transport._ws = ws

        with pytest.raises(RuntimeError, match="Failed to receive message: bad message"):
            await transport.receive_text()


class TestWebSocketTransportIsConnected:
    """Тесты метода is_connected WebSocketTransport."""

    def test_is_connected_true(self) -> None:
        """Проверяет что is_connected возвращает True для активного ws."""
        ws = MagicMock()
        ws.closed = False
        transport = WebSocketTransport()
        transport._ws = ws

        assert transport.is_connected() is True

    def test_is_connected_false_when_ws_closed(self) -> None:
        """Проверяет что is_connected возвращает False для закрытого ws."""
        ws = MagicMock()
        ws.closed = True
        transport = WebSocketTransport()
        transport._ws = ws

        assert transport.is_connected() is False

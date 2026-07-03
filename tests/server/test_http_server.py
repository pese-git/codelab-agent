"""Тесты для ACPHttpServer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from codelab.server.config import AppConfig
from codelab.server.http_server import ACPHttpServer


class TestInit:
    """Тесты инициализации ACPHttpServer."""

    def test_default_config_when_config_is_none(self) -> None:
        """При config=None должен создаваться конфигурация по умолчанию."""
        server = ACPHttpServer()

        assert isinstance(server.config, AppConfig)

    def test_trace_messages_true(self) -> None:
        """Параметр trace_messages=True должен сохраняться в атрибуте."""
        server = ACPHttpServer(trace_messages=True)

        assert server.trace_messages is True

    def test_host_and_port_stored(self) -> None:
        """Host и port сохраняются в атрибутах."""
        server = ACPHttpServer(host="192.168.1.1", port=9000)

        assert server.host == "192.168.1.1"
        assert server.port == 9000

    def test_enable_web_default_true(self) -> None:
        """enable_web по умолчанию True."""
        server = ACPHttpServer()

        assert server.enable_web is True

    def test_enable_web_false(self) -> None:
        """enable_web=False сохраняется."""
        server = ACPHttpServer(enable_web=False)

        assert server.enable_web is False

    def test_web_ui_manager_none_initially(self) -> None:
        """_web_ui_manager изначально None."""
        server = ACPHttpServer()

        assert server._web_ui_manager is None


class TestHandleWebUIRequest:
    """Тесты обработчика HTTP-запроса к корневому пути Web UI."""

    async def test_returns_404_when_web_ui_manager_none(self) -> None:
        """Возвращает 404 когда WebUIManager не инициализирован."""
        server = ACPHttpServer()
        request = MagicMock()

        response = await server.handle_web_ui_request(request)

        assert response.status == 404

    async def test_delegates_to_web_ui_manager(self) -> None:
        """Делегирует обработку WebUIManager."""
        server = ACPHttpServer()
        server._web_ui_manager = MagicMock()
        server._web_ui_manager.get_response.return_value = MagicMock(status=200)
        request = MagicMock()

        response = await server.handle_web_ui_request(request)

        server._web_ui_manager.get_response.assert_called_once()
        assert response.status == 200


class TestHandleWSRequest:
    """Тесты обработчика WebSocket-запроса."""

    async def test_returns_websocket_response(self) -> None:
        """Возвращает WebSocketResponse."""
        server = ACPHttpServer()
        server._app_container = MagicMock()

        ws = MagicMock()
        ws.prepare = AsyncMock()
        ws.close = AsyncMock()

        with patch("codelab.server.http_server.web.WebSocketResponse", return_value=ws):
            with patch("codelab.server.http_server.WebSocketTransport") as mock_transport:
                mock_transport.return_value.run = AsyncMock()
                request = MagicMock()
                request.remote = "127.0.0.1"

                result = await server.handle_ws_request(request)

        assert result is ws

    async def test_closes_ws_when_container_none(self) -> None:
        """Закрывает WebSocket когда контейнер не инициализирован."""
        server = ACPHttpServer()
        server._app_container = None

        ws = MagicMock()
        ws.prepare = AsyncMock()
        ws.close = AsyncMock()

        with patch("codelab.server.http_server.web.WebSocketResponse", return_value=ws):
            request = MagicMock()
            request.remote = "127.0.0.1"

            result = await server.handle_ws_request(request)

        ws.close.assert_called_once_with(code=1011, message=b"Server not initialized")
        assert result is ws

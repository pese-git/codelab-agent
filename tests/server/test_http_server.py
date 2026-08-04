"""Тесты для ACPHttpServer."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


class TestRunWebUiOwnership:
    """Порядок спавна Web UI относительно bind'а (P2-53)."""

    @staticmethod
    def _patched_run(server: ACPHttpServer, site: MagicMock):
        """Собрать окружение для run(): DI, runner и site — заглушки."""
        container = MagicMock()
        container.get = AsyncMock()
        container.close = AsyncMock()

        runner = MagicMock()
        runner.setup = AsyncMock()
        runner.cleanup = AsyncMock()

        return (
            patch("codelab.server.http_server.make_container", return_value=container),
            patch("codelab.server.http_server.web.AppRunner", return_value=runner),
            patch("codelab.server.http_server.web.TCPSite", return_value=site),
        )

    async def test_no_child_spawned_when_bind_fails(self) -> None:
        """Занятый порт не должен оставлять подпроцесс Web UI без владельца."""
        server = ACPHttpServer(enable_web=True)
        manager = MagicMock()
        site = MagicMock()
        site.start = AsyncMock(side_effect=OSError("address already in use"))

        patch_container, patch_runner, patch_site = self._patched_run(server, site)
        with patch_container, patch_runner, patch_site:
            with patch("codelab.server.http_server.WebUIManager", return_value=manager):
                with pytest.raises(OSError, match="address already in use"):
                    await server.run()

        manager.start_subprocess.assert_not_called()
        manager.stop_subprocess.assert_called_once()

    async def test_child_spawned_only_after_successful_bind(self) -> None:
        """Подпроцесс запускается после site.start(), а не до него."""
        server = ACPHttpServer(enable_web=True)
        order: list[str] = []

        manager = MagicMock()
        manager.start_subprocess.side_effect = lambda: order.append("spawn") or True
        manager.web_ui_url = "http://127.0.0.1:9080/"

        site = MagicMock()

        async def _start() -> None:
            order.append("bind")

        site.start = AsyncMock(side_effect=_start)

        patch_container, patch_runner, patch_site = self._patched_run(server, site)
        with patch_container, patch_runner, patch_site:
            with patch("codelab.server.http_server.WebUIManager", return_value=manager):
                with patch(
                    "codelab.server.http_server.asyncio.sleep",
                    side_effect=asyncio.CancelledError,
                ):
                    with pytest.raises(asyncio.CancelledError):
                        await server.run()

        assert order == ["bind", "spawn"]
        manager.stop_subprocess.assert_called_once()

    async def test_web_disabled_spawns_nothing(self) -> None:
        """С выключенным Web UI менеджер не создаётся вовсе."""
        server = ACPHttpServer(enable_web=False)
        site = MagicMock()
        site.start = AsyncMock()

        patch_container, patch_runner, patch_site = self._patched_run(server, site)
        with patch_container, patch_runner, patch_site:
            with patch("codelab.server.http_server.WebUIManager") as manager_cls:
                with patch(
                    "codelab.server.http_server.asyncio.sleep",
                    side_effect=asyncio.CancelledError,
                ):
                    with pytest.raises(asyncio.CancelledError):
                        await server.run()

        manager_cls.assert_not_called()

"""Дополнительные тесты покрытия оставшихся непокрытыми участков ACPHttpServer."""

from __future__ import annotations

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codelab.server.http_server import ACPHttpServer
from codelab.server.messages import ACPMessage


class TestValidateHost:
    """Тесты валидации хоста."""

    def test_valid_ip_returns_unchanged(self) -> None:
        """Корректный IP-адрес возвращается без изменений."""
        server = ACPHttpServer()

        result = server._validate_host("127.0.0.1")

        assert result == "127.0.0.1"

    def test_valid_hostname_returns_unchanged(self) -> None:
        """Корректное имя хоста возвращается без изменений."""
        server = ACPHttpServer()

        result = server._validate_host("localhost")

        assert result == "localhost"

    def test_invalid_host_raises_value_error(self) -> None:
        """Некорректный хост вызывает ValueError."""
        server = ACPHttpServer()

        with pytest.raises(ValueError, match="Invalid host"):
            server._validate_host("not a host!")


class TestStartWebUISubprocess:
    """Тесты запуска subprocess Web UI."""

    @patch("codelab.server.web_app.is_web_ui_available", return_value=False)
    def test_unavailable_returns_false(self, mock_available: MagicMock) -> None:
        """Если textual-web недоступен, метод возвращает False."""
        server = ACPHttpServer()

        result = server._start_web_ui_subprocess()

        assert result is False

    @patch("codelab.server.web_app.is_web_ui_available", return_value=True)
    @patch("codelab.server.http_server.subprocess.Popen")
    def test_success_starts_process(
        self,
        mock_popen: MagicMock,
        mock_available: MagicMock,
    ) -> None:
        """Успешный запуск subprocess сохраняет процесс и URL."""
        server = ACPHttpServer(host="127.0.0.1", port=8080)
        process = MagicMock()
        process.pid = 12345
        mock_popen.return_value = process

        result = server._start_web_ui_subprocess()

        assert result is True
        assert server._web_ui_process is process
        assert server._web_ui_url == "http://127.0.0.1:9080/"
        mock_popen.assert_called_once()
        _, kwargs = mock_popen.call_args
        assert kwargs["env"]["CODELAB_WS_HOST"] == "127.0.0.1"
        assert kwargs["env"]["CODELAB_WS_PORT"] == "8080"

    @patch("codelab.server.web_app.is_web_ui_available", return_value=True)
    @patch("codelab.server.http_server.subprocess.Popen", side_effect=OSError("boom"))
    def test_exception_returns_false(
        self,
        mock_popen: MagicMock,
        mock_available: MagicMock,
    ) -> None:
        """При ошибке запуска subprocess возвращается False."""
        server = ACPHttpServer(host="127.0.0.1", port=8080)

        result = server._start_web_ui_subprocess()

        assert result is False
        assert server._web_ui_process is None


class TestRun:
    """Тесты запуска HTTP-сервера."""

    @patch("codelab.server.http_server.asyncio.sleep", side_effect=asyncio.CancelledError)
    @patch("codelab.server.http_server.web.TCPSite")
    @patch("codelab.server.http_server.web.AppRunner")
    @patch("codelab.server.http_server.make_container")
    async def test_run_lifecycle_without_web(
        self,
        mock_make_container: MagicMock,
        mock_runner_cls: MagicMock,
        mock_site_cls: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        """Полный жизненный цикл run без Web UI корректно останавливается."""
        server = ACPHttpServer(host="127.0.0.1", port=8080, enable_web=False)
        container = AsyncMock()
        mock_make_container.return_value = container
        runner = MagicMock()
        runner.setup = AsyncMock()
        runner.cleanup = AsyncMock()
        mock_runner_cls.return_value = runner
        site = MagicMock()
        site.start = AsyncMock()
        mock_site_cls.return_value = site

        with pytest.raises(asyncio.CancelledError):
            await server.run()

        assert server.storage is not None
        mock_make_container.assert_called_once_with(
            config=server.config,
            storage=server.storage,
            require_auth=server.require_auth,
            auth_api_key=server.auth_api_key,
            trace_messages=server.trace_messages,
        )
        runner.setup.assert_awaited_once()
        site.start.assert_awaited_once_with()
        runner.cleanup.assert_awaited_once()
        container.close.assert_awaited_once()

    @patch("codelab.server.http_server.asyncio.sleep", side_effect=asyncio.CancelledError)
    @patch("codelab.server.http_server.web.TCPSite")
    @patch("codelab.server.http_server.web.AppRunner")
    @patch("codelab.server.http_server.make_container")
    @patch.object(ACPHttpServer, "_start_web_ui_subprocess", return_value=True)
    async def test_run_with_web_started(
        self,
        mock_start_web: MagicMock,
        mock_make_container: MagicMock,
        mock_runner_cls: MagicMock,
        mock_site_cls: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        """Запуск с enable_web=True и успешно стартовавшим Web UI."""
        server = ACPHttpServer(host="127.0.0.1", port=8080, enable_web=True)
        server._web_ui_url = "http://127.0.0.1:9080/"
        container = AsyncMock()
        mock_make_container.return_value = container
        runner = MagicMock()
        runner.setup = AsyncMock()
        runner.cleanup = AsyncMock()
        mock_runner_cls.return_value = runner
        site = MagicMock()
        site.start = AsyncMock()
        mock_site_cls.return_value = site

        with pytest.raises(asyncio.CancelledError):
            await server.run()

        mock_start_web.assert_called_once()
        runner.cleanup.assert_awaited_once()

    @patch("codelab.server.http_server.asyncio.sleep", side_effect=asyncio.CancelledError)
    @patch("codelab.server.http_server.web.TCPSite")
    @patch("codelab.server.http_server.web.AppRunner")
    @patch("codelab.server.http_server.make_container")
    @patch.object(ACPHttpServer, "_start_web_ui_subprocess", return_value=False)
    async def test_run_with_web_fallback(
        self,
        mock_start_web: MagicMock,
        mock_make_container: MagicMock,
        mock_runner_cls: MagicMock,
        mock_site_cls: MagicMock,
        mock_sleep: MagicMock,
    ) -> None:
        """Запуск с enable_web=True, но Web UI не удалось стартовать."""
        server = ACPHttpServer(host="127.0.0.1", port=8080, enable_web=True)
        container = AsyncMock()
        mock_make_container.return_value = container
        runner = MagicMock()
        runner.setup = AsyncMock()
        runner.cleanup = AsyncMock()
        mock_runner_cls.return_value = runner
        site = MagicMock()
        site.start = AsyncMock()
        mock_site_cls.return_value = site

        with pytest.raises(asyncio.CancelledError):
            await server.run()

        mock_start_web.assert_called_once()
        runner.cleanup.assert_awaited_once()


class TestHandleWSRequest:
    """Тесты обработчика WebSocket-запроса."""

    @patch("codelab.server.http_server.web.WebSocketResponse")
    async def test_container_not_initialized_closes_ws(
        self,
        mock_ws_cls: MagicMock,
    ) -> None:
        """Если DI-контейнер не инициализирован, WebSocket закрывается."""
        server = ACPHttpServer()
        ws = MagicMock()
        ws.prepare = AsyncMock()
        ws.close = AsyncMock()
        mock_ws_cls.return_value = ws
        request = MagicMock()
        request.remote = "127.0.0.1"

        result = await server.handle_ws_request(request)

        assert result is ws
        ws.prepare.assert_awaited_once_with(request)
        ws.close.assert_awaited_once_with(code=1011, message=b"Server not initialized")

    @patch("codelab.server.http_server.WebSocketTransport")
    @patch("codelab.server.http_server.web.WebSocketResponse")
    async def test_container_initialized_runs_transport(
        self,
        mock_ws_cls: MagicMock,
        mock_transport_cls: MagicMock,
    ) -> None:
        """При инициализированном контейнере создаётся и запускается транспорт."""
        server = ACPHttpServer()
        server._app_container = AsyncMock()
        ws = MagicMock()
        ws.prepare = AsyncMock()
        ws.closed = False
        mock_ws_cls.return_value = ws
        transport = MagicMock()
        transport.run = AsyncMock()
        mock_transport_cls.return_value = transport
        request = MagicMock()
        request.remote = "127.0.0.1"

        result = await server.handle_ws_request(request)

        assert result is ws
        mock_transport_cls.assert_called_once()
        transport.run.assert_awaited_once()


class TestCompleteDeferredPromptRemaining:
    """Тесты оставшихся веток завершения отложенного prompt."""

    @patch(
        "codelab.server.http_server.asyncio.sleep",
        side_effect=asyncio.CancelledError,
    )
    async def test_cancelled_error_load_session_raises(
        self,
        mock_sleep: MagicMock,
    ) -> None:
        """CancelledError при ошибке load_session логирует ошибку."""
        server = ACPHttpServer()
        ws = MagicMock()
        ws.closed = False
        ws.send_str = AsyncMock()
        protocol = MagicMock()
        protocol._storage.load_session = AsyncMock(side_effect=RuntimeError("load failed"))
        tasks = cast(dict[str, asyncio.Task[None]], {"sess_1": MagicMock()})

        await server._complete_deferred_prompt(
            ws=ws,
            protocol=protocol,
            session_id="sess_1",
            deferred_prompt_tasks=tasks,
            connection_id="conn_1",
        )

        protocol._storage.load_session.assert_awaited_once_with("sess_1")
        ws.send_str.assert_not_awaited()
        assert "sess_1" not in tasks

    @patch("codelab.server.http_server.asyncio.sleep", new_callable=AsyncMock)
    async def test_unexpected_exception_in_main_body(
        self,
        mock_sleep: AsyncMock,
    ) -> None:
        """Непредвиденное исключение в основном теле логируется."""
        server = ACPHttpServer()
        ws = MagicMock()
        ws.closed = False
        ws.send_str = AsyncMock()

        class BrokenClosed:
            """Мок объекта с ломающимся свойством closed."""

            @property
            def closed(self) -> bool:
                raise RuntimeError("ws broken")

        ws = cast(MagicMock, BrokenClosed())
        protocol = MagicMock()
        protocol.complete_active_turn = AsyncMock(
            return_value=ACPMessage.response("req_1", {}),
        )
        tasks = cast(dict[str, asyncio.Task[None]], {"sess_1": MagicMock()})

        await server._complete_deferred_prompt(
            ws=ws,  # type: ignore[arg-type]
            protocol=protocol,
            session_id="sess_1",
            deferred_prompt_tasks=tasks,
            connection_id="conn_1",
        )

        assert "sess_1" not in tasks

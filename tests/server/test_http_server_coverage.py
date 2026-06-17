"""Тесты покрытия непокрытых методов ACPHttpServer."""

from __future__ import annotations

import asyncio
import subprocess
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import web

from codelab.server.config import AppConfig
from codelab.server.http_server import ACPHttpServer
from codelab.server.messages import ACPMessage


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


class TestStopWebUISubprocess:
    """Тесты остановки subprocess с Web UI."""

    def test_no_process_is_noop(self) -> None:
        """Если процесса нет, метод не делает ничего и не падает."""
        server = ACPHttpServer()

        server._stop_web_ui_subprocess()

        assert server._web_ui_process is None

    def test_terminate_success(self) -> None:
        """При успешном terminate+wait процесс сбрасывается в None."""
        server = ACPHttpServer()
        process = MagicMock()
        process.terminate = MagicMock()
        process.wait = MagicMock()
        server._web_ui_process = process

        server._stop_web_ui_subprocess()

        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=5)
        assert server._web_ui_process is None

    def test_terminate_timeout_then_kill(self) -> None:
        """При TimeoutExpired должен вызываться kill, процесс обнулён."""
        server = ACPHttpServer()
        process = MagicMock()
        process.terminate = MagicMock()
        process.wait = MagicMock(
            side_effect=subprocess.TimeoutExpired(cmd="cmd", timeout=5),
        )
        process.kill = MagicMock()
        server._web_ui_process = process

        server._stop_web_ui_subprocess()

        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=5)
        process.kill.assert_called_once()
        assert server._web_ui_process is None

    def test_kill_also_fails_still_clears_process(self) -> None:
        """Даже если и terminate, и kill падают, процесс сбрасывается в None."""
        server = ACPHttpServer()
        process = MagicMock()
        process.terminate = MagicMock(side_effect=ProcessLookupError("no process"))
        process.kill = MagicMock(side_effect=OSError("kill failed"))
        server._web_ui_process = process

        server._stop_web_ui_subprocess()

        assert server._web_ui_process is None


class TestHandleWebUIRequest:
    """Тесты обработчика HTTP-запроса к корневому пути Web UI."""

    async def test_subprocess_running_returns_iframe_html(self) -> None:
        """Запущенный subprocess возвращает HTML-страницу с iframe."""
        server = ACPHttpServer(host="127.0.0.1", port=8080)
        process = MagicMock()
        process.poll.return_value = None
        server._web_ui_process = process
        server._web_ui_url = "http://127.0.0.1:9080/"
        request = MagicMock()

        response = await server.handle_web_ui_request(request)

        assert isinstance(response, web.Response)
        assert response.content_type == "text/html"
        assert response.text is not None
        assert "<iframe" in response.text
        assert "http://127.0.0.1:9080/" in response.text

    @patch("codelab.server.web_app.is_web_ui_available", return_value=True)
    async def test_subprocess_dead_falls_through_to_manual_start(
        self, mock_available: MagicMock,
    ) -> None:
        """Мёртвый subprocess приводит к HTML с инструкцией ручного запуска."""
        server = ACPHttpServer(host="127.0.0.1", port=8080)
        process = MagicMock()
        process.poll.return_value = 1
        server._web_ui_process = process
        request = MagicMock()

        response = await server.handle_web_ui_request(request)

        assert response.content_type == "text/html"
        assert response.text is not None
        assert "Web UI не запущен" in response.text
        assert "textual-web --run" in response.text

    @patch("codelab.server.web_app.is_web_ui_available", return_value=True)
    async def test_no_subprocess_but_available_returns_manual_start_html(
        self, mock_available: MagicMock,
    ) -> None:
        """textual-web доступен, но subprocess не запущен — показываем инструкцию."""
        server = ACPHttpServer(host="127.0.0.1", port=8080)
        server._web_ui_process = None
        request = MagicMock()

        response = await server.handle_web_ui_request(request)

        assert response.content_type == "text/html"
        assert response.text is not None
        assert "Web UI не запущен" in response.text
        assert "codelab connect" in response.text

    @patch("codelab.server.web_app.is_web_ui_available", return_value=False)
    @patch(
        "codelab.server.web_app.get_fallback_html",
        return_value="<fallback>html</fallback>",
    )
    async def test_unavailable_returns_fallback_html(
        self,
        mock_fallback: MagicMock,
        mock_available: MagicMock,
    ) -> None:
        """Если Web UI недоступен — возвращаем fallback HTML."""
        server = ACPHttpServer(host="127.0.0.1", port=8080)
        request = MagicMock()

        response = await server.handle_web_ui_request(request)

        assert response.content_type == "text/html"
        assert response.text == "<fallback>html</fallback>"
        mock_fallback.assert_called_once_with("127.0.0.1", 8080)


class TestCompleteDeferredPrompt:
    """Тесты завершения отложенного prompt."""

    @patch("codelab.server.http_server.asyncio.sleep", new_callable=AsyncMock)
    async def test_success_sends_response(self, mock_sleep: AsyncMock) -> None:
        """Успешное complete_active_turn отправляет response по WebSocket."""
        server = ACPHttpServer()
        ws = MagicMock()
        ws.closed = False
        ws.send_str = AsyncMock()
        protocol = MagicMock()
        response_msg = ACPMessage.response("req_1", {"stopReason": "end_turn"})
        protocol.complete_active_turn = AsyncMock(return_value=response_msg)
        tasks = cast(dict[str, asyncio.Task[None]], {"sess_1": MagicMock()})

        await server._complete_deferred_prompt(
            ws=ws,
            protocol=protocol,
            session_id="sess_1",
            deferred_prompt_tasks=tasks,
            connection_id="conn_1",
        )

        protocol.complete_active_turn.assert_awaited_once_with(
            "sess_1", stop_reason="end_turn",
        )
        ws.send_str.assert_awaited_once_with(response_msg.to_json())
        assert "sess_1" not in tasks

    @patch("codelab.server.http_server.asyncio.sleep", new_callable=AsyncMock)
    async def test_timeout_error_no_send(self, mock_sleep: AsyncMock) -> None:
        """При TimeoutError response не отправляется, задача удаляется."""
        server = ACPHttpServer()
        ws = MagicMock()
        ws.closed = False
        ws.send_str = AsyncMock()
        protocol = MagicMock()
        protocol.complete_active_turn = AsyncMock(side_effect=TimeoutError)
        tasks = cast(dict[str, asyncio.Task[None]], {"sess_1": MagicMock()})

        await server._complete_deferred_prompt(
            ws=ws,
            protocol=protocol,
            session_id="sess_1",
            deferred_prompt_tasks=tasks,
            connection_id="conn_1",
        )

        ws.send_str.assert_not_awaited()
        assert "sess_1" not in tasks

    @patch("codelab.server.http_server.asyncio.sleep", new_callable=AsyncMock)
    async def test_generic_exception_no_send(self, mock_sleep: AsyncMock) -> None:
        """Generic Exception не отправляет response, задача удаляется."""
        server = ACPHttpServer()
        ws = MagicMock()
        ws.closed = False
        ws.send_str = AsyncMock()
        protocol = MagicMock()
        protocol.complete_active_turn = AsyncMock(side_effect=RuntimeError("boom"))
        tasks = cast(dict[str, asyncio.Task[None]], {"sess_1": MagicMock()})

        await server._complete_deferred_prompt(
            ws=ws,
            protocol=protocol,
            session_id="sess_1",
            deferred_prompt_tasks=tasks,
            connection_id="conn_1",
        )

        ws.send_str.assert_not_awaited()
        assert "sess_1" not in tasks

    @patch("codelab.server.http_server.asyncio.sleep", new_callable=AsyncMock)
    async def test_ws_closed_before_send(self, mock_sleep: AsyncMock) -> None:
        """Если websocket закрыт до отправки, response не отправляется."""
        server = ACPHttpServer()
        ws = MagicMock()
        ws.closed = True
        ws.send_str = AsyncMock()
        protocol = MagicMock()
        protocol.complete_active_turn = AsyncMock(
            return_value=ACPMessage.response("req_1", {}),
        )
        tasks = cast(dict[str, asyncio.Task[None]], {"sess_1": MagicMock()})

        await server._complete_deferred_prompt(
            ws=ws,
            protocol=protocol,
            session_id="sess_1",
            deferred_prompt_tasks=tasks,
            connection_id="conn_1",
        )

        ws.send_str.assert_not_awaited()
        assert "sess_1" not in tasks

    @patch("codelab.server.http_server.asyncio.sleep", new_callable=AsyncMock)
    async def test_send_str_raises_logs_error(self, mock_sleep: AsyncMock) -> None:
        """Ошибка send_str логируется, выполнение продолжается, задача удаляется."""
        server = ACPHttpServer()
        ws = MagicMock()
        ws.closed = False
        ws.send_str = AsyncMock(side_effect=ConnectionError("send failed"))
        protocol = MagicMock()
        protocol.complete_active_turn = AsyncMock(
            return_value=ACPMessage.response("req_1", {}),
        )
        tasks = cast(dict[str, asyncio.Task[None]], {"sess_1": MagicMock()})

        await server._complete_deferred_prompt(
            ws=ws,
            protocol=protocol,
            session_id="sess_1",
            deferred_prompt_tasks=tasks,
            connection_id="conn_1",
        )

        ws.send_str.assert_awaited_once()
        assert "sess_1" not in tasks

    @patch(
        "codelab.server.http_server.asyncio.sleep",
        side_effect=asyncio.CancelledError,
    )
    async def test_cancelled_error_with_pending_response_sends_cancel(
        self, mock_sleep: MagicMock,
    ) -> None:
        """CancelledError с pending_prompt_response отправляет отменённый ответ."""
        server = ACPHttpServer()
        ws = MagicMock()
        ws.closed = False
        ws.send_str = AsyncMock()
        protocol = MagicMock()
        session = MagicMock()
        session.pending_prompt_response = {
            "request_id": "req_1",
            "stop_reason": "cancelled",
        }
        protocol._storage.load_session = AsyncMock(return_value=session)
        protocol._storage.save_session = AsyncMock()
        tasks = cast(dict[str, asyncio.Task[None]], {"sess_1": MagicMock()})

        await server._complete_deferred_prompt(
            ws=ws,
            protocol=protocol,
            session_id="sess_1",
            deferred_prompt_tasks=tasks,
            connection_id="conn_1",
        )

        protocol._storage.load_session.assert_awaited_once_with("sess_1")
        protocol._storage.save_session.assert_awaited_once_with(session)
        assert session.pending_prompt_response is None
        ws.send_str.assert_awaited_once()
        sent_json = ws.send_str.await_args[0][0]
        assert '"stopReason":"cancelled"' in sent_json
        assert "sess_1" not in tasks

    @patch(
        "codelab.server.http_server.asyncio.sleep",
        side_effect=asyncio.CancelledError,
    )
    async def test_cancelled_error_without_pending_no_response(
        self, mock_sleep: MagicMock,
    ) -> None:
        """CancelledError без pending_prompt_response не отправляет ответ."""
        server = ACPHttpServer()
        ws = MagicMock()
        ws.closed = False
        ws.send_str = AsyncMock()
        protocol = MagicMock()
        session = MagicMock()
        session.pending_prompt_response = None
        protocol._storage.load_session = AsyncMock(return_value=session)
        tasks = cast(dict[str, asyncio.Task[None]], {"sess_1": MagicMock()})

        await server._complete_deferred_prompt(
            ws=ws,
            protocol=protocol,
            session_id="sess_1",
            deferred_prompt_tasks=tasks,
            connection_id="conn_1",
        )

        ws.send_str.assert_not_awaited()
        assert "sess_1" not in tasks

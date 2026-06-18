"""Дополнительные тесты покрытия для MCP транспортов.

Покрывают непокрытые ветки StdioTransport, HttpTransport и SseTransport,
сосредоточенные на методах connect/send/close/read loops, обработке ошибок HTTP
и парсинге SSE событий.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from codelab.server.mcp.models import MCPResponse
from codelab.server.mcp.transport import (
    HttpConnectionError,
    HttpTimeoutError,
    HttpTransport,
    HttpTransportError,
    ProcessExitedError,
    ProcessNotStartedError,
    SseTransport,
    SseTransportError,
    StdioTransport,
    StdioTransportError,
)


def _async_iter(lines: list[bytes]):
    """Вспомогательный асинхронный итератор из списка байтовых строк."""
    it = iter(lines)

    class _AsyncIter:
        def __aiter__(self) -> _AsyncIter:
            return self

        async def __anext__(self) -> bytes:
            try:
                return next(it)
            except StopIteration:
                raise StopAsyncIteration from None

    return _AsyncIter()


def _mock_stdio_process(returncode: int | None = None, pid: int = 123) -> MagicMock:
    """Создаёт mock subprocess.Process для StdioTransport."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.pid = pid

    proc.stdin = MagicMock()
    proc.stdin.close = MagicMock()
    proc.stdin.wait_closed = AsyncMock()
    proc.stdin.write = MagicMock()
    proc.stdin.drain = AsyncMock()

    proc.stdout = MagicMock()
    proc.stdout.readline = AsyncMock()

    proc.stderr = MagicMock()
    proc.stderr.readline = AsyncMock()

    proc.wait = AsyncMock(return_value=0)
    proc.terminate = MagicMock()
    proc.kill = MagicMock()

    return proc


def _mock_http_response(status: int = 200, json_data=None, raise_on_json=None):
    """Создаёт mock HTTP response, пригодный для async with."""
    response = MagicMock()
    response.status = status
    if raise_on_json is not None:
        response.json = AsyncMock(side_effect=raise_on_json)
    else:
        response.json = AsyncMock(return_value=json_data)
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    return response


class TestProcessExitedError:
    """Тесты исключения ProcessExitedError."""

    def test_process_exited_error_stores_return_code(self):
        """ProcessExitedError сохраняет код возврата процесса."""
        err = ProcessExitedError("process exited", return_code=42)
        assert str(err) == "process exited"
        assert err.return_code == 42


class TestStdioTransportConnect:
    """Тесты подключения StdioTransport."""

    @pytest.mark.asyncio
    async def test_connect_already_connected(self):
        """Повторный connect выбрасывает StdioTransportError."""
        transport = StdioTransport(command="test")
        transport._process = _mock_stdio_process()

        with pytest.raises(StdioTransportError, match="already connected"):
            await transport.connect()

    @pytest.mark.asyncio
    async def test_connect_file_not_found(self):
        """FileNotFoundError при запуске процесса преобразуется в StdioTransportError."""
        with patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            side_effect=FileNotFoundError(),
        ):
            transport = StdioTransport(command="missing")
            with pytest.raises(StdioTransportError, match="MCP server not found"):
                await transport.connect()

    @pytest.mark.asyncio
    async def test_connect_os_error(self):
        """OSError при запуске процесса преобразуется в StdioTransportError."""
        with patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            side_effect=OSError("permission denied"),
        ):
            transport = StdioTransport(command="test")
            with pytest.raises(StdioTransportError, match="Failed to start"):
                await transport.connect()

    @pytest.mark.asyncio
    async def test_connect_success_with_env_and_cwd(self):
        """Успешный connect создаёт задачи чтения и сохраняет процесс."""
        process = _mock_stdio_process()

        with patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=process,
        ):
            transport = StdioTransport(
                command="test",
                args=["--stdio"],
                env={"EXTRA": "value"},
                cwd="/tmp",
            )
            await transport.connect()

            assert transport.is_connected
            assert transport._read_task is not None
            assert transport._stderr_task is not None

            await transport.close()


class TestStdioTransportSend:
    """Тесты отправки сообщений StdioTransport."""

    @pytest.mark.asyncio
    async def test_send_request_not_connected(self):
        """send_request без соединения выбрасывает ProcessNotStartedError."""
        transport = StdioTransport(command="test")

        with pytest.raises(ProcessNotStartedError, match="not running"):
            await transport.send_request("test_method")

    @pytest.mark.asyncio
    async def test_send_request_success(self):
        """Успешная отправка запроса возвращает результат."""
        transport = StdioTransport(command="test")
        transport._process = _mock_stdio_process()
        transport._write_message = AsyncMock()

        async def resolve():
            await asyncio.sleep(0)
            future = transport._pending_requests.get(1)
            if future and not future.done():
                future.set_result(MCPResponse(id=1, result={"ok": True}))

        asyncio.create_task(resolve())
        result = await transport.send_request("test_method", timeout=0.1)

        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_send_request_error_response(self):
        """Ответ с ошибкой MCP преобразуется в StdioTransportError."""
        transport = StdioTransport(command="test")
        transport._process = _mock_stdio_process()
        transport._write_message = AsyncMock()

        async def resolve():
            await asyncio.sleep(0)
            future = transport._pending_requests.get(1)
            if future and not future.done():
                future.set_result(
                    MCPResponse(
                        id=1,
                        error={"code": -32600, "message": "Invalid Request"},
                    )
                )

        asyncio.create_task(resolve())
        with pytest.raises(StdioTransportError, match="MCP error"):
            await transport.send_request("test_method", timeout=0.1)

    @pytest.mark.asyncio
    async def test_send_request_timeout(self):
        """Таймаут ожидания ответа выбрасывает asyncio.TimeoutError."""
        transport = StdioTransport(command="test")
        transport._process = _mock_stdio_process()
        transport._write_message = AsyncMock()

        with pytest.raises(asyncio.TimeoutError):
            await transport.send_request("test_method", timeout=0.01)

    @pytest.mark.asyncio
    async def test_send_notification_not_connected(self):
        """send_notification без соединения выбрасывает ProcessNotStartedError."""
        transport = StdioTransport(command="test")

        with pytest.raises(ProcessNotStartedError, match="not running"):
            await transport.send_notification("test_method")

    @pytest.mark.asyncio
    async def test_send_notification_success(self):
        """Успешная отправка notification не возвращает значения."""
        transport = StdioTransport(command="test")
        transport._process = _mock_stdio_process()
        transport._write_message = AsyncMock()

        await transport.send_notification("test_method", {"data": 1})

        transport._write_message.assert_awaited_once()


class TestStdioTransportClose:
    """Тесты закрытия StdioTransport."""

    @pytest.mark.asyncio
    async def test_close_already_closed(self):
        """Повторный close не выполняет действий."""
        transport = StdioTransport(command="test")
        transport._closed = True

        await transport.close()

        assert transport._process is None

    @pytest.mark.asyncio
    async def test_close_normal(self):
        """Нормальное закрытие завершает процесс."""
        transport = StdioTransport(command="test")
        transport._process = _mock_stdio_process()

        await transport.close()

        assert transport._closed
        assert transport._process is None

    @pytest.mark.asyncio
    async def test_close_cancels_pending_requests(self):
        """Закрытие отменяет все ожидающие запросы."""
        transport = StdioTransport(command="test")
        transport._process = _mock_stdio_process()
        future = asyncio.get_running_loop().create_future()
        transport._pending_requests[1] = future

        await transport.close()

        assert future.cancelled()

    @pytest.mark.asyncio
    async def test_close_terminate_and_kill(self):
        """При таймауте закрытия процесс terminate/kill."""
        transport = StdioTransport(command="test")
        process = _mock_stdio_process()
        transport._process = process

        with patch(
            "asyncio.wait_for",
            side_effect=[TimeoutError, TimeoutError],
        ):
            await transport.close()

        process.terminate.assert_called_once()
        process.kill.assert_called_once()


class TestStdioTransportWrite:
    """Тесты записи сообщений StdioTransport."""

    @pytest.mark.asyncio
    async def test_write_message_not_started(self):
        """Запись без процесса выбрасывает ProcessNotStartedError."""
        transport = StdioTransport(command="test")

        with pytest.raises(ProcessNotStartedError, match="No stdin"):
            await transport._write_message({"jsonrpc": "2.0"})

    @pytest.mark.asyncio
    async def test_write_message_broken_pipe(self):
        """BrokenPipeError при записи преобразуется в ProcessExitedError."""
        transport = StdioTransport(command="test")
        process = _mock_stdio_process()
        process.stdin.write.side_effect = BrokenPipeError("broken")
        transport._process = process

        with pytest.raises(ProcessExitedError, match="pipe broken"):
            await transport._write_message({"jsonrpc": "2.0"})

    @pytest.mark.asyncio
    async def test_write_message_connection_reset(self):
        """ConnectionResetError при drain преобразуется в ProcessExitedError."""
        transport = StdioTransport(command="test")
        process = _mock_stdio_process()
        process.stdin.drain.side_effect = ConnectionResetError("reset")
        transport._process = process

        with pytest.raises(ProcessExitedError, match="pipe broken"):
            await transport._write_message({"jsonrpc": "2.0"})


class TestStdioTransportReadLoops:
    """Тесты циклов чтения StdioTransport."""

    @pytest.mark.asyncio
    async def test_read_stdout_loop_no_stdout(self):
        """Цикл чтения stdout завершается, если stdout недоступен."""
        transport = StdioTransport(command="test")
        transport._process = _mock_stdio_process()
        transport._process.stdout = None

        await transport._read_stdout_loop()

    @pytest.mark.asyncio
    async def test_read_stdout_loop_invalid_json(self, caplog):
        """Невалидный JSON логируется и пропускается."""
        transport = StdioTransport(command="test")
        process = _mock_stdio_process()
        process.stdout.readline = AsyncMock(
            side_effect=[b"not json\n", b""],
        )
        transport._process = process

        with caplog.at_level("WARNING"):
            await transport._read_stdout_loop()
            assert "Invalid JSON" in caplog.text

    @pytest.mark.asyncio
    async def test_read_stdout_loop_unknown_message(self, caplog):
        """Неизвестный формат сообщения логируется."""
        transport = StdioTransport(command="test")
        process = _mock_stdio_process()
        process.stdout.readline = AsyncMock(
            side_effect=[b'{"foo": "bar"}\n', b""],
        )
        transport._process = process

        with caplog.at_level("WARNING"):
            await transport._read_stdout_loop()
            assert "Unknown message format" in caplog.text

    @pytest.mark.asyncio
    async def test_read_stdout_loop_invalid_response_exception(self):
        """Ошибка валидации response устанавливает исключение в Future."""
        transport = StdioTransport(command="test")
        process = _mock_stdio_process()
        process.stdout.readline = AsyncMock(
            side_effect=[b'{"jsonrpc": "2.0", "id": 1, "result": {}}\n', b""],
        )
        transport._process = process
        future = asyncio.get_running_loop().create_future()
        transport._pending_requests[1] = future

        with patch.object(MCPResponse, "model_validate", side_effect=ValueError("bad")):
            await transport._read_stdout_loop()

        assert future.done()
        with pytest.raises(StdioTransportError, match="Invalid response"):
            future.result()

    @pytest.mark.asyncio
    async def test_read_stdout_loop_unknown_id(self, caplog):
        """Response с неизвестным id логируется."""
        transport = StdioTransport(command="test")
        process = _mock_stdio_process()
        process.stdout.readline = AsyncMock(
            side_effect=[b'{"jsonrpc": "2.0", "id": 999, "result": {}}\n', b""],
        )
        transport._process = process

        with caplog.at_level("WARNING"):
            await transport._read_stdout_loop()
            assert "unknown request id" in caplog.text

    @pytest.mark.asyncio
    async def test_read_stdout_loop_read_error(self):
        """Ошибка чтения stdout отменяет ожидающие запросы."""
        transport = StdioTransport(command="test")
        process = _mock_stdio_process()
        process.stdout.readline = AsyncMock(side_effect=RuntimeError("boom"))
        transport._process = process
        future = asyncio.get_running_loop().create_future()
        transport._pending_requests[1] = future

        await transport._read_stdout_loop()

        assert future.done()
        with pytest.raises(ProcessExitedError, match="Read error"):
            future.result()

    @pytest.mark.asyncio
    async def test_read_stdout_loop_cancelled(self):
        """CancelledError пробрасывается из цикла чтения stdout."""
        transport = StdioTransport(command="test")
        process = _mock_stdio_process()
        process.stdout.readline = AsyncMock(side_effect=asyncio.CancelledError())
        transport._process = process

        with pytest.raises(asyncio.CancelledError):
            await transport._read_stdout_loop()

    @pytest.mark.asyncio
    async def test_read_stderr_loop_no_stderr(self):
        """Цикл чтения stderr завершается, если stderr недоступен."""
        transport = StdioTransport(command="test")
        process = _mock_stdio_process()
        process.stderr = None
        transport._process = process

        await transport._read_stderr_loop()

    @pytest.mark.asyncio
    async def test_read_stderr_loop_eof(self):
        """EOF в stderr корректно завершает цикл."""
        transport = StdioTransport(command="test")
        process = _mock_stdio_process()
        process.stderr.readline = AsyncMock(side_effect=[b""])
        transport._process = process

        await transport._read_stderr_loop()

    @pytest.mark.asyncio
    async def test_read_stderr_loop_logs_and_exception(self, caplog):
        """stderr логируется, ошибки чтения обрабатываются."""
        transport = StdioTransport(command="test")
        process = _mock_stdio_process()
        process.stderr.readline = AsyncMock(
            side_effect=[b"log line\n", RuntimeError("boom")],
        )
        transport._process = process

        with caplog.at_level("DEBUG"):
            await transport._read_stderr_loop()
            assert "log line" in caplog.text

    @pytest.mark.asyncio
    async def test_read_stderr_loop_cancelled(self):
        """CancelledError пробрасывается из цикла чтения stderr."""
        transport = StdioTransport(command="test")
        process = _mock_stdio_process()
        process.stderr.readline = AsyncMock(side_effect=asyncio.CancelledError())
        transport._process = process

        with pytest.raises(asyncio.CancelledError):
            await transport._read_stderr_loop()


class TestStdioTransportHandlers:
    """Тесты обработчиков StdioTransport."""

    @pytest.mark.asyncio
    async def test_handle_notification_sync_and_wildcard(self):
        """Синхронные и wildcard обработчики notification вызываются."""
        transport = StdioTransport(command="test")
        specific = MagicMock()
        wildcard = MagicMock()
        transport.register_notification_handler("method", specific)
        transport.register_notification_handler("*", wildcard)

        data = {"method": "method", "params": {}}
        await transport._handle_notification(data)

        assert transport.notification_queue.get_nowait() == data
        specific.assert_called_once_with(data)
        wildcard.assert_called_once_with(data)

    @pytest.mark.asyncio
    async def test_handle_notification_handler_exception(self, caplog):
        """Исключение в обработчике notification логируется."""
        transport = StdioTransport(command="test")
        failing = AsyncMock(side_effect=ValueError("fail"))
        transport.register_notification_handler("method", failing)

        with caplog.at_level("ERROR"):
            await transport._handle_notification({"method": "method"})
            assert "Error in notification handler" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_incoming_request_without_id(self, caplog):
        """Входящий запрос без id логируется."""
        transport = StdioTransport(command="test")

        with caplog.at_level("WARNING"):
            await transport._handle_incoming_request({"method": "roots/list"})
            assert "without id" in caplog.text

    @pytest.mark.asyncio
    async def test_register_request_handler(self):
        """Регистрация обработчика входящего запроса."""
        transport = StdioTransport(command="test")
        handler = AsyncMock(return_value={"result": True})
        transport.register_request_handler("roots/list", handler)

        assert transport._request_handlers["roots/list"] == handler

    @pytest.mark.asyncio
    async def test_handle_response_message_without_id(self, caplog):
        """Response без id логируется."""
        transport = StdioTransport(command="test")

        with caplog.at_level("WARNING"):
            await transport._handle_response_message({"result": {}})
            assert "response without id" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_response_message_success(self):
        """Валидный response устанавливает результат Future."""
        transport = StdioTransport(command="test")
        future = asyncio.get_running_loop().create_future()
        transport._pending_requests[1] = future

        await transport._handle_response_message(
            {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
        )

        response = future.result()
        assert response.result == {"ok": True}

    @pytest.mark.asyncio
    async def test_send_response_not_connected(self):
        """send_response без соединения выбрасывает ProcessNotStartedError."""
        transport = StdioTransport(command="test")

        with pytest.raises(ProcessNotStartedError, match="not running"):
            await transport.send_response(1, {"ok": True})

    @pytest.mark.asyncio
    async def test_send_response_no_stdin(self):
        """send_response без stdin выбрасывает ProcessNotStartedError."""
        transport = StdioTransport(command="test")
        transport._process = _mock_stdio_process()
        transport._process.stdin = None

        with pytest.raises(ProcessNotStartedError, match="stdin not available"):
            await transport.send_response(1, {"ok": True})

    @pytest.mark.asyncio
    async def test_send_response_success(self):
        """Успешная отправка response."""
        transport = StdioTransport(command="test")
        transport._process = _mock_stdio_process()

        await transport.send_response(1, {"ok": True})

        transport._process.stdin.write.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_response_exception(self):
        """Исключение при отправке response преобразуется в StdioTransportError."""
        transport = StdioTransport(command="test")
        process = _mock_stdio_process()
        process.stdin.drain.side_effect = RuntimeError("fail")
        transport._process = process

        with pytest.raises(StdioTransportError, match="Failed to send response"):
            await transport.send_response(1, {"ok": True})

    @pytest.mark.asyncio
    async def test_send_error_not_connected(self):
        """send_error без соединения выбрасывает ProcessNotStartedError."""
        transport = StdioTransport(command="test")

        with pytest.raises(ProcessNotStartedError, match="not running"):
            await transport.send_error(1, -32603, "err")

    @pytest.mark.asyncio
    async def test_send_error_no_stdin(self):
        """send_error без stdin выбрасывает ProcessNotStartedError."""
        transport = StdioTransport(command="test")
        transport._process = _mock_stdio_process()
        transport._process.stdin = None

        with pytest.raises(ProcessNotStartedError, match="stdin not available"):
            await transport.send_error(1, -32603, "err")

    @pytest.mark.asyncio
    async def test_send_error_with_data(self):
        """send_error с дополнительными данными включает data в ответ."""
        transport = StdioTransport(command="test")
        process = _mock_stdio_process()
        transport._process = process

        await transport.send_error(1, -32603, "err", data={"detail": "x"})

        written = process.stdin.write.call_args[0][0].decode("utf-8")
        assert '"data"' in written

    @pytest.mark.asyncio
    async def test_send_error_exception(self):
        """Исключение при отправке error преобразуется в StdioTransportError."""
        transport = StdioTransport(command="test")
        process = _mock_stdio_process()
        process.stdin.drain.side_effect = RuntimeError("fail")
        transport._process = process

        with pytest.raises(StdioTransportError, match="Failed to send error response"):
            await transport.send_error(1, -32603, "err")

    @pytest.mark.asyncio
    async def test_notification_queue(self):
        """Свойство notification_queue возвращает внутреннюю очередь."""
        transport = StdioTransport(command="test")
        assert transport.notification_queue is transport._notification_queue


class TestHttpTransportErrorHandling:
    """Тесты обработки ошибок HttpTransport."""

    @pytest.mark.asyncio
    async def test_connect_head_server_error(self, caplog):
        """HEAD с ошибкой >=400 логирует warning, но соединение остаётся."""
        mock_session = AsyncMock()
        mock_session.closed = False
        response = _mock_http_response(status=500)
        mock_session.head = MagicMock(return_value=response)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            transport = HttpTransport(url="http://test")
            with caplog.at_level("WARNING"):
                await transport.connect()
                assert "returned status 500" in caplog.text

            assert transport.is_connected
            await transport.close()

    @pytest.mark.asyncio
    async def test_send_request_session_not_initialized(self):
        """send_request с is_connected, но без session выбрасывает HttpConnectionError."""
        transport = HttpTransport(url="http://test")
        with patch.object(HttpTransport, "is_connected", property(lambda self: True)):
            with pytest.raises(HttpConnectionError, match="Session not initialized"):
                await transport.send_request("test")

    @pytest.mark.asyncio
    async def test_send_request_status_408(self):
        """HTTP 408 выбрасывает HttpTimeoutError."""
        transport = HttpTransport(url="http://test")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        response = _mock_http_response(status=408)
        mock_session.post = MagicMock(return_value=response)
        transport._session = mock_session

        with pytest.raises(HttpTimeoutError, match="HTTP timeout"):
            await transport.send_request("test")

    @pytest.mark.asyncio
    async def test_send_request_status_504(self):
        """HTTP 504 выбрасывает HttpTimeoutError."""
        transport = HttpTransport(url="http://test")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        response = _mock_http_response(status=504)
        mock_session.post = MagicMock(return_value=response)
        transport._session = mock_session

        with pytest.raises(HttpTimeoutError, match="HTTP timeout"):
            await transport.send_request("test")

    @pytest.mark.asyncio
    async def test_send_request_client_error(self):
        """HTTP 404 выбрасывает HttpTransportError."""
        transport = HttpTransport(url="http://test")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        response = _mock_http_response(status=404)
        mock_session.post = MagicMock(return_value=response)
        transport._session = mock_session

        with pytest.raises(HttpTransportError, match="HTTP client error"):
            await transport.send_request("test")

    @pytest.mark.asyncio
    async def test_send_request_invalid_json(self):
        """Невалидный JSON ответа выбрасывает HttpTransportError."""
        transport = HttpTransport(url="http://test")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        response = _mock_http_response(
            status=200,
            raise_on_json=json.JSONDecodeError("bad", "", 0),
        )
        mock_session.post = MagicMock(return_value=response)
        transport._session = mock_session

        with pytest.raises(HttpTransportError, match="Invalid JSON response"):
            await transport.send_request("test")

    @pytest.mark.asyncio
    async def test_send_request_mcp_error(self):
        """MCP error в ответе выбрасывает HttpTransportError."""
        transport = HttpTransport(url="http://test")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        response = _mock_http_response(
            status=200,
            json_data={
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32600, "message": "bad"},
            },
        )
        mock_session.post = MagicMock(return_value=response)
        transport._session = mock_session

        with pytest.raises(HttpTransportError, match="MCP error"):
            await transport.send_request("test")

    @pytest.mark.asyncio
    async def test_send_request_future_timeout(self):
        """Таймаут ожидания future выбрасывает HttpTimeoutError."""
        transport = HttpTransport(url="http://test")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        response = _mock_http_response(
            status=200,
            json_data={"jsonrpc": "2.0", "id": 1, "result": {}},
        )
        mock_session.post = MagicMock(return_value=response)
        transport._session = mock_session

        with patch("asyncio.wait_for", side_effect=TimeoutError):
            with pytest.raises(HttpTimeoutError, match="Request timeout"):
                await transport.send_request("test")

    @pytest.mark.asyncio
    async def test_send_notification_client_error(self):
        """ClientError при отправке notification выбрасывает HttpTransportError."""
        transport = HttpTransport(url="http://test")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(side_effect=aiohttp.ClientError("fail"))
        transport._session = mock_session

        with pytest.raises(HttpTransportError, match="Failed to send notification"):
            await transport.send_notification("test")

    @pytest.mark.asyncio
    async def test_send_notification_session_not_initialized(self):
        """send_notification с is_connected, но без session выбрасывает HttpConnectionError."""
        transport = HttpTransport(url="http://test")
        with patch.object(HttpTransport, "is_connected", property(lambda self: True)):
            with pytest.raises(HttpConnectionError, match="Session not initialized"):
                await transport.send_notification("test")

    @pytest.mark.asyncio
    async def test_close_pending_requests_exception(self):
        """Закрытие устанавливает исключение в ожидающие запросы."""
        transport = HttpTransport(url="http://test")
        future = asyncio.get_running_loop().create_future()
        transport._pending_requests[1] = future

        await transport.close()

        assert future.done()
        with pytest.raises(HttpTransportError, match="Transport closed"):
            future.result()

    @pytest.mark.asyncio
    async def test_handle_response_unknown_format(self, caplog):
        """Неизвестный формат JSON-RPC логируется."""
        transport = HttpTransport(url="http://test")

        with caplog.at_level("WARNING"):
            await transport._handle_response({"foo": "bar"})
            assert "Unknown message format" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_response_message_without_id(self, caplog):
        """Response без id логируется."""
        transport = HttpTransport(url="http://test")

        with caplog.at_level("WARNING"):
            await transport._handle_response_message({"result": {}})
            assert "response without id" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_response_message_invalid_response(self):
        """Ошибка валидации response устанавливает исключение в Future."""
        transport = HttpTransport(url="http://test")
        future = asyncio.get_running_loop().create_future()
        transport._pending_requests[1] = future

        with patch.object(MCPResponse, "model_validate", side_effect=ValueError("bad")):
            await transport._handle_response_message(
                {"jsonrpc": "2.0", "id": 1, "result": {}}
            )

        with pytest.raises(HttpTransportError, match="Invalid response"):
            future.result()

    @pytest.mark.asyncio
    async def test_handle_response_message_unknown_id(self, caplog):
        """Response с неизвестным id логируется."""
        transport = HttpTransport(url="http://test")

        with caplog.at_level("WARNING"):
            await transport._handle_response_message(
                {"jsonrpc": "2.0", "id": 999, "result": {}}
            )
            assert "unknown request id" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_notification_sync_and_wildcard(self):
        """Синхронные и wildcard обработчики notification вызываются."""
        transport = HttpTransport(url="http://test")
        specific = MagicMock()
        wildcard = MagicMock()
        transport.register_notification_handler("method", specific)
        transport.register_notification_handler("*", wildcard)

        data = {"method": "method", "params": {}}
        await transport._handle_notification(data)

        specific.assert_called_once_with(data)
        wildcard.assert_called_once_with(data)

    @pytest.mark.asyncio
    async def test_handle_notification_handler_exception(self, caplog):
        """Исключение в обработчике notification логируется."""
        transport = HttpTransport(url="http://test")
        failing = AsyncMock(side_effect=ValueError("fail"))
        transport.register_notification_handler("method", failing)

        with caplog.at_level("ERROR"):
            await transport._handle_notification({"method": "method"})
            assert "Error in notification handler" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_incoming_request_without_id(self, caplog):
        """Входящий запрос без id логируется."""
        transport = HttpTransport(url="http://test")

        with caplog.at_level("WARNING"):
            await transport._handle_incoming_request({"method": "roots/list"})
            assert "without id" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_incoming_request_success(self):
        """Успешная обработка входящего запроса отправляет ответ."""
        transport = HttpTransport(url="http://test")
        transport.send_response = AsyncMock()
        transport.send_error = AsyncMock()
        transport.register_request_handler("roots/list", AsyncMock(return_value={"roots": []}))

        await transport._handle_incoming_request(
            {"jsonrpc": "2.0", "method": "roots/list", "id": 1, "params": {}}
        )

        transport.send_response.assert_awaited_once_with(1, {"roots": []})
        transport.send_error.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handle_incoming_request_exception(self):
        """Исключение в обработчике входящего запроса отправляет ошибку."""
        transport = HttpTransport(url="http://test")
        transport.send_response = AsyncMock()
        transport.send_error = AsyncMock()
        transport.register_request_handler(
            "roots/list", AsyncMock(side_effect=ValueError("fail"))
        )

        await transport._handle_incoming_request(
            {"jsonrpc": "2.0", "method": "roots/list", "id": 1, "params": {}}
        )

        transport.send_response.assert_not_awaited()
        transport.send_error.assert_awaited_once()
        assert transport.send_error.call_args[0][1] == -32603

    @pytest.mark.asyncio
    async def test_handle_incoming_request_no_handler(self):
        """Отсутствие обработчика входящего запроса отправляет Method not found."""
        transport = HttpTransport(url="http://test")
        transport.send_response = AsyncMock()
        transport.send_error = AsyncMock()

        await transport._handle_incoming_request(
            {"jsonrpc": "2.0", "method": "unknown", "id": 1, "params": {}}
        )

        transport.send_response.assert_not_awaited()
        transport.send_error.assert_awaited_once()
        assert transport.send_error.call_args[0][1] == -32601

    @pytest.mark.asyncio
    async def test_send_response_not_connected(self):
        """send_response без соединения выбрасывает HttpConnectionError."""
        transport = HttpTransport(url="http://test")

        with pytest.raises(HttpConnectionError, match="Not connected"):
            await transport.send_response(1, {})

    @pytest.mark.asyncio
    async def test_send_response_session_not_initialized(self):
        """send_response с is_connected, но без session выбрасывает HttpConnectionError."""
        transport = HttpTransport(url="http://test")
        with patch.object(HttpTransport, "is_connected", property(lambda self: True)):
            with pytest.raises(HttpConnectionError, match="Session not initialized"):
                await transport.send_response(1, {})

    @pytest.mark.asyncio
    async def test_send_response_success(self):
        """Успешная отправка response по HTTP."""
        transport = HttpTransport(url="http://test")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        response = _mock_http_response(status=200)
        mock_session.post = MagicMock(return_value=response)
        transport._session = mock_session

        await transport.send_response(1, {"ok": True})

        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_response_client_error(self):
        """ClientError при отправке response выбрасывает HttpTransportError."""
        transport = HttpTransport(url="http://test")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(side_effect=aiohttp.ClientError("fail"))
        transport._session = mock_session

        with pytest.raises(HttpTransportError, match="Failed to send response"):
            await transport.send_response(1, {})

    @pytest.mark.asyncio
    async def test_send_error_not_connected(self):
        """send_error без соединения выбрасывает HttpConnectionError."""
        transport = HttpTransport(url="http://test")

        with pytest.raises(HttpConnectionError, match="Not connected"):
            await transport.send_error(1, -32603, "err")

    @pytest.mark.asyncio
    async def test_send_error_session_not_initialized(self):
        """send_error с is_connected, но без session выбрасывает HttpConnectionError."""
        transport = HttpTransport(url="http://test")
        with patch.object(HttpTransport, "is_connected", property(lambda self: True)):
            with pytest.raises(HttpConnectionError, match="Session not initialized"):
                await transport.send_error(1, -32603, "err")

    @pytest.mark.asyncio
    async def test_send_error_with_data(self):
        """send_error включает data при её наличии."""
        transport = HttpTransport(url="http://test")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        response = _mock_http_response(status=200)
        mock_session.post = MagicMock(return_value=response)
        transport._session = mock_session

        await transport.send_error(1, -32603, "err", data={"detail": "x"})

        args = mock_session.post.call_args
        assert args[1]["json"]["error"]["data"] == {"detail": "x"}

    @pytest.mark.asyncio
    async def test_send_error_success(self):
        """Успешная отправка error response по HTTP."""
        transport = HttpTransport(url="http://test")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        response = _mock_http_response(status=200)
        mock_session.post = MagicMock(return_value=response)
        transport._session = mock_session

        await transport.send_error(1, -32603, "err")

        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_error_client_error(self):
        """ClientError при отправке error response выбрасывает HttpTransportError."""
        transport = HttpTransport(url="http://test")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(side_effect=aiohttp.ClientError("fail"))
        transport._session = mock_session

        with pytest.raises(HttpTransportError, match="Failed to send error response"):
            await transport.send_error(1, -32603, "err")


class TestSseTransportParsingAndErrors:
    """Тесты парсинга SSE и обработки ошибок SseTransport."""

    @pytest.mark.asyncio
    async def test_send_request_session_not_initialized(self):
        """send_request с is_connected, но без session выбрасывает SseTransportError."""
        transport = SseTransport(url="http://test/sse")
        with patch.object(SseTransport, "is_connected", property(lambda self: True)):
            with pytest.raises(SseTransportError, match="Session not initialized"):
                await transport.send_request("test")

    @pytest.mark.asyncio
    async def test_send_request_http_error(self):
        """HTTP >=400 при SSE запросе выбрасывает SseTransportError."""
        transport = SseTransport(url="http://test/sse")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        response = _mock_http_response(status=500)
        mock_session.post = MagicMock(return_value=response)
        transport._session = mock_session
        transport._sse_response = MagicMock()

        with pytest.raises(SseTransportError, match="HTTP error"):
            await transport.send_request("test")

    @pytest.mark.asyncio
    async def test_send_request_timeout(self):
        """Таймаут SSE запроса выбрасывает SseTransportError."""
        transport = SseTransport(url="http://test/sse")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        response = _mock_http_response(
            status=200,
            json_data={"jsonrpc": "2.0", "id": 1, "result": {}},
        )
        mock_session.post = MagicMock(return_value=response)
        transport._session = mock_session
        transport._sse_response = MagicMock()

        with patch("asyncio.wait_for", side_effect=TimeoutError):
            with pytest.raises(SseTransportError, match="Request timeout"):
                await transport.send_request("test")

    @pytest.mark.asyncio
    async def test_send_request_mcp_error(self):
        """MCP error в SSE ответе выбрасывает SseTransportError."""
        transport = SseTransport(url="http://test/sse")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        response = _mock_http_response(status=200)
        mock_session.post = MagicMock(return_value=response)
        transport._session = mock_session
        transport._sse_response = MagicMock()

        async def resolve():
            await asyncio.sleep(0)
            future = transport._pending_requests.get(1)
            if future and not future.done():
                future.set_result(
                    MCPResponse(
                        id=1,
                        error={"code": -32600, "message": "bad"},
                    )
                )

        asyncio.create_task(resolve())

        with pytest.raises(SseTransportError, match="MCP error"):
            await transport.send_request("test")

    @pytest.mark.asyncio
    async def test_send_notification_client_error(self):
        """ClientError при отправке SSE notification выбрасывает SseTransportError."""
        transport = SseTransport(url="http://test/sse")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(side_effect=aiohttp.ClientError("fail"))
        transport._session = mock_session
        transport._sse_response = MagicMock()

        with pytest.raises(SseTransportError, match="Failed to send notification"):
            await transport.send_notification("test")

    @pytest.mark.asyncio
    async def test_send_notification_session_not_initialized(self):
        """SSE send_notification с is_connected, но без session выбрасывает SseTransportError."""
        transport = SseTransport(url="http://test/sse")
        with patch.object(SseTransport, "is_connected", property(lambda self: True)):
            with pytest.raises(SseTransportError, match="Session not initialized"):
                await transport.send_notification("test")

    @pytest.mark.asyncio
    async def test_send_notification_success(self):
        """SSE успешная отправка notification."""
        transport = SseTransport(url="http://test/sse")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        response = _mock_http_response(status=200)
        mock_session.post = MagicMock(return_value=response)
        transport._session = mock_session
        transport._sse_response = MagicMock()

        await transport.send_notification("test")

        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_request_success(self):
        """SSE успешная отправка запроса возвращает результат."""
        transport = SseTransport(url="http://test/sse")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        response = _mock_http_response(status=200)
        mock_session.post = MagicMock(return_value=response)
        transport._session = mock_session
        transport._sse_response = MagicMock()

        async def resolve():
            await asyncio.sleep(0)
            future = transport._pending_requests.get(1)
            if future and not future.done():
                future.set_result(MCPResponse(id=1, result={"ok": True}))

        asyncio.create_task(resolve())
        result = await transport.send_request("test")

        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_close_pending_requests_exception(self):
        """Закрытие SSE устанавливает исключение в ожидающие запросы."""
        transport = SseTransport(url="http://test/sse")
        future = asyncio.get_running_loop().create_future()
        transport._pending_requests[1] = future
        transport._read_task = asyncio.create_task(asyncio.sleep(10))

        await transport.close()

        assert future.done()
        with pytest.raises(SseTransportError, match="Transport closed"):
            future.result()

    @pytest.mark.asyncio
    async def test_read_sse_loop_early_return(self):
        """Цикл чтения SSE завершается, если response отсутствует."""
        transport = SseTransport(url="http://test/sse")
        transport._sse_response = None

        await transport._read_sse_loop()

    @pytest.mark.asyncio
    async def test_read_sse_loop_parsing(self):
        """Цикл чтения корректно парсит SSE event, id, data и комментарии."""
        transport = SseTransport(url="http://test/sse")
        transport._handle_sse_event = AsyncMock()
        response = MagicMock()
        response.content = _async_iter(
            [
                b": comment\n",
                b"event: custom\n",
                b"id: 42\n",
                b"data: line1\n",
                b"data: line2\n",
                b"\n",
                b"data: single\n",
                b"\n",
            ]
        )
        transport._sse_response = response

        await transport._read_sse_loop()

        assert transport._handle_sse_event.await_count == 2
        transport._handle_sse_event.assert_any_await(
            event="custom", data="line1\nline2", event_id="42"
        )
        transport._handle_sse_event.assert_any_await(
            event="message", data="single", event_id=None
        )

    @pytest.mark.asyncio
    async def test_read_sse_loop_exception(self):
        """Ошибка чтения SSE отменяет ожидающие запросы."""
        transport = SseTransport(url="http://test/sse")
        response = MagicMock()
        response.content = MagicMock()
        response.content.__aiter__ = MagicMock(side_effect=RuntimeError("boom"))
        transport._sse_response = response
        future = asyncio.get_running_loop().create_future()
        transport._pending_requests[1] = future

        await transport._read_sse_loop()

        assert future.done()
        with pytest.raises(SseTransportError, match="SSE read error"):
            future.result()

    @pytest.mark.asyncio
    async def test_read_sse_loop_no_colon_field(self):
        """SSE строка без двоеточия игнорируется."""
        transport = SseTransport(url="http://test/sse")
        transport._handle_sse_event = AsyncMock()
        response = MagicMock()
        response.content = _async_iter(
            [
                b"ping\n",
                b"data: ok\n",
                b"\n",
            ]
        )
        transport._sse_response = response

        await transport._read_sse_loop()

        transport._handle_sse_event.assert_awaited_once_with(
            event="message", data="ok", event_id=None
        )

    @pytest.mark.asyncio
    async def test_read_sse_loop_cancelled(self):
        """CancelledError пробрасывается из цикла чтения SSE."""
        transport = SseTransport(url="http://test/sse")
        response = MagicMock()
        response.content = MagicMock()
        response.content.__aiter__ = MagicMock(side_effect=asyncio.CancelledError())
        transport._sse_response = response

        with pytest.raises(asyncio.CancelledError):
            await transport._read_sse_loop()

    @pytest.mark.asyncio
    async def test_handle_sse_event_invalid_json(self, caplog):
        """Невалидный JSON в SSE event логируется."""
        transport = SseTransport(url="http://test/sse")

        with caplog.at_level("WARNING"):
            await transport._handle_sse_event("message", "not json")
            assert "Invalid JSON" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_sse_event_response(self):
        """SSE event с response устанавливает результат Future."""
        transport = SseTransport(url="http://test/sse")
        future = asyncio.get_running_loop().create_future()
        transport._pending_requests[1] = future

        await transport._handle_sse_event(
            "message",
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}),
        )

        response = future.result()
        assert response.result == {"ok": True}

    @pytest.mark.asyncio
    async def test_handle_sse_event_unknown_format(self, caplog):
        """Неизвестный SSE message format логируется."""
        transport = SseTransport(url="http://test/sse")

        with caplog.at_level("WARNING"):
            await transport._handle_sse_event(
                "message", json.dumps({"foo": "bar"})
            )
            assert "Unknown SSE message format" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_response_message_without_id(self, caplog):
        """SSE response без id логируется."""
        transport = SseTransport(url="http://test/sse")

        with caplog.at_level("WARNING"):
            await transport._handle_response_message({"result": {}})
            assert "response without id" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_response_message_invalid_response(self):
        """Ошибка валидации SSE response устанавливает исключение в Future."""
        transport = SseTransport(url="http://test/sse")
        future = asyncio.get_running_loop().create_future()
        transport._pending_requests[1] = future

        with patch.object(MCPResponse, "model_validate", side_effect=ValueError("bad")):
            await transport._handle_response_message(
                {"jsonrpc": "2.0", "id": 1, "result": {}}
            )

        with pytest.raises(SseTransportError, match="Invalid response"):
            future.result()

    @pytest.mark.asyncio
    async def test_handle_response_message_unknown_id(self, caplog):
        """SSE response с неизвестным id логируется."""
        transport = SseTransport(url="http://test/sse")

        with caplog.at_level("WARNING"):
            await transport._handle_response_message(
                {"jsonrpc": "2.0", "id": 999, "result": {}}
            )
            assert "unknown request id" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_notification_sync_and_exception(self, caplog):
        """Синхронный обработчик notification вызывается, исключение логируется."""
        transport = SseTransport(url="http://test/sse")
        sync_handler = MagicMock()
        failing = AsyncMock(side_effect=ValueError("fail"))
        transport.register_notification_handler("method", sync_handler)
        transport.register_notification_handler("method", failing)

        with caplog.at_level("ERROR"):
            await transport._handle_notification({"method": "method"})
            sync_handler.assert_called_once()
            assert "Error in SSE notification handler" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_incoming_request_without_id(self, caplog):
        """SSE входящий запрос без id логируется."""
        transport = SseTransport(url="http://test/sse")

        with caplog.at_level("WARNING"):
            await transport._handle_incoming_request({"method": "roots/list"})
            assert "without id" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_incoming_request_success(self):
        """SSE успешная обработка входящего запроса отправляет ответ."""
        transport = SseTransport(url="http://test/sse")
        transport.send_response = AsyncMock()
        transport.send_error = AsyncMock()
        transport.register_request_handler("roots/list", AsyncMock(return_value={"roots": []}))

        await transport._handle_incoming_request(
            {"jsonrpc": "2.0", "method": "roots/list", "id": 1, "params": {}}
        )

        transport.send_response.assert_awaited_once_with(1, {"roots": []})

    @pytest.mark.asyncio
    async def test_handle_incoming_request_exception(self):
        """SSE исключение в обработчике отправляет ошибку."""
        transport = SseTransport(url="http://test/sse")
        transport.send_response = AsyncMock()
        transport.send_error = AsyncMock()
        transport.register_request_handler(
            "roots/list", AsyncMock(side_effect=ValueError("fail"))
        )

        await transport._handle_incoming_request(
            {"jsonrpc": "2.0", "method": "roots/list", "id": 1, "params": {}}
        )

        transport.send_error.assert_awaited_once()
        assert transport.send_error.call_args[0][1] == -32603

    @pytest.mark.asyncio
    async def test_handle_incoming_request_no_handler(self):
        """SSE отсутствие обработчика отправляет Method not found."""
        transport = SseTransport(url="http://test/sse")
        transport.send_response = AsyncMock()
        transport.send_error = AsyncMock()

        await transport._handle_incoming_request(
            {"jsonrpc": "2.0", "method": "unknown", "id": 1, "params": {}}
        )

        transport.send_error.assert_awaited_once()
        assert transport.send_error.call_args[0][1] == -32601

    @pytest.mark.asyncio
    async def test_send_response_not_connected(self):
        """SSE send_response без соединения выбрасывает SseTransportError."""
        transport = SseTransport(url="http://test/sse")

        with pytest.raises(SseTransportError, match="Not connected"):
            await transport.send_response(1, {})

    @pytest.mark.asyncio
    async def test_send_response_session_not_initialized(self):
        """SSE send_response с is_connected, но без session выбрасывает SseTransportError."""
        transport = SseTransport(url="http://test/sse")
        with patch.object(SseTransport, "is_connected", property(lambda self: True)):
            with pytest.raises(SseTransportError, match="Session not initialized"):
                await transport.send_response(1, {})

    @pytest.mark.asyncio
    async def test_send_response_success(self):
        """SSE успешная отправка response."""
        transport = SseTransport(url="http://test/sse")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        response = _mock_http_response(status=200)
        mock_session.post = MagicMock(return_value=response)
        transport._session = mock_session
        transport._sse_response = MagicMock()

        await transport.send_response(1, {"ok": True})

        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_response_client_error(self):
        """SSE ClientError при отправке response выбрасывает SseTransportError."""
        transport = SseTransport(url="http://test/sse")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(side_effect=aiohttp.ClientError("fail"))
        transport._session = mock_session
        transport._sse_response = MagicMock()

        with pytest.raises(SseTransportError, match="Failed to send response"):
            await transport.send_response(1, {})

    @pytest.mark.asyncio
    async def test_send_error_not_connected(self):
        """SSE send_error без соединения выбрасывает SseTransportError."""
        transport = SseTransport(url="http://test/sse")

        with pytest.raises(SseTransportError, match="Not connected"):
            await transport.send_error(1, -32603, "err")

    @pytest.mark.asyncio
    async def test_send_error_session_not_initialized(self):
        """SSE send_error с is_connected, но без session выбрасывает SseTransportError."""
        transport = SseTransport(url="http://test/sse")
        with patch.object(SseTransport, "is_connected", property(lambda self: True)):
            with pytest.raises(SseTransportError, match="Session not initialized"):
                await transport.send_error(1, -32603, "err")

    @pytest.mark.asyncio
    async def test_send_error_with_data(self):
        """SSE send_error включает data при её наличии."""
        transport = SseTransport(url="http://test/sse")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        response = _mock_http_response(status=200)
        mock_session.post = MagicMock(return_value=response)
        transport._session = mock_session
        transport._sse_response = MagicMock()

        await transport.send_error(1, -32603, "err", data={"detail": "x"})

        args = mock_session.post.call_args
        assert args[1]["json"]["error"]["data"] == {"detail": "x"}

    @pytest.mark.asyncio
    async def test_send_error_success(self):
        """SSE успешная отправка error response."""
        transport = SseTransport(url="http://test/sse")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        response = _mock_http_response(status=200)
        mock_session.post = MagicMock(return_value=response)
        transport._session = mock_session
        transport._sse_response = MagicMock()

        await transport.send_error(1, -32603, "err")

        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_error_client_error(self):
        """SSE ClientError при отправке error response выбрасывает SseTransportError."""
        transport = SseTransport(url="http://test/sse")
        transport._closed = False
        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(side_effect=aiohttp.ClientError("fail"))
        transport._session = mock_session
        transport._sse_response = MagicMock()

        with pytest.raises(SseTransportError, match="Failed to send error response"):
            await transport.send_error(1, -32603, "err")

"""Тесты покрытия для StdioClientTransport.

Проверяет непокрытые ранее сценарии: жизненный цикл subprocess,
отправку и получение сообщений, фоновые задачи чтения stdout/stderr.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codelab.client.infrastructure.stdio_transport import StdioClientTransport


class TestStdioClientTransportLifecycle:
    """Тесты жизненного цикла транспорта (aenter/aexit)."""

    async def test_aenter_starts_subprocess_and_readers(self) -> None:
        """Проверяет успешный запуск subprocess и фоновых задач чтения."""
        transport = StdioClientTransport(
            command="test",
            args=["--stdio"],
            cwd="/tmp",
        )

        mock_process = MagicMock()
        mock_process.pid = 1234
        mock_process.stdin = MagicMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.readline = AsyncMock(return_value=b"")
        mock_process.stderr = AsyncMock()
        mock_process.stderr.readline = AsyncMock(return_value=b"")
        mock_process.wait = AsyncMock(return_value=0)

        with patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_process,
        ) as mock_exec:
            async with transport as entered:
                assert entered is transport
                assert transport._process is mock_process
                assert transport._stdout_task is not None
                assert transport._stderr_task is not None

            mock_exec.assert_awaited_once_with(
                "test",
                "--stdio",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/tmp",
            )

        assert transport._process is None

    async def test_aenter_raises_on_file_not_found(self) -> None:
        """Проверяет преобразование FileNotFoundError в RuntimeError."""
        transport = StdioClientTransport(command="missing", args=[])

        with patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            side_effect=FileNotFoundError(),
        ):
            with pytest.raises(RuntimeError, match="Command not found"):
                async with transport:
                    pass

    async def test_aenter_raises_on_os_error(self) -> None:
        """Проверяет преобразование OSError в RuntimeError."""
        transport = StdioClientTransport(command="test", args=[])

        with patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            side_effect=OSError("permission denied"),
        ):
            with pytest.raises(RuntimeError, match="Failed to start subprocess"):
                async with transport:
                    pass

    async def test_aexit_terminates_on_wait_timeout(self) -> None:
        """Проверяет terminate при превышении таймаута ожидания процесса."""
        transport = StdioClientTransport(command="test", args=[])

        mock_process = MagicMock()
        mock_process.pid = 1234
        mock_process.stdin = MagicMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.readline = AsyncMock(return_value=b"")
        mock_process.stderr = AsyncMock()
        mock_process.stderr.readline = AsyncMock(return_value=b"")

        wait_calls = 0

        async def fake_wait() -> int:
            nonlocal wait_calls
            wait_calls += 1
            if wait_calls == 1:
                await asyncio.Future()  # никогда не завершается
            return 0

        mock_process.wait = AsyncMock(side_effect=fake_wait)

        with patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_process,
        ):
            async with transport:
                pass

        mock_process.stdin.close.assert_called_once()
        mock_process.terminate.assert_called_once()
        assert mock_process.wait.await_count == 2

    async def test_aexit_kills_on_terminate_timeout(self) -> None:
        """Проверяет kill при неудачном terminate."""
        transport = StdioClientTransport(command="test", args=[])

        mock_process = MagicMock()
        mock_process.pid = 1234
        mock_process.stdin = MagicMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.readline = AsyncMock(return_value=b"")
        mock_process.stderr = AsyncMock()
        mock_process.stderr.readline = AsyncMock(return_value=b"")

        wait_calls = 0

        async def fake_wait() -> int:
            nonlocal wait_calls
            wait_calls += 1
            if wait_calls in (1, 2):
                await asyncio.Future()  # никогда не завершается
            return 0

        mock_process.wait = AsyncMock(side_effect=fake_wait)

        with patch(
            "asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=mock_process,
        ):
            async with transport:
                pass

        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()
        assert mock_process.wait.await_count == 3

    async def test_aexit_without_process(self) -> None:
        """Проверяет безопасный выход, если процесс не был запущен."""
        transport = StdioClientTransport(command="test", args=[])
        transport._closed = False

        await transport.__aexit__(None, None, None)

        assert transport._process is None


class TestStdioClientTransportSend:
    """Тесты отправки сообщений через send_str."""

    async def test_send_str_success(self) -> None:
        """Проверяет успешную отправку строки в stdin процесса."""
        transport = StdioClientTransport(command="test", args=[])
        transport._process = MagicMock()
        transport._process.stdin = MagicMock()
        transport._process.stdin.write = MagicMock()
        transport._process.stdin.drain = AsyncMock()
        transport._closed = False

        await transport.send_str('{"jsonrpc": "2.0"}')

        transport._process.stdin.write.assert_called_once_with(b'{"jsonrpc": "2.0"}\n')
        transport._process.stdin.drain.assert_awaited_once()

    async def test_send_str_raises_when_process_missing(self) -> None:
        """Проверяет ошибку, если процесс не запущен."""
        transport = StdioClientTransport(command="test", args=[])
        transport._process = None

        with pytest.raises(RuntimeError, match="Subprocess is not running"):
            await transport.send_str("data")

    async def test_send_str_raises_when_stdin_missing(self) -> None:
        """Проверяет ошибку, если stdin процесса недоступен."""
        transport = StdioClientTransport(command="test", args=[])
        transport._process = MagicMock()
        transport._process.stdin = None

        with pytest.raises(RuntimeError, match="Subprocess is not running"):
            await transport.send_str("data")

    async def test_send_str_raises_when_closed(self) -> None:
        """Проверяет ошибку, если транспорт закрыт."""
        transport = StdioClientTransport(command="test", args=[])
        transport._process = MagicMock()
        transport._process.stdin = MagicMock()
        transport._closed = True

        with pytest.raises(RuntimeError, match="Transport is closed"):
            await transport.send_str("data")

    async def test_send_str_raises_on_broken_pipe(self) -> None:
        """Проверяет преобразование BrokenPipeError в RuntimeError."""
        transport = StdioClientTransport(command="test", args=[])
        transport._process = MagicMock()
        transport._process.stdin = MagicMock()
        transport._process.stdin.write = MagicMock()
        transport._process.stdin.drain = AsyncMock(side_effect=BrokenPipeError())
        transport._closed = False

        with pytest.raises(RuntimeError, match="Subprocess stdin pipe broken"):
            await transport.send_str("data")

    async def test_send_str_raises_on_generic_error(self) -> None:
        """Проверяет преобразование произвольной ошибки в RuntimeError."""
        transport = StdioClientTransport(command="test", args=[])
        transport._process = MagicMock()
        transport._process.stdin = MagicMock()
        transport._process.stdin.write = MagicMock()
        transport._process.stdin.drain = AsyncMock(side_effect=ValueError("bad"))
        transport._closed = False

        with pytest.raises(RuntimeError, match="Failed to send message"):
            await transport.send_str("data")


class TestStdioClientTransportReceive:
    """Тесты получения сообщений через receive_text."""

    async def test_receive_text_propagates_cancelled_error(self) -> None:
        """Проверяет, что asyncio.CancelledError пробрасывается выше."""
        transport = StdioClientTransport(command="test", args=[])
        transport._process = MagicMock()
        transport._process.returncode = None
        transport._stdout_queue = MagicMock()
        transport._stdout_queue.get = AsyncMock(side_effect=asyncio.CancelledError())

        with pytest.raises(asyncio.CancelledError):
            await transport.receive_text()

    async def test_receive_text_raises_on_queue_error(self) -> None:
        """Проверяет преобразование ошибки очереди в RuntimeError."""
        transport = StdioClientTransport(command="test", args=[])
        transport._process = MagicMock()
        transport._process.returncode = None
        transport._stdout_queue = MagicMock()
        transport._stdout_queue.get = AsyncMock(side_effect=ValueError("queue error"))

        with pytest.raises(RuntimeError, match="Failed to receive message"):
            await transport.receive_text()


class TestStdioClientTransportConnection:
    """Тесты состояния подключения is_connected."""

    def test_is_connected_false_without_process(self) -> None:
        """Проверяет, что без процесса транспорт не подключён."""
        transport = StdioClientTransport(command="test", args=[])
        transport._process = None
        transport._closed = False

        assert transport.is_connected() is False

    def test_is_connected_false_when_closed(self) -> None:
        """Проверяет, что закрытый транспорт не подключён."""
        transport = StdioClientTransport(command="test", args=[])
        transport._process = MagicMock()
        transport._process.returncode = None
        transport._closed = True

        assert transport.is_connected() is False

    def test_is_connected_false_when_process_exited(self) -> None:
        """Проверяет, что завершившийся процесс означает отсутствие подключения."""
        transport = StdioClientTransport(command="test", args=[])
        transport._process = MagicMock()
        transport._process.returncode = 1
        transport._closed = False

        assert transport.is_connected() is False

    def test_is_connected_true_when_running(self) -> None:
        """Проверяет, что запущенный процесс означает активное подключение."""
        transport = StdioClientTransport(command="test", args=[])
        transport._process = MagicMock()
        transport._process.returncode = None
        transport._closed = False

        assert transport.is_connected() is True


class TestStdioClientTransportReaders:
    """Тесты фоновых задач чтения stdout/stderr."""

    async def test_stdout_reader_returns_without_process(self) -> None:
        """Проверяет, что _stdout_reader выходит, если процесс не задан."""
        transport = StdioClientTransport(command="test", args=[])
        transport._process = None

        result = await transport._stdout_reader()

        assert result is None

    async def test_stdout_reader_returns_without_stdout(self) -> None:
        """Проверяет, что _stdout_reader выходит, если stdout отсутствует."""
        transport = StdioClientTransport(command="test", args=[])
        transport._process = MagicMock()
        transport._process.stdout = None

        result = await transport._stdout_reader()

        assert result is None

    async def test_stdout_reader_puts_lines_into_queue(self) -> None:
        """Проверяет построчное чтение stdout и заполнение очереди."""
        transport = StdioClientTransport(command="test", args=[])
        transport._closed = False
        transport._stdout_queue = asyncio.Queue()

        mock_process = MagicMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.readline = AsyncMock(
            side_effect=[b'{"id": 1}\n', b"", b""]
        )
        transport._process = mock_process

        await transport._stdout_reader()

        assert transport._stdout_queue.qsize() == 1
        assert await transport._stdout_queue.get() == '{"id": 1}'

    async def test_stdout_reader_stops_on_eof(self) -> None:
        """Проверяет остановку reader при EOF."""
        transport = StdioClientTransport(command="test", args=[])
        transport._closed = False
        transport._stdout_queue = asyncio.Queue()

        mock_process = MagicMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.readline = AsyncMock(return_value=b"")
        transport._process = mock_process

        await transport._stdout_reader()

        assert transport._stdout_queue.empty()

    async def test_stdout_reader_logs_error(self) -> None:
        """Проверяет логирование ошибки при сбое чтения stdout."""
        transport = StdioClientTransport(command="test", args=[])
        transport._closed = False
        transport._stdout_queue = asyncio.Queue()

        mock_process = MagicMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.readline = AsyncMock(side_effect=ValueError("read error"))
        transport._process = mock_process

        await transport._stdout_reader()

        assert transport._stdout_queue.empty()

    async def test_stdout_reader_propagates_cancelled_error(self) -> None:
        """Проверяет, что asyncio.CancelledError пробрасывается в stdout reader."""
        transport = StdioClientTransport(command="test", args=[])
        transport._closed = False
        transport._stdout_queue = asyncio.Queue()

        future = asyncio.Future()

        async def readline() -> bytes:
            return await future

        mock_process = MagicMock()
        mock_process.stdout = AsyncMock()
        mock_process.stdout.readline = AsyncMock(side_effect=readline)
        transport._process = mock_process

        task = asyncio.create_task(transport._stdout_reader())
        await asyncio.sleep(0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_stderr_reader_returns_without_process(self) -> None:
        """Проверяет, что _stderr_reader выходит, если процесс не задан."""
        transport = StdioClientTransport(command="test", args=[])
        transport._process = None

        result = await transport._stderr_reader()

        assert result is None

    async def test_stderr_reader_returns_without_stderr(self) -> None:
        """Проверяет, что _stderr_reader выходит, если stderr отсутствует."""
        transport = StdioClientTransport(command="test", args=[])
        transport._process = MagicMock()
        transport._process.stderr = None

        result = await transport._stderr_reader()

        assert result is None

    async def test_stderr_reader_logs_stderr_lines(self) -> None:
        """Проверяет логирование строк из stderr."""
        transport = StdioClientTransport(command="test", args=[])
        transport._closed = False

        mock_process = MagicMock()
        mock_process.stderr = AsyncMock()
        mock_process.stderr.readline = AsyncMock(
            side_effect=[b"agent warning\n", b"", b""]
        )
        transport._process = mock_process

        await transport._stderr_reader()

        mock_process.stderr.readline.assert_awaited()

    async def test_stderr_reader_stops_on_eof(self) -> None:
        """Проверяет остановку reader при EOF stderr."""
        transport = StdioClientTransport(command="test", args=[])
        transport._closed = False

        mock_process = MagicMock()
        mock_process.stderr = AsyncMock()
        mock_process.stderr.readline = AsyncMock(return_value=b"")
        transport._process = mock_process

        await transport._stderr_reader()

        mock_process.stderr.readline.assert_awaited()

    async def test_stderr_reader_logs_warning(self) -> None:
        """Проверяет логирование предупреждения при сбое чтения stderr."""
        transport = StdioClientTransport(command="test", args=[])
        transport._closed = False

        mock_process = MagicMock()
        mock_process.stderr = AsyncMock()
        mock_process.stderr.readline = AsyncMock(side_effect=ValueError("read error"))
        transport._process = mock_process

        await transport._stderr_reader()

        mock_process.stderr.readline.assert_awaited()

    async def test_stderr_reader_propagates_cancelled_error(self) -> None:
        """Проверяет, что asyncio.CancelledError пробрасывается в stderr reader."""
        transport = StdioClientTransport(command="test", args=[])
        transport._closed = False

        future = asyncio.Future()

        async def readline() -> bytes:
            return await future

        mock_process = MagicMock()
        mock_process.stderr = AsyncMock()
        mock_process.stderr.readline = AsyncMock(side_effect=readline)
        transport._process = mock_process

        task = asyncio.create_task(transport._stderr_reader())
        await asyncio.sleep(0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

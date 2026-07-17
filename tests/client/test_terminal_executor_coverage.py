"""Дополнительные тесты для покрытия TerminalExecutor.

Покрывает:
- shlex ValueError при авто-разбиении
- _read_output: stdout=None, лимит байт, ошибки
- wait_for_exit для уже завершённого процесса
- ошибки в kill_terminal, release_terminal, cleanup_all
- execute: объединение stderr, общее исключение
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, Mock, patch

import pytest

from codelab.client.infrastructure.services.terminal_executor import (
    TerminalExecutor,
    TerminalSession,
    TerminalState,
)


@pytest.fixture
async def executor() -> AsyncGenerator[TerminalExecutor, None]:
    """TerminalExecutor с teardown: закрывает subprocess-транспорты ДО закрытия
    event loop, иначе их __del__ при GC пишет unraisable "Event loop is closed"
    (order-dependent, P0-3c). Использовать во всех тестах, порождающих РЕАЛЬНЫЙ
    подпроцесс.
    """
    ex = TerminalExecutor()
    yield ex
    await ex.cleanup_all()


class TestTerminalExecutorCreateEdgeCases:
    """Тесты для create_terminal с edge cases."""

    @pytest.mark.asyncio
    async def test_create_terminal_ignores_shlex_value_error(self) -> None:
        """create_terminal игнорирует ValueError от shlex.split."""
        executor = TerminalExecutor()

        mock_process = Mock()
        mock_process.stdout = Mock()
        mock_process.stdout.readline = AsyncMock(return_value=b"")
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.returncode = 0

        with patch("shlex.split", side_effect=ValueError("unclosed quote")):
            with patch(
                "asyncio.create_subprocess_exec",
                AsyncMock(return_value=mock_process),
            ):
                terminal_id = await executor.create_terminal("echo hello")

        session = executor._terminals[terminal_id]
        assert session.command == "echo hello"
        assert session.args == []


class TestTerminalExecutorReadOutput:
    """Тесты для _read_output."""

    @pytest.mark.asyncio
    async def test_read_output_warns_when_stdout_is_none(self) -> None:
        """_read_output логирует warning если stdout=None."""
        executor = TerminalExecutor()
        process = Mock()
        process.stdout = None
        session = TerminalSession(
            terminal_id="term_test",
            command="cmd",
            args=[],
            process=process,
            state=TerminalState.RUNNING,
        )

        await executor._read_output(session)

    @pytest.mark.asyncio
    async def test_read_output_trims_by_byte_limit(self, executor: TerminalExecutor) -> None:
        """_read_output обрезает буфер при превышении byte limit."""
        terminal_id = await executor.create_terminal("printf", ["%s", "hello\nworld\n"])
        session = executor._terminals[terminal_id]
        session.output_byte_limit = 8

        # Перезаписываем буфер вручную для контроля
        session.output_buffer = ["first line\n", "second line\n", "third line\n"]

        await executor._read_output(session)

        # Буфер должен быть обрезан до byte_limit
        combined = "".join(session.output_buffer)
        assert len(combined.encode("utf-8")) <= 8
        # was_truncated должен быть установлен
        assert session.was_truncated is True

    @pytest.mark.asyncio
    async def test_read_output_handles_exception(self) -> None:
        """_read_output логирует исключения."""
        executor = TerminalExecutor()
        process = Mock()
        process.stdout = Mock()
        process.stdout.readline = AsyncMock(side_effect=RuntimeError("read error"))
        session = TerminalSession(
            terminal_id="term_test",
            command="cmd",
            args=[],
            process=process,
            state=TerminalState.RUNNING,
        )

        await executor._read_output(session)


class TestTerminalExecutorWaitForExit:
    """Тесты для wait_for_exit."""

    @pytest.mark.asyncio
    async def test_wait_for_exit_already_exited(self, executor: TerminalExecutor) -> None:
        """wait_for_exit возвращает exit_code если процесс уже завершился."""
        terminal_id = await executor.create_terminal("echo", ["done"])
        await asyncio.sleep(0.2)

        exit_code = await executor.wait_for_exit(terminal_id)

        assert exit_code == 0


class TestTerminalExecutorKillAndReleaseErrors:
    """Тесты для обработки ошибок в kill и release."""

    @staticmethod
    def _register_mock_session(executor: TerminalExecutor, terminal_id: str) -> TerminalSession:
        """Зарегистрировать сессию с мок-процессом (без реального подпроцесса).

        kill/release-тесты мокают `process.kill`; на реальном `sleep 100` это оставило
        бы процесс-сироту и незакрытый subprocess-транспорт → order-dependent unraisable
        "Event loop is closed" при GC (P0-3c). Мок-процесс исключает реальный спавн.
        """
        session = TerminalSession(
            terminal_id=terminal_id,
            command="sleep",
            args=["100"],
            process=Mock(),
            state=TerminalState.RUNNING,
        )
        executor._terminals[terminal_id] = session
        return session

    @pytest.mark.asyncio
    async def test_kill_terminal_raises_runtime_error(self) -> None:
        """kill_terminal бросает RuntimeError при ошибке убийства."""
        executor = TerminalExecutor()
        session = self._register_mock_session(executor, "term_kill")

        session.process.kill = Mock(side_effect=RuntimeError("kill failed"))

        with pytest.raises(RuntimeError, match="Failed to kill terminal"):
            await executor.kill_terminal("term_kill")

    @pytest.mark.asyncio
    async def test_release_terminal_ignores_kill_error(self) -> None:
        """release_terminal игнорирует ошибку при убийстве процесса."""
        executor = TerminalExecutor()
        session = self._register_mock_session(executor, "term_release")

        session.process.kill = Mock(side_effect=RuntimeError("kill failed"))
        session.process.wait = AsyncMock()

        result = await executor.release_terminal("term_release")

        assert result is True
        assert "term_release" not in executor._terminals

    @pytest.mark.asyncio
    async def test_cleanup_all_ignores_release_error(self) -> None:
        """cleanup_all логирует ошибки release и не прерывается."""
        executor = TerminalExecutor()
        session = self._register_mock_session(executor, "term_cleanup")
        session.process.wait = AsyncMock(return_value=0)
        session.process.returncode = 0

        with patch.object(
            executor,
            "release_terminal",
            side_effect=RuntimeError("release failed"),
        ):
            # Не должно бросать исключение
            await executor.cleanup_all()

        # Ошибка release не привела к падению, но терминал остался в реестре
        # т.к. release не отработал. Завершаем вручную.
        assert "term_cleanup" in executor._terminals
        await executor.kill_terminal("term_cleanup")
        await executor.release_terminal("term_cleanup")


class TestTerminalExecutorExecuteEdgeCases:
    """Тесты для edge cases execute."""

    def test_execute_combines_stdout_and_stderr(self) -> None:
        """execute объединяет stdout и stderr в output."""
        executor = TerminalExecutor()

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "stdout content\n"
        mock_result.stderr = "stderr content\n"

        with patch("subprocess.run", return_value=mock_result):
            result = executor.execute("echo hello")

        assert result["success"] is True
        assert "stdout content" in result["output"]
        assert "stderr content" in result["output"]

    def test_execute_handles_generic_exception(self) -> None:
        """execute обрабатывает непредвиденные исключения."""
        executor = TerminalExecutor()

        with patch("subprocess.run", side_effect=RuntimeError("boom")):
            result = executor.execute("echo hello")

        assert result["success"] is False
        assert result["exit_code"] == -1
        assert "Error executing command" in result["output"]

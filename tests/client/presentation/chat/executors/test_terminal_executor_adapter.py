"""Тесты для TerminalExecutorAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.client.presentation.chat.executors.terminal_executor_adapter import (
    TerminalExecutorAdapter,
)


@pytest.fixture
def mock_terminal_executor() -> MagicMock:
    """Создает mock TerminalExecutor."""
    executor = MagicMock()
    executor.create_terminal = AsyncMock(return_value="term_123")
    executor.get_output = AsyncMock(return_value=("output text", True, 0, False))
    executor.wait_for_exit = AsyncMock(return_value=0)
    executor.release_terminal = AsyncMock()
    executor.kill_terminal = AsyncMock(return_value=True)
    return executor


@pytest.fixture
def adapter(mock_terminal_executor: MagicMock) -> TerminalExecutorAdapter:
    """Создает TerminalExecutorAdapter с mock executor."""
    return TerminalExecutorAdapter(mock_terminal_executor)


class TestTerminalExecutorAdapter:
    """Тесты TerminalExecutorAdapter."""

    async def test_create_terminal(
        self, adapter: TerminalExecutorAdapter, mock_terminal_executor: MagicMock
    ) -> None:
        """Тест создания терминала."""
        result = await adapter.create_terminal("ls -la")

        assert result == "term_123"
        mock_terminal_executor.create_terminal.assert_awaited_once_with("ls -la")

    async def test_get_output(
        self, adapter: TerminalExecutorAdapter, mock_terminal_executor: MagicMock
    ) -> None:
        """Тест получения вывода терминала."""
        result = await adapter.get_output("term_123")

        assert result == ("output text", True, 0, False)
        mock_terminal_executor.get_output.assert_awaited_once_with("term_123")

    async def test_get_output_with_error(
        self, adapter: TerminalExecutorAdapter, mock_terminal_executor: MagicMock
    ) -> None:
        """Тест получения вывода с ошибкой."""
        mock_terminal_executor.get_output.return_value = ("error output", True, 1, False)

        result = await adapter.get_output("term_123")

        assert result == ("error output", True, 1, False)

    async def test_wait_for_exit(
        self, adapter: TerminalExecutorAdapter, mock_terminal_executor: MagicMock
    ) -> None:
        """Тест ожидания завершения терминала."""
        result = await adapter.wait_for_exit("term_123")

        assert result == (0, "output text")
        mock_terminal_executor.wait_for_exit.assert_awaited_once_with("term_123")
        # Должен вызвать get_output для получения финального output
        assert mock_terminal_executor.get_output.await_count == 1

    async def test_wait_for_exit_with_none_exit_code(
        self, adapter: TerminalExecutorAdapter, mock_terminal_executor: MagicMock
    ) -> None:
        """Тест ожидания завершения с None exit code."""
        mock_terminal_executor.wait_for_exit.return_value = None
        mock_terminal_executor.get_output.return_value = ("partial output", False, None, False)

        result = await adapter.wait_for_exit("term_123")

        assert result == (None, "partial output")

    async def test_release_terminal(
        self, adapter: TerminalExecutorAdapter, mock_terminal_executor: MagicMock
    ) -> None:
        """Тест освобождения ресурсов терминала."""
        await adapter.release_terminal("term_123")

        mock_terminal_executor.release_terminal.assert_awaited_once_with("term_123")

    async def test_kill_terminal(
        self, adapter: TerminalExecutorAdapter, mock_terminal_executor: MagicMock
    ) -> None:
        """Тест принудительного завершения терминала."""
        result = await adapter.kill_terminal("term_123")

        assert result is True
        mock_terminal_executor.kill_terminal.assert_awaited_once_with("term_123")

    async def test_kill_terminal_failure(
        self, adapter: TerminalExecutorAdapter, mock_terminal_executor: MagicMock
    ) -> None:
        """Тест неудачного принудительного завершения терминала."""
        mock_terminal_executor.kill_terminal.return_value = False

        result = await adapter.kill_terminal("term_123")

        assert result is False

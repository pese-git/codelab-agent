"""Тесты для TerminalCallbackExecutor."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from codelab.client.presentation.chat.executors.terminal_callback_executor import (
    TerminalCallbackExecutor,
)


class MockTerminalExecutor:
    """Mock реализация TerminalExecutorPort для тестов."""

    def __init__(self) -> None:
        self.create_terminal = AsyncMock(return_value="real-terminal-1")
        self.get_output = AsyncMock(return_value=("test output", True, 0, False))
        self.wait_for_exit = AsyncMock(return_value=(0, "final output"))
        self.release_terminal = AsyncMock()
        self.kill_terminal = AsyncMock(return_value=True)


class TestTerminalCallbackExecutor:
    """Тесты для TerminalCallbackExecutor."""

    @pytest.fixture
    def mock_executor(self) -> MockTerminalExecutor:
        """Создаёт mock исполнитель терминалов."""
        return MockTerminalExecutor()

    @pytest.fixture
    def executor(self, mock_executor: MockTerminalExecutor) -> TerminalCallbackExecutor:
        """Создаёт экземпляр TerminalCallbackExecutor для тестов."""
        return TerminalCallbackExecutor(mock_executor)

    @pytest.mark.asyncio
    async def test_create_terminal_success(
        self, executor: TerminalCallbackExecutor, mock_executor: MockTerminalExecutor
    ) -> None:
        """create_terminal должен успешно создавать терминал."""
        terminal_id, error = await executor.create_terminal("echo hello")

        assert terminal_id is not None
        assert error is None
        mock_executor.create_terminal.assert_called_once_with("echo hello")

    @pytest.mark.asyncio
    async def test_create_terminal_empty_command(
        self, executor: TerminalCallbackExecutor
    ) -> None:
        """create_terminal должен отклонять пустые команды."""
        terminal_id, error = await executor.create_terminal("")

        assert terminal_id is None
        assert error is not None
        assert "empty" in error.lower()

    @pytest.mark.asyncio
    async def test_create_terminal_whitespace_command(
        self, executor: TerminalCallbackExecutor
    ) -> None:
        """create_terminal должен отклонять команды из пробелов."""
        terminal_id, error = await executor.create_terminal("   ")

        assert terminal_id is None
        assert error is not None
        assert "empty" in error.lower()

    @pytest.mark.asyncio
    async def test_create_terminal_error(
        self, executor: TerminalCallbackExecutor, mock_executor: MockTerminalExecutor
    ) -> None:
        """create_terminal должен обрабатывать ошибки."""
        mock_executor.create_terminal.side_effect = Exception("Creation failed")

        terminal_id, error = await executor.create_terminal("test")

        assert terminal_id is None
        assert error is not None
        assert "failed" in error.lower()

    @pytest.mark.asyncio
    async def test_get_output_success(
        self, executor: TerminalCallbackExecutor
    ) -> None:
        """get_output должен успешно получать вывод терминала."""
        terminal_id, _ = await executor.create_terminal("test")
        assert terminal_id is not None

        output, error = await executor.get_output(terminal_id)

        assert output is not None
        assert error is None
        assert output["output"] == "test output"
        assert output["truncated"] is False

    @pytest.mark.asyncio
    async def test_get_output_not_found(
        self, executor: TerminalCallbackExecutor
    ) -> None:
        """get_output должен возвращать ошибку для несуществующего терминала."""
        output, error = await executor.get_output("nonexistent")

        assert output is None
        assert error is not None
        assert "not found" in error.lower()

    @pytest.mark.asyncio
    async def test_get_output_already_released(
        self, executor: TerminalCallbackExecutor, mock_executor: MockTerminalExecutor
    ) -> None:
        """get_output должен возвращать ошибку для освобождённого терминала."""
        terminal_id, _ = await executor.create_terminal("test")
        assert terminal_id is not None

        # Освобождаем терминал
        await executor.release_terminal(terminal_id)

        output, error = await executor.get_output(terminal_id)

        assert output is None
        assert error is not None
        assert "released" in error.lower()

    @pytest.mark.asyncio
    async def test_wait_for_exit_success(
        self, executor: TerminalCallbackExecutor
    ) -> None:
        """wait_for_exit должен успешно ожидать завершения."""
        terminal_id, _ = await executor.create_terminal("test")
        assert terminal_id is not None

        result, error = await executor.wait_for_exit(terminal_id)

        assert result is not None
        assert error is None
        exit_code, output = result
        assert exit_code == 0
        assert output == "final output"

    @pytest.mark.asyncio
    async def test_wait_for_exit_not_found(
        self, executor: TerminalCallbackExecutor
    ) -> None:
        """wait_for_exit должен возвращать ошибку для несуществующего терминала."""
        result, error = await executor.wait_for_exit("nonexistent")

        assert result is None
        assert error is not None
        assert "not found" in error.lower()

    @pytest.mark.asyncio
    async def test_release_terminal_success(
        self, executor: TerminalCallbackExecutor, mock_executor: MockTerminalExecutor
    ) -> None:
        """release_terminal должен успешно освобождать терминал."""
        terminal_id, _ = await executor.create_terminal("test")
        assert terminal_id is not None

        error = await executor.release_terminal(terminal_id)

        assert error is None
        mock_executor.release_terminal.assert_called_once()

    @pytest.mark.asyncio
    async def test_release_terminal_not_found(
        self, executor: TerminalCallbackExecutor
    ) -> None:
        """release_terminal должен возвращать ошибку для несуществующего терминала."""
        error = await executor.release_terminal("nonexistent")

        assert error is not None
        assert "not found" in error.lower()

    @pytest.mark.asyncio
    async def test_release_terminal_idempotent(
        self, executor: TerminalCallbackExecutor
    ) -> None:
        """release_terminal должен быть идемпотентным."""
        terminal_id, _ = await executor.create_terminal("test")
        assert terminal_id is not None

        # Первое освобождение
        error1 = await executor.release_terminal(terminal_id)
        assert error1 is None

        # Второе освобождение (должно быть успешным)
        error2 = await executor.release_terminal(terminal_id)
        assert error2 is None

    @pytest.mark.asyncio
    async def test_kill_terminal_success(
        self, executor: TerminalCallbackExecutor, mock_executor: MockTerminalExecutor
    ) -> None:
        """kill_terminal должен успешно завершать терминал."""
        terminal_id, _ = await executor.create_terminal("test")
        assert terminal_id is not None

        success, error = await executor.kill_terminal(terminal_id)

        assert success is True
        assert error is None
        mock_executor.kill_terminal.assert_called_once()

    @pytest.mark.asyncio
    async def test_kill_terminal_not_found(
        self, executor: TerminalCallbackExecutor
    ) -> None:
        """kill_terminal должен возвращать ошибку для несуществующего терминала."""
        success, error = await executor.kill_terminal("nonexistent")

        assert success is False
        assert error is not None
        assert "not found" in error.lower()

    @pytest.mark.asyncio
    async def test_kill_terminal_removes_from_cache(
        self, executor: TerminalCallbackExecutor
    ) -> None:
        """kill_terminal должен удалять терминал из кэша."""
        terminal_id, _ = await executor.create_terminal("test")
        assert terminal_id is not None

        # Проверяем что терминал в кэше
        info = await executor.get_terminal_info(terminal_id)
        assert info is not None

        # Убиваем терминал
        await executor.kill_terminal(terminal_id)

        # Проверяем что терминал удалён из кэша
        info = await executor.get_terminal_info(terminal_id)
        assert info is None

    @pytest.mark.asyncio
    async def test_get_terminal_info(
        self, executor: TerminalCallbackExecutor
    ) -> None:
        """get_terminal_info должен возвращать информацию о терминале."""
        terminal_id, _ = await executor.create_terminal("echo test")
        assert terminal_id is not None

        info = await executor.get_terminal_info(terminal_id)

        assert info is not None
        assert info["terminal_id"] == terminal_id
        assert info["command"] == "echo test"
        assert info["is_released"] is False

    @pytest.mark.asyncio
    async def test_get_terminal_info_not_found(
        self, executor: TerminalCallbackExecutor
    ) -> None:
        """get_terminal_info должен возвращать None для несуществующего терминала."""
        info = await executor.get_terminal_info("nonexistent")

        assert info is None

    @pytest.mark.asyncio
    async def test_full_lifecycle(
        self, executor: TerminalCallbackExecutor
    ) -> None:
        """Полный жизненный цикл терминала должен работать корректно."""
        # Создание
        terminal_id, error = await executor.create_terminal("test command")
        assert terminal_id is not None
        assert error is None

        # Получение вывода
        output, error = await executor.get_output(terminal_id)
        assert output is not None
        assert error is None

        # Ожидание завершения
        result, error = await executor.wait_for_exit(terminal_id)
        assert result is not None
        assert error is None

        # Освобождение
        error = await executor.release_terminal(terminal_id)
        assert error is None

        # Проверка что терминал освобождён
        info = await executor.get_terminal_info(terminal_id)
        assert info is not None
        assert info["is_released"] is True

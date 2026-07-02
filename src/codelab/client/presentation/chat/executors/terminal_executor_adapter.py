"""Адаптер для TerminalExecutor к TerminalExecutorPort.

Адаптирует существующий TerminalExecutor из infrastructure к новому
интерфейсу TerminalExecutorPort из chat/executors.
"""

from __future__ import annotations

from codelab.client.infrastructure.services.terminal_executor import TerminalExecutor
from codelab.client.presentation.chat.executors.terminal_callback_executor import (
    TerminalExecutorPort,
)


class TerminalExecutorAdapter(TerminalExecutorPort):
    """Адаптер TerminalExecutor к TerminalExecutorPort.

    Преобразует интерфейс TerminalExecutor к интерфейсу TerminalExecutorPort.
    """

    def __init__(self, executor: TerminalExecutor) -> None:
        """Инициализирует адаптер.

        Args:
            executor: Существующий TerminalExecutor
        """
        self._executor = executor

    async def create_terminal(self, command: str) -> str:
        """Создаёт новый терминал.

        Args:
            command: Команда для выполнения

        Returns:
            ID созданного терминала
        """
        return await self._executor.create_terminal(command)

    async def get_output(
        self, terminal_id: str
    ) -> tuple[str, bool, int | None, bool]:
        """Получает вывод терминала.

        Args:
            terminal_id: ID терминала

        Returns:
            Tuple (output, is_complete, exit_code, truncated)
        """
        return await self._executor.get_output(terminal_id)

    async def wait_for_exit(self, terminal_id: str) -> tuple[int | None, str | None]:
        """Ожидает завершения терминала.

        Args:
            terminal_id: ID терминала

        Returns:
            Tuple (exit_code, output)
        """
        exit_code = await self._executor.wait_for_exit(terminal_id)
        # Получаем финальный output
        output, _, _, _ = await self._executor.get_output(terminal_id)
        return (exit_code, output)

    async def release_terminal(self, terminal_id: str) -> None:
        """Освобождает ресурсы терминала.

        Args:
            terminal_id: ID терминала
        """
        await self._executor.release_terminal(terminal_id)

    async def kill_terminal(self, terminal_id: str) -> bool:
        """Принудительно завершает терминал.

        Args:
            terminal_id: ID терминала

        Returns:
            True если успешно
        """
        return await self._executor.kill_terminal(terminal_id)

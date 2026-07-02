"""TerminalCallbackExecutor - исполнитель callback'ов для терминалов.

Управляет жизненным циклом терминалов: создание, получение вывода,
ожидание завершения, освобождение ресурсов.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

import structlog


class TerminalExecutorPort(Protocol):
    """Протокол для низкоуровневого исполнителя терминалов.

    Определяет интерфейс для взаимодействия с реальной реализацией
    терминалов (например, TerminalExecutor из infrastructure).
    """

    async def create_terminal(self, command: str) -> str:
        """Создаёт новый терминал и возвращает его ID."""
        ...

    async def get_output(
        self, terminal_id: str
    ) -> tuple[str, bool, int | None, bool]:
        """Получает вывод терминала.

        Returns:
            Tuple (output, is_complete, exit_code, truncated)
        """
        ...

    async def wait_for_exit(self, terminal_id: str) -> tuple[int | None, str | None]:
        """Ожидает завершения терминала и возвращает (exit_code, output)."""
        ...

    async def release_terminal(self, terminal_id: str) -> None:
        """Освобождает ресурсы терминала."""
        ...

    async def kill_terminal(self, terminal_id: str) -> bool:
        """Принудительно завершает терминал."""
        ...


@dataclass
class TerminalState:
    """Состояние активного терминала.

    Attributes:
        terminal_id: Уникальный ID терминала
        command: Команда запущенная в терминале
        created_at: Timestamp создания
        is_released: Флаг освобождения ресурсов
    """

    terminal_id: str
    command: str
    created_at: float = field(default_factory=lambda: asyncio.get_event_loop().time())
    is_released: bool = False


class TerminalCallbackExecutor:
    """Исполнитель callback'ов для терминалов.

    Управляет жизненным циклом терминалов через низкоуровневый TerminalExecutorPort.
    Поддерживает кэширование состояния терминалов.

    Attributes:
        _executor: Низкоуровневый исполнитель терминалов
        _terminals: Кэш состояния терминалов
        _lock: Lock для потокобезопасного доступа к кэшу
        _logger: Logger для логирования операций
    """

    def __init__(self, executor: TerminalExecutorPort) -> None:
        """Инициализирует TerminalCallbackExecutor.

        Args:
            executor: Низкоуровневый исполнитель терминалов
        """
        self._executor = executor
        self._terminals: dict[str, TerminalState] = {}
        self._lock = asyncio.Lock()
        self._logger = structlog.get_logger("terminal_callback_executor")

    async def create_terminal(self, command: str) -> tuple[str | None, str | None]:
        """Создаёт новый терминал и выполняет команду.

        Args:
            command: Команда для выполнения

        Returns:
            Tuple (terminal_id, error):
            - (terminal_id, None) при успехе
            - (None, error_message) при ошибке
        """
        if not command or not command.strip():
            error_msg = "Command cannot be empty"
            self._logger.warning("terminal_create_empty_command")
            return None, error_msg

        try:
            # Создаём терминал через низкоуровневый исполнитель
            real_terminal_id = await self._executor.create_terminal(command)

            # Генерируем наш внутренний ID
            internal_id = str(uuid.uuid4())

            # Сохраняем состояние в кэш
            async with self._lock:
                self._terminals[internal_id] = TerminalState(
                    terminal_id=real_terminal_id,
                    command=command,
                )

            self._logger.info(
                "terminal_created",
                internal_id=internal_id,
                real_id=real_terminal_id,
                command=command,
            )
            return internal_id, None

        except Exception as e:
            error_msg = f"Failed to create terminal: {e}"
            self._logger.error(
                "terminal_create_error",
                command=command,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None, error_msg

    async def get_output(self, terminal_id: str) -> tuple[dict[str, Any] | None, str | None]:
        """Получает вывод терминала.

        Args:
            terminal_id: Внутренний ID терминала

        Returns:
            Tuple (output_data, error):
            - (output_data, None) при успехе
            - (None, error_message) при ошибке
        """
        async with self._lock:
            state = self._terminals.get(terminal_id)

        if state is None:
            error_msg = f"Terminal not found: {terminal_id}"
            self._logger.warning(
                "terminal_get_output_not_found",
                terminal_id=terminal_id,
            )
            return None, error_msg

        if state.is_released:
            error_msg = f"Terminal already released: {terminal_id}"
            self._logger.warning(
                "terminal_get_output_already_released",
                terminal_id=terminal_id,
            )
            return None, error_msg

        try:
            output, is_complete, exit_code, truncated = await self._executor.get_output(
                state.terminal_id
            )

            # Сформировать ответ согласно ACP спецификации
            output_data: dict[str, Any] = {
                "output": output,
                "truncated": truncated,
            }

            if is_complete:
                output_data["exitStatus"] = {
                    "exitCode": exit_code,
                    "signal": None,
                }

            self._logger.debug(
                "terminal_output_retrieved",
                terminal_id=terminal_id,
                output_size=len(output),
                truncated=truncated,
            )
            return output_data, None

        except Exception as e:
            error_msg = f"Failed to get terminal output: {e}"
            self._logger.error(
                "terminal_get_output_error",
                terminal_id=terminal_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None, error_msg

    async def wait_for_exit(
        self, terminal_id: str
    ) -> tuple[tuple[int | None, str | None] | None, str | None]:
        """Ожидает завершения терминала.

        Args:
            terminal_id: Внутренний ID терминала

        Returns:
            Tuple ((exit_code, output), error):
            - ((exit_code, output), None) при успехе
            - (None, error_message) при ошибке
        """
        async with self._lock:
            state = self._terminals.get(terminal_id)

        if state is None:
            error_msg = f"Terminal not found: {terminal_id}"
            self._logger.warning(
                "terminal_wait_not_found",
                terminal_id=terminal_id,
            )
            return None, error_msg

        if state.is_released:
            error_msg = f"Terminal already released: {terminal_id}"
            self._logger.warning(
                "terminal_wait_already_released",
                terminal_id=terminal_id,
            )
            return None, error_msg

        try:
            exit_code, output = await self._executor.wait_for_exit(state.terminal_id)

            self._logger.info(
                "terminal_exited",
                terminal_id=terminal_id,
                exit_code=exit_code,
            )
            return (exit_code, output), None

        except TimeoutError:
            error_msg = "Timeout waiting for terminal exit"
            self._logger.warning(
                "terminal_wait_timeout",
                terminal_id=terminal_id,
            )
            return (None, error_msg), None

        except Exception as e:
            error_msg = f"Failed to wait for terminal exit: {e}"
            self._logger.error(
                "terminal_wait_error",
                terminal_id=terminal_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None, error_msg

    async def release_terminal(self, terminal_id: str) -> str | None:
        """Освобождает ресурсы терминала.

        Args:
            terminal_id: Внутренний ID терминала

        Returns:
            None при успехе, error_message при ошибке
        """
        async with self._lock:
            state = self._terminals.get(terminal_id)

            if state is None:
                error_msg = f"Terminal not found: {terminal_id}"
                self._logger.warning(
                    "terminal_release_not_found",
                    terminal_id=terminal_id,
                )
                return error_msg

            if state.is_released:
                self._logger.debug(
                    "terminal_already_released",
                    terminal_id=terminal_id,
                )
                return None

        try:
            await self._executor.release_terminal(state.terminal_id)

            # Помечаем как освобождённый
            async with self._lock:
                if terminal_id in self._terminals:
                    self._terminals[terminal_id].is_released = True

            self._logger.info(
                "terminal_released",
                terminal_id=terminal_id,
            )
            return None

        except Exception as e:
            error_msg = f"Failed to release terminal: {e}"
            self._logger.error(
                "terminal_release_error",
                terminal_id=terminal_id,
                error=str(e),
                error_type=type(e).__name__,
            )

            # Всё равно помечаем как освобождённый чтобы избежать утечек
            async with self._lock:
                if terminal_id in self._terminals:
                    self._terminals[terminal_id].is_released = True

            return error_msg

    async def kill_terminal(self, terminal_id: str) -> tuple[bool, str | None]:
        """Принудительно завершает терминал.

        Args:
            terminal_id: Внутренний ID терминала

        Returns:
            Tuple (success, error):
            - (True, None) при успехе
            - (False, error_message) при ошибке
        """
        async with self._lock:
            state = self._terminals.get(terminal_id)

            if state is None:
                error_msg = f"Terminal not found: {terminal_id}"
                self._logger.warning(
                    "terminal_kill_not_found",
                    terminal_id=terminal_id,
                )
                return False, error_msg

        try:
            success = await self._executor.kill_terminal(state.terminal_id)

            # Удаляем из кэша
            async with self._lock:
                self._terminals.pop(terminal_id, None)

            self._logger.info(
                "terminal_killed",
                terminal_id=terminal_id,
                success=success,
            )
            return success, None

        except Exception as e:
            error_msg = f"Failed to kill terminal: {e}"
            self._logger.error(
                "terminal_kill_error",
                terminal_id=terminal_id,
                error=str(e),
                error_type=type(e).__name__,
            )

            # Всё равно удаляем из кэша
            async with self._lock:
                self._terminals.pop(terminal_id, None)

            return False, error_msg

    async def get_terminal_info(self, terminal_id: str) -> dict[str, Any] | None:
        """Получает информацию о терминале.

        Args:
            terminal_id: Внутренний ID терминала

        Returns:
            Dict с информацией о терминале или None если не найден
        """
        async with self._lock:
            state = self._terminals.get(terminal_id)

        if state is None:
            return None

        return {
            "terminal_id": terminal_id,
            "real_terminal_id": state.terminal_id,
            "command": state.command,
            "created_at": state.created_at,
            "is_released": state.is_released,
        }

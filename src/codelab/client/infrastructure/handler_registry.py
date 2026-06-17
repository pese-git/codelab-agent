"""Реестр обработчиков ACP-запросов от сервера.

Модуль предоставляет:
- Централизованное управление обработчиками
- Регистрацию и вызов обработчиков по типам
- Поддержку async и sync обработчиков
- Типизированный интерфейс

Пример использования:
    registry = HandlerRegistry()
    registry.register_permission_handler(my_permission_handler)
    registry.register_fs_handler("read", my_fs_read_handler)
    
    result = await registry.handle_permission(permission_data)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, cast

import structlog

logger = structlog.get_logger("acp_client.handler_registry")

# Type aliases для обработчиков
PermissionHandler = Callable[[dict[str, Any]], str | None | Awaitable[str | None]]
FsReadHandler = Callable[[str], str]
FsWriteHandler = Callable[[str, str], str | None]
TerminalCreateHandler = Callable[[str], str]
TerminalOutputHandler = Callable[[str], str]
TerminalWaitHandler = Callable[[str], int | tuple[int | None, str | None]]
TerminalReleaseHandler = Callable[[str], None]
TerminalKillHandler = Callable[[str], bool]

# Union тип для всех обработчиков
Handler = (
    PermissionHandler
    | FsReadHandler
    | FsWriteHandler
    | TerminalCreateHandler
    | TerminalOutputHandler
    | TerminalWaitHandler
    | TerminalReleaseHandler
    | TerminalKillHandler
)


class HandlerRegistry:
    """Реестр обработчиков для RPC-запросов от сервера.

    Класс управляет регистрацией и вызовом обработчиков:
    - Permission обработчиков (для session/request_permission)
    - FileSystem обработчиков (read/write запросы)
    - Terminal обработчиков (create/output/wait/release/kill)

    Пример использования:
        registry = HandlerRegistry()
        registry.register_permission_handler(lambda x: "approve")
        result = await registry.handle_permission({...})
    """

    def __init__(self) -> None:
        """Инициализирует пустой реестр обработчиков."""
        # Permission обработчик
        self._permission_handler: PermissionHandler | None = None

        # FileSystem обработчики
        self._fs_read_handler: FsReadHandler | None = None
        self._fs_write_handler: FsWriteHandler | None = None

        # Terminal обработчики
        self._terminal_create_handler: TerminalCreateHandler | None = None
        self._terminal_output_handler: TerminalOutputHandler | None = None
        self._terminal_wait_handler: TerminalWaitHandler | None = None
        self._terminal_release_handler: TerminalReleaseHandler | None = None
        self._terminal_kill_handler: TerminalKillHandler | None = None

        # Generic handlers для плагинов
        self._generic_handlers: dict[str, Any] = {}

        logger.debug("handler_registry_initialized")

    def register(self, name: str, handler: Any) -> None:
        """Регистрирует generic обработчик по имени (для плагинов).

        Args:
            name: Уникальное имя обработчика (e.g., "my_handler", "custom_fs")
            handler: Обработчик (Handler Protocol compatible)
        """
        self._generic_handlers[name] = handler
        logger.debug("generic_handler_registered", handler_name=name)

    def get(self, name: str) -> Any | None:
        """Получает зарегистрированный обработчик по имени.

        Args:
            name: Имя обработчика

        Returns:
            Обработчик или None если не найден
        """
        return self._generic_handlers.get(name)

    # === Permission обработчики ===

    def register_permission_handler(self, handler: PermissionHandler | None) -> None:
        """Регистрирует обработчик для session/request_permission.

        Args:
            handler: Callable обработчик или None для отмены

        Пример:
            async def approve_permission(data):
                return "approve"
            registry.register_permission_handler(approve_permission)
        """
        self._permission_handler = handler
        logger.debug("permission_handler_registered", has_handler=handler is not None)

    async def handle_permission(self, data: dict[str, Any]) -> str | None:
        """Вызывает зарегистрированный обработчик permission.

        Args:
            data: Данные permission запроса

        Returns:
            Результат обработчика (обычно "approve" или "deny") или None

        Raises:
            RuntimeError: Если обработчик не зарегистрирован
        """
        if self._permission_handler is None:
            logger.warning("permission_handler_not_registered")
            raise RuntimeError("Permission handler is not registered")

        try:
            result = self._permission_handler(data)
            # Поддерживаем как async, так и sync обработчики
            if isinstance(result, Awaitable):
                result = await result
            logger.debug("permission_handled", result=result)
            return cast(str | None, result)
        except Exception as e:
            msg = f"Permission handler failed: {e}"
            logger.error("permission_handler_error", error=str(e))
            raise RuntimeError(msg) from e

    # === FileSystem обработчики ===

    def register_fs_read_handler(self, handler: FsReadHandler | None) -> None:
        """Регистрирует обработчик для session/fs_read.

        Args:
            handler: Callable(path: str) -> str обработчик

        Пример:
            def read_file(path):
                with open(path) as f:
                    return f.read()
            registry.register_fs_read_handler(read_file)
        """
        self._fs_read_handler = handler
        logger.debug("fs_read_handler_registered", has_handler=handler is not None)

    def register_fs_write_handler(self, handler: FsWriteHandler | None) -> None:
        """Регистрирует обработчик для session/fs_write.

        Args:
            handler: Callable(path: str, content: str) -> str | None обработчик

        Пример:
            def write_file(path, content):
                with open(path, 'w') as f:
                    f.write(content)
                return None  # OK
            registry.register_fs_write_handler(write_file)
        """
        self._fs_write_handler = handler
        logger.debug("fs_write_handler_registered", has_handler=handler is not None)

    def handle_fs_read(self, path: str) -> str:
        """Вызывает обработчик для чтения файла.

        Args:
            path: Путь к файлу

        Returns:
            Содержимое файла

        Raises:
            RuntimeError: Если обработчик не зарегистрирован
        """
        if self._fs_read_handler is None:
            logger.warning("fs_read_handler_not_registered")
            raise RuntimeError("FS read handler is not registered")

        try:
            result = self._fs_read_handler(path)
            logger.debug("fs_read_handled", path=path)
            return result
        except Exception as e:
            msg = f"FS read handler failed: {e}"
            logger.error("fs_read_handler_error", error=str(e), path=path)
            raise RuntimeError(msg) from e

    def handle_fs_write(self, path: str, content: str) -> str | None:
        """Вызывает обработчик для записи файла.

        Args:
            path: Путь к файлу
            content: Содержимое для записи

        Returns:
            Ошибка (если есть) или None

        Raises:
            RuntimeError: Если обработчик не зарегистрирован
        """
        if self._fs_write_handler is None:
            logger.warning("fs_write_handler_not_registered")
            raise RuntimeError("FS write handler is not registered")

        try:
            result = self._fs_write_handler(path, content)
            logger.debug("fs_write_handled", path=path)
            return result
        except Exception as e:
            msg = f"FS write handler failed: {e}"
            logger.error("fs_write_handler_error", error=str(e), path=path)
            raise RuntimeError(msg) from e

    # === Terminal обработчики ===

    def register_terminal_create_handler(self, handler: TerminalCreateHandler | None) -> None:
        """Регистрирует обработчик для создания terminal."""
        self._terminal_create_handler = handler
        logger.debug("terminal_create_handler_registered", has_handler=handler is not None)

    def register_terminal_output_handler(self, handler: TerminalOutputHandler | None) -> None:
        """Регистрирует обработчик для получения output из terminal."""
        self._terminal_output_handler = handler
        logger.debug("terminal_output_handler_registered", has_handler=handler is not None)

    def register_terminal_wait_handler(self, handler: TerminalWaitHandler | None) -> None:
        """Регистрирует обработчик для ожидания terminal."""
        self._terminal_wait_handler = handler
        logger.debug("terminal_wait_handler_registered", has_handler=handler is not None)

    def register_terminal_release_handler(self, handler: TerminalReleaseHandler | None) -> None:
        """Регистрирует обработчик для освобождения terminal."""
        self._terminal_release_handler = handler
        logger.debug("terminal_release_handler_registered", has_handler=handler is not None)

    def register_terminal_kill_handler(self, handler: TerminalKillHandler | None) -> None:
        """Регистрирует обработчик для завершения terminal."""
        self._terminal_kill_handler = handler
        logger.debug("terminal_kill_handler_registered", has_handler=handler is not None)

    def handle_terminal_create(self, shell: str) -> str:
        """Вызывает обработчик для создания terminal."""
        if self._terminal_create_handler is None:
            raise RuntimeError("Terminal create handler is not registered")
        try:
            result = self._terminal_create_handler(shell)
            logger.debug("terminal_created", shell=shell)
            return result
        except Exception as e:
            msg = f"Terminal create handler failed: {e}"
            logger.error("terminal_create_error", error=str(e))
            raise RuntimeError(msg) from e

    def handle_terminal_output(self, terminal_id: str) -> str:
        """Вызывает обработчик для получения output из terminal."""
        if self._terminal_output_handler is None:
            raise RuntimeError("Terminal output handler is not registered")
        try:
            result = self._terminal_output_handler(terminal_id)
            logger.debug("terminal_output_retrieved", terminal_id=terminal_id)
            return result
        except Exception as e:
            msg = f"Terminal output handler failed: {e}"
            logger.error("terminal_output_error", error=str(e))
            raise RuntimeError(msg) from e

    def handle_terminal_wait(self, terminal_id: str) -> int | tuple[int | None, str | None]:
        """Вызывает обработчик для ожидания terminal."""
        if self._terminal_wait_handler is None:
            raise RuntimeError("Terminal wait handler is not registered")
        try:
            result = self._terminal_wait_handler(terminal_id)
            logger.debug("terminal_waited", terminal_id=terminal_id)
            return result
        except Exception as e:
            msg = f"Terminal wait handler failed: {e}"
            logger.error("terminal_wait_error", error=str(e))
            raise RuntimeError(msg) from e

    def handle_terminal_release(self, terminal_id: str) -> None:
        """Вызывает обработчик для освобождения terminal."""
        if self._terminal_release_handler is None:
            raise RuntimeError("Terminal release handler is not registered")
        try:
            self._terminal_release_handler(terminal_id)
            logger.debug("terminal_released", terminal_id=terminal_id)
        except Exception as e:
            msg = f"Terminal release handler failed: {e}"
            logger.error("terminal_release_error", error=str(e))
            raise RuntimeError(msg) from e

    def handle_terminal_kill(self, terminal_id: str) -> bool:
        """Вызывает обработчик для завершения terminal."""
        if self._terminal_kill_handler is None:
            raise RuntimeError("Terminal kill handler is not registered")
        try:
            result = self._terminal_kill_handler(terminal_id)
            logger.debug("terminal_killed", terminal_id=terminal_id)
            return result
        except Exception as e:
            msg = f"Terminal kill handler failed: {e}"
            logger.error("terminal_kill_error", error=str(e))
            raise RuntimeError(msg) from e

    # === Регистрация из dict ===

    def register_all(
        self,
        *,
        permission: PermissionHandler | None = None,
        fs_read: FsReadHandler | None = None,
        fs_write: FsWriteHandler | None = None,
        terminal_create: TerminalCreateHandler | None = None,
        terminal_output: TerminalOutputHandler | None = None,
        terminal_wait: TerminalWaitHandler | None = None,
        terminal_release: TerminalReleaseHandler | None = None,
        terminal_kill: TerminalKillHandler | None = None,
    ) -> None:
        """Регистрирует все обработчики за один раз.

        Args:
            permission: Обработчик для permission запросов
            fs_read: Обработчик для чтения файлов
            fs_write: Обработчик для записи файлов
            terminal_create: Обработчик для создания terminal
            terminal_output: Обработчик для получения output
            terminal_wait: Обработчик для ожидания
            terminal_release: Обработчик для освобождения
            terminal_kill: Обработчик для завершения

        Пример:
            registry.register_all(
                permission=my_permission_handler,
                fs_read=my_fs_read_handler,
            )
        """
        if permission is not None:
            self.register_permission_handler(permission)
        if fs_read is not None:
            self.register_fs_read_handler(fs_read)
        if fs_write is not None:
            self.register_fs_write_handler(fs_write)
        if terminal_create is not None:
            self.register_terminal_create_handler(terminal_create)
        if terminal_output is not None:
            self.register_terminal_output_handler(terminal_output)
        if terminal_wait is not None:
            self.register_terminal_wait_handler(terminal_wait)
        if terminal_release is not None:
            self.register_terminal_release_handler(terminal_release)
        if terminal_kill is not None:
            self.register_terminal_kill_handler(terminal_kill)
        logger.debug("all_handlers_registered")

    def clear(self) -> None:
        """Очищает все зарегистрированные обработчики.

        Пример:
            registry.clear()
        """
        self._permission_handler = None
        self._fs_read_handler = None
        self._fs_write_handler = None
        self._terminal_create_handler = None
        self._terminal_output_handler = None
        self._terminal_wait_handler = None
        self._terminal_release_handler = None
        self._terminal_kill_handler = None
        logger.debug("all_handlers_cleared")

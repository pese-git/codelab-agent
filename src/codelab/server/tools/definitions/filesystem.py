"""Определения для файловых инструментов (fs/*)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from codelab.server.domain.path_boundary import normalize_path as _normalize_path
from codelab.server.tools.base import ToolDefinition, ToolExecutionResult

if TYPE_CHECKING:
    from codelab.server.domain.session import Session
    from codelab.server.tools.base import ToolRegistry
    from codelab.server.tools.executors.decorators.base import ToolExecutorProtocol


class FileSystemToolDefinitions:
    """Фабрика для создания определений файловых инструментов.

    Поддерживает:
    - fs/read_text_file: Чтение текстовых файлов
    - fs/write_text_file: Запись текстовых файлов с diff tracking
    """

    @staticmethod
    def read_text_file() -> ToolDefinition:
        """Создать определение для инструмента fs/read_text_file.

        Позволяет LLM читать содержимое текстовых файлов в окружении клиента
        с поддержкой partial reads (line и limit).

        Returns:
            ToolDefinition для регистрации в реестре.
        """
        return ToolDefinition(
            name="fs/read_text_file",
            description=(
                "Read text file content from client filesystem. "
                "Supports line numbers (1-based) and limits for partial reads."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative file path",
                    },
                    "line": {
                        "type": "integer",
                        "description": "Starting line number (1-based, optional)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of lines to read (optional)",
                    },
                    "operation": {
                        "type": "string",
                        "description": "Internal: operation type (read)",
                    },
                },
                "required": ["path"],
            },
            kind="read",
            requires_permission=True,
        )

    @staticmethod
    def write_text_file() -> ToolDefinition:
        """Создать определение для инструмента fs/write_text_file.

        Позволяет LLM создавать и обновлять текстовые файлы в окружении клиента
        с автоматическим отслеживанием изменений (diff).

        Returns:
            ToolDefinition для регистрации в реестре.
        """
        return ToolDefinition(
            name="fs/write_text_file",
            description=(
                "Write or update text file in client filesystem. "
                "Supports diff generation for tracking changes."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative file path",
                    },
                    "content": {
                        "type": "string",
                        "description": "File content to write",
                    },
                    "operation": {
                        "type": "string",
                        "description": "Internal: operation type (write)",
                    },
                },
                "required": ["path", "content"],
            },
            kind="edit",
            requires_permission=True,
        )

    @staticmethod
    def register_all(
        tool_registry: ToolRegistry,
        executor: ToolExecutorProtocol,
    ) -> None:
        """Зарегистрировать все файловые инструменты в реестре.

        Регистрирует:
        - fs/read_text_file с executor для чтения
        - fs/write_text_file с executor для записи

        Args:
            tool_registry: Реестр инструментов для регистрации
            executor: Executor для выполнения операций с файлами (поддерживает декораторы)
        """

        # Создать обработчик для чтения файлов
        async def read_handler(session: Session, **arguments: Any) -> ToolExecutionResult:
            """Обработчик для fs/read_text_file."""
            # Добавить тип операции в аргументы
            arguments["operation"] = "read"

            # Валидация path ДО RPC (#21): пустой путь и путь-директория раньше
            # уходили в клиент и возвращались сырым -32603/-32002.
            raw_path = arguments.get("path")
            if not isinstance(raw_path, str) or not raw_path.strip():
                return ToolExecutionResult(
                    success=False,
                    error=(
                        "Параметр 'path' обязателен и не может быть пустым: укажите путь к файлу."
                    ),
                )

            # Нормализация — подготовка аргумента для клиента; границу рабочего
            # каталога проверяет шов исполнения (ADR-009, шаг 2б), а не обработчик:
            # иначе её получал бы только тот инструмент, чей автор о ней вспомнил.
            if session.config.cwd:
                arguments["path"] = _normalize_path(session.config.cwd, arguments["path"])

            # Директория — не файл: отклоняем с понятным сообщением, а не сырым RPC-кодом.
            if Path(arguments["path"]).is_dir():
                return ToolExecutionResult(
                    success=False,
                    error=(
                        f"Путь '{arguments['path']}' — директория, а не файл. "
                        f"Используйте команды ls/find для просмотра содержимого каталога."
                    ),
                )
            return await executor.execute(session, arguments)

        # Создать обработчик для записи файлов
        async def write_handler(session: Session, **arguments: Any) -> ToolExecutionResult:
            """Обработчик для fs/write_text_file."""
            # Добавить тип операции в аргументы
            arguments["operation"] = "write"
            # Границу каталога проверяет шов исполнения (ADR-009, шаг 2б).
            if "path" in arguments and session.config.cwd:
                arguments["path"] = _normalize_path(session.config.cwd, arguments["path"])
            return await executor.execute(session, arguments)

        # Зарегистрировать инструменты в реестре
        tool_registry.register(
            FileSystemToolDefinitions.read_text_file(),
            read_handler,
        )
        tool_registry.register(
            FileSystemToolDefinitions.write_text_file(),
            write_handler,
        )

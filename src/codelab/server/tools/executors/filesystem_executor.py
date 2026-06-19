"""Executor для файловых операций через ClientRPC."""

from __future__ import annotations

import difflib
from typing import Any

import structlog

from codelab.server.client_rpc.exceptions import ClientRPCResponseError
from codelab.server.protocol.state import SessionState
from codelab.server.tools.base import ToolExecutionResult
from codelab.server.tools.executors.base import ToolExecutor
from codelab.server.tools.integrations.client_rpc_bridge import ClientRPCBridge
from codelab.server.tools.integrations.permission_checker import PermissionChecker

logger = structlog.get_logger()


class FileSystemToolExecutor(ToolExecutor):
    """Executor для файловых операций через ClientRPC.
    
    Поддерживает:
    - fs/read_text_file (с line и limit)
    - fs/write_text_file (с diff tracking)
    
    Интегрирует проверку разрешений и логирование.
    """

    def __init__(
        self,
        client_rpc_bridge: ClientRPCBridge,
        permission_checker: PermissionChecker,
    ) -> None:
        """Инициализировать executor с зависимостями.
        
        Args:
            client_rpc_bridge: Адаптер для ClientRPCService.
            permission_checker: Адаптер для PermissionManager.
        """
        self._bridge = client_rpc_bridge
        self._permission_checker = permission_checker

    async def execute(
        self,
        session: SessionState,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        """Выполнить инструмент на основе аргументов.
        
        Args:
            session: Состояние сессии.
            arguments: Словарь аргументов инструмента.
                Ожидается поле 'operation' для выбора метода.
                
        Returns:
            ToolExecutionResult с результатом выполнения.
        """
        operation = arguments.get("operation")
        
        if operation == "read":
            return await self.execute_read(
                session=session,
                path=arguments.get("path", ""),
                line=arguments.get("line"),
                limit=arguments.get("limit"),
            )
        elif operation == "write":
            return await self.execute_write(
                session=session,
                path=arguments.get("path", ""),
                content=arguments.get("content", ""),
            )
        else:
            return ToolExecutionResult(
                success=False,
                error=f"Неизвестная операция: {operation}",
            )

    async def execute_read(
        self,
        session: SessionState,
        path: str,
        line: int | None = None,
        limit: int | None = None,
    ) -> ToolExecutionResult:
        """Чтение текстового файла через ClientRPC.
        
        Args:
            session: Состояние сессии.
            path: Путь к файлу.
            line: Начальная строка (1-based, опционально).
            limit: Максимум строк (опционально).
            
        Returns:
            ToolExecutionResult с содержимым файла.
        """
        try:
            logger.debug(
                "Начало выполнения read_text_file",
                extra={"session_id": session.session_id, "path": path},
            )
            
            # Примечание: Проверка разрешений выполняется в
            # PromptOrchestrator._decide_tool_execution() перед вызовом executor.
            # Здесь мы только выполняем операцию.
            
            # Вызов ClientRPC
            content = await self._bridge.read_file(
                session=session,
                path=path,
                line=line,
                limit=limit,
            )
            
            if content is None:
                return ToolExecutionResult(
                    success=False,
                    error=f"Ошибка при чтении файла: {path}",
                )
            
            logger.debug(
                "Файл успешно прочитан",
                extra={
                    "session_id": session.session_id,
                    "path": path,
                    "bytes": len(content),
                },
            )
            
            return ToolExecutionResult(
                success=True,
                output=content,
            )
            
        except ClientRPCResponseError as e:
            logger.error(
                "RPC ошибка при чтении файла",
                extra={
                    "session_id": session.session_id,
                    "path": path,
                    "error": str(e),
                },
            )
            return ToolExecutionResult(
                success=False,
                error=f"Ошибка при чтении файла: {e.message}",
            )

        except Exception as e:
            logger.error(
                "Ошибка при чтении файла",
                extra={
                    "session_id": session.session_id,
                    "path": path,
                    "error": str(e),
                },
            )
            return ToolExecutionResult(
                success=False,
                error=f"Ошибка при чтении файла: {str(e)}",
            )

    async def execute_write(
        self,
        session: SessionState,
        path: str,
        content: str,
    ) -> ToolExecutionResult:
        """Запись текстового файла с diff tracking через ClientRPC.
        
        Args:
            session: Состояние сессии.
            path: Путь к файлу.
            content: Содержимое для записи.
            
        Returns:
            ToolExecutionResult с diff в metadata.
        """
        try:
            logger.debug(
                "Начало выполнения write_text_file",
                extra={
                    "session_id": session.session_id,
                    "path": path,
                    "bytes": len(content),
                },
            )
            
            # Примечание: Проверка разрешений выполняется в
            # PromptOrchestrator._decide_tool_execution() перед вызовом executor.
            # Здесь мы только выполняем операцию.
            
            # Попытка прочитать старое содержимое для diff
            old_content = await self._bridge.read_file(
                session=session,
                path=path,
            )
            
            # Генерировать diff если удалось прочитать старое содержимое
            diff_text = None
            if old_content is not None:
                diff_lines = difflib.unified_diff(
                    old_content.splitlines(keepends=True),
                    content.splitlines(keepends=True),
                    fromfile=f"a/{path}",
                    tofile=f"b/{path}",
                )
                diff_text = "".join(diff_lines)
            
            # Вызов ClientRPC для записи
            success = await self._bridge.write_file(
                session=session,
                path=path,
                content=content,
            )
            
            if not success:
                return ToolExecutionResult(
                    success=False,
                    error=f"Ошибка при записи файла: {path}",
                )
            
            logger.debug(
                "Файл успешно записан",
                extra={
                    "session_id": session.session_id,
                    "path": path,
                    "bytes": len(content),
                },
            )
            
            return ToolExecutionResult(
                success=True,
                output=f"Файл {path} успешно записан",
                metadata={
                    "diff": diff_text,
                    "bytes": len(content),
                },
            )
            
        except ClientRPCResponseError as e:
            logger.error(
                "RPC ошибка при записи файла",
                extra={
                    "session_id": session.session_id,
                    "path": path,
                    "error": str(e),
                },
            )
            return ToolExecutionResult(
                success=False,
                error=f"Ошибка при записи файла: {e.message}",
            )

        except Exception as e:
            logger.error(
                "Ошибка при записи файла",
                extra={
                    "session_id": session.session_id,
                    "path": path,
                    "error": str(e),
                },
            )
            return ToolExecutionResult(
                success=False,
                error=f"Ошибка при записи файла: {str(e)}",
            )

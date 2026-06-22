"""Retry decorator для tool executors.

Добавляет retry логику с exponential backoff для временных ошибок.
Поддерживает разделение на retryable и non-retryable ошибки.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.mcp.exceptions import MCPConnectionError, MCPTimeoutError
from codelab.server.tools.base import ToolExecutionResult

from .base import ToolExecutorDecorator, ToolExecutorProtocol

if TYPE_CHECKING:
    from codelab.server.protocol.state import SessionState

logger = structlog.get_logger()


class RetryDecorator(ToolExecutorDecorator):
    """Добавляет retry логику для временных ошибок.
    
    Использует exponential backoff: delay = backoff_factor ^ attempt.
    Retry применяется только к retryable ошибкам (MCPTimeoutError, MCPConnectionError).
    Non-retryable ошибки (MCPValidationError, MCPServerError) возвращаются сразу.
    
    Example:
        >>> executor = RetryDecorator(
        ...     timeout_executor,
        ...     max_retries=3,
        ...     backoff_factor=2.0,
        ... )
        >>> result = await executor.execute(session, arguments)
    """
    
    # Ошибки, которые можно retry (временные ошибки)
    RETRYABLE_ERRORS: tuple[type[Exception], ...] = (
        MCPTimeoutError,
        MCPConnectionError,
    )
    
    def __init__(
        self,
        wrapped: ToolExecutorProtocol,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
    ) -> None:
        """Инициализация декоратора.
        
        Args:
            wrapped: Оборачиваемый executor.
            max_retries: Максимальное количество попыток (default: 3).
            backoff_factor: Фактор для exponential backoff (default: 2.0).
        """
        super().__init__(wrapped)
        self._max_retries = max_retries
        self._backoff_factor = backoff_factor
    
    async def execute(
        self,
        session: SessionState,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        """Выполнить инструмент с retry.
        
        Args:
            session: Состояние сессии.
            arguments: Аргументы инструмента.
        
        Returns:
            Результат выполнения инструмента.
        
        Raises:
            Exception: Если все попытки исчерпаны и ошибка non-retryable.
        """
        tool_name = arguments.get("tool_name", "unknown")
        last_error: Exception | None = None
        
        for attempt in range(self._max_retries):
            try:
                logger.debug(
                    "retry_attempt",
                    tool_name=tool_name,
                    attempt=attempt + 1,
                    max_retries=self._max_retries,
                    session_id=session.session_id,
                )
                
                result = await self._wrapped.execute(session, arguments)
                
                if attempt > 0:
                    logger.info(
                        "retry_succeeded",
                        tool_name=tool_name,
                        attempt=attempt + 1,
                        session_id=session.session_id,
                    )
                
                return result
                
            except self.RETRYABLE_ERRORS as e:
                last_error = e
                
                if attempt < self._max_retries - 1:
                    delay = self._backoff_factor ** attempt
                    logger.warning(
                        "retryable_error_retrying",
                        tool_name=tool_name,
                        attempt=attempt + 1,
                        delay=delay,
                        error_type=type(e).__name__,
                        error_message=str(e),
                        session_id=session.session_id,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "all_retries_exhausted",
                        tool_name=tool_name,
                        max_retries=self._max_retries,
                        error_type=type(e).__name__,
                        error_message=str(e),
                        session_id=session.session_id,
                    )
            
            except Exception as e:
                # Non-retryable ошибка — возвращаем сразу
                logger.warning(
                    "non_retryable_error",
                    tool_name=tool_name,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    session_id=session.session_id,
                )
                raise
        
        # Все попытки исчерпаны
        # Возвращаем ToolExecutionResult с ошибкой вместо поднятия исключения
        # Это позволяет клиенту получить информативное сообщение об ошибке
        error_message = (
            f"MCP tool '{tool_name}' failed after {self._max_retries} attempts. "
            f"Last error: {last_error}"
        )
        
        logger.error(
            "tool_execution_failed_after_retries",
            tool_name=tool_name,
            max_retries=self._max_retries,
            error_message=error_message,
            session_id=session.session_id,
        )
        
        return ToolExecutionResult(
            success=False,
            error=error_message,
        )
    
    @staticmethod
    def is_retryable_error(error: Exception) -> bool:
        """Проверить, является ли ошибка retryable.
        
        Args:
            error: Исключение для проверки.
        
        Returns:
            True если ошибка retryable (временная).
        """
        return isinstance(error, RetryDecorator.RETRYABLE_ERRORS)

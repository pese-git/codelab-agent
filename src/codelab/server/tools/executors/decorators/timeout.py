"""Timeout decorator для tool executors.

Добавляет timeout для выполнения инструментов через asyncio.wait_for().
При превышении timeout генерирует MCPTimeoutError.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.mcp.exceptions import MCPTimeoutError
from codelab.server.tools.base import ToolExecutionResult

from .base import ToolExecutorDecorator, ToolExecutorProtocol

if TYPE_CHECKING:
    from codelab.server.protocol.state import SessionState

logger = structlog.get_logger()


class TimeoutDecorator(ToolExecutorDecorator):
    """Добавляет timeout для выполнения инструмента.
    
    При превышении timeout генерирует MCPTimeoutError, которое
    может быть обработано RetryDecorator для retry логики.
    
    Example:
        >>> executor = TimeoutDecorator(mcp_executor, timeout=30.0)
        >>> try:
        ...     result = await executor.execute(session, arguments)
        ... except MCPTimeoutError as e:
        ...     print(f"Tool {e.tool_name} timed out after {e.timeout}s")
    """
    
    def __init__(
        self,
        wrapped: ToolExecutorProtocol,
        timeout: float = 30.0,
    ) -> None:
        """Инициализация декоратора.
        
        Args:
            wrapped: Оборачиваемый executor.
            timeout: Timeout в секундах (default: 30.0).
        """
        super().__init__(wrapped)
        self._timeout = timeout
    
    async def execute(
        self,
        session: SessionState,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        """Выполнить инструмент с timeout.
        
        Args:
            session: Состояние сессии.
            arguments: Аргументы инструмента.
        
        Returns:
            Результат выполнения инструмента.
        
        Raises:
            MCPTimeoutError: При превышении timeout.
        """
        tool_name = arguments.get("tool_name", "unknown")
        
        logger.debug(
            "executing_tool_with_timeout",
            tool_name=tool_name,
            timeout=self._timeout,
            session_id=session.session_id,
        )
        
        try:
            result = await asyncio.wait_for(
                self._wrapped.execute(session, arguments),
                timeout=self._timeout,
            )
            
            logger.debug(
                "tool_execution_completed",
                tool_name=tool_name,
                success=result.success,
                session_id=session.session_id,
            )
            
            return result
            
        except TimeoutError:
            logger.warning(
                "tool_execution_timeout",
                tool_name=tool_name,
                timeout=self._timeout,
                session_id=session.session_id,
            )
            raise MCPTimeoutError(tool_name, self._timeout) from None

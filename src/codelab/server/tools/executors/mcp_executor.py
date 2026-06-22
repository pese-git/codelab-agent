"""Executor для MCP инструментов.

Адаптирует MCPManager.call_tool() под интерфейс ToolExecutor.
Конвертирует MCP content → ACP content format.
Обрабатывает timeout и errors.

Использует Decorator Pattern для добавления timeout и retry логики:
Base Executor → TimeoutDecorator → RetryDecorator
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.protocol.state import SessionState
from codelab.server.tools.base import ToolExecutionResult
from codelab.server.tools.executors.base import ToolExecutor
from codelab.server.tools.executors.decorators import (
    RetryDecorator,
    TimeoutDecorator,
    ToolExecutorProtocol,
)

if TYPE_CHECKING:
    from codelab.server.mcp.manager import MCPManager

logger = structlog.get_logger()

# MCP namespace prefix
_MCP_PREFIX = "mcp:"


class MCPToolExecutor(ToolExecutor):
    """Executor для MCP инструментов через MCPManager.

    Делегирует выполнение инструментов MCP серверам через MCPManager.
    Конвертирует результаты MCP в формат ToolExecutionResult.
    
    Использует chain of decorators для добавления timeout и retry:
    - TimeoutDecorator: ограничивает время выполнения
    - RetryDecorator: повторяет вызов при временных ошибках

    Attributes:
        mcp_manager: Менеджер MCP серверов сессии.
        default_timeout: Таймаут выполнения инструмента в секундах.
        max_retries: Максимальное количество попыток при retry.
        backoff_factor: Фактор для exponential backoff.
    """

    def __init__(
        self,
        mcp_manager: MCPManager,
        default_timeout: float = 30.0,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
    ) -> None:
        """Инициализировать executor.

        Args:
            mcp_manager: Менеджер MCP серверов сессии.
            default_timeout: Таймаут выполнения в секундах.
            max_retries: Максимальное количество попыток при retry.
            backoff_factor: Фактор для exponential backoff.
        """
        self._mcp_manager = mcp_manager
        self._default_timeout = default_timeout
        self._max_retries = max_retries
        self._backoff_factor = backoff_factor

    @staticmethod
    def is_mcp_tool(tool_name: str) -> bool:
        """Проверить, является ли инструмент MCP инструментом.

        Args:
            tool_name: Имя инструмента (в ACP формате).

        Returns:
            True если инструмент имеет MCP namespace.
        """
        return tool_name.startswith(_MCP_PREFIX)

    @staticmethod
    def _convert_mcp_content_to_text(content: list[dict[str, Any]]) -> str:
        """Конвертировать MCP content в текстовый формат.

        Поддерживает text, image (base64 metadata), embedded resource.

        Args:
            content: Список MCP content элементов.

        Returns:
            Текстовое представление всех content элементов.
        """
        parts: list[str] = []
        for item in content:
            item_type = item.get("type", "text")

            if item_type == "text":
                parts.append(item.get("text", ""))

            elif item_type == "image":
                # Изображение — описываем metadata, base64 данные не включаем в текст
                mime_type = item.get("mimeType", "image/unknown")
                data_len = len(item.get("data", ""))
                parts.append(f"[Image: {mime_type}, {data_len} bytes base64 data]")

            elif item_type == "resource":
                # Embedded resource — извлекаем содержимое ресурса
                resource = item.get("resource", {})
                if resource.get("text"):
                    parts.append(resource["text"])
                elif resource.get("blob"):
                    mime_type = resource.get("mimeType", "application/octet-stream")
                    parts.append(f"[Embedded resource: {mime_type}, blob data]")
                elif resource.get("uri"):
                    parts.append(f"[Resource link: {resource['uri']}]")
                else:
                    parts.append("[Embedded resource: no content]")

            else:
                # Unknown type — сериализуем как JSON
                parts.append(json.dumps(item, ensure_ascii=False))

        return "\n".join(parts) if parts else ""

    async def execute(
        self,
        session: SessionState,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        """Выполнить MCP инструмент с timeout и retry.
        
        Использует chain of decorators:
        Base Executor → TimeoutDecorator → RetryDecorator
        
        Это обеспечивает:
        - Timeout: предотвращает бесконечное ожидание
        - Retry: устойчивость к временным сбоям (timeout, connection errors)

        Args:
            session: Состояние сессии (используется для получения mcp_manager).
            arguments: Аргументы инструмента, включая 'tool_name'.

        Returns:
            ToolExecutionResult с результатом выполнения.
        """
        tool_name = arguments.get("tool_name", "")

        if not self.is_mcp_tool(tool_name):
            return ToolExecutionResult(
                success=False,
                error=f"Not an MCP tool: {tool_name}",
            )

        if self._mcp_manager is None:
            session_id = session.session_id if session else "unknown"
            return ToolExecutionResult(
                success=False,
                error=f"MCP manager not available for session {session_id}",
            )

        logger.info(
            "executing MCP tool with decorators",
            session_id=session.session_id,
            tool_name=tool_name,
            timeout=self._default_timeout,
            max_retries=self._max_retries,
        )

        # Создаём chain of decorators
        # Base executor → Timeout → Retry
        base_executor = self._create_base_executor()
        timeout_executor = TimeoutDecorator(base_executor, timeout=self._default_timeout)
        retry_executor = RetryDecorator(
            timeout_executor,
            max_retries=self._max_retries,
            backoff_factor=self._backoff_factor,
        )

        # Выполняем через decorated executor
        return await retry_executor.execute(session, arguments)
    
    def _create_base_executor(self) -> ToolExecutorProtocol:
        """Создать базовый executor без декораторов.
        
        Возвращает executor, который выполняет базовую логику
        вызова MCP инструмента через MCPManager.
        
        Returns:
            ToolExecutorProtocol для базового выполнения.
        """
        
        class BaseMCPExecutor:
            """Базовый executor для MCP инструментов."""
            
            def __init__(self, outer: MCPToolExecutor) -> None:
                self._outer = outer
            
            async def execute(
                self,
                session: SessionState,
                arguments: dict[str, Any],
            ) -> ToolExecutionResult:
                """Выполнить MCP инструмент без декораторов."""
                tool_name = arguments.get("tool_name", "")
                
                # Убираем tool_name из arguments перед передачей в MCP
                mcp_arguments = {k: v for k, v in arguments.items() if k != "tool_name"}
                
                try:
                    result = await self._outer._mcp_manager.call_tool(
                        tool_name, mcp_arguments
                    )
                    
                    # Если результат уже ToolExecutionResult — возвращаем напрямую
                    if isinstance(result, ToolExecutionResult):
                        return result
                    
                    # Конвертируем MCP content в текст
                    if hasattr(result, "content") and result.content:
                        output = self._outer._convert_mcp_content_to_text(result.content)
                        is_error = getattr(result, "is_error", False)
                        return ToolExecutionResult(
                            success=not is_error,
                            output=output,
                            error=output if is_error else None,
                        )
                    
                    return ToolExecutionResult(
                        success=True,
                        output=str(result) if result else "",
                    )
                except Exception as exc:
                    logger.error(
                        "MCP tool execution failed",
                        session_id=session.session_id,
                        tool_name=tool_name,
                        error=str(exc),
                        exc_info=True,
                    )
                    return ToolExecutionResult(
                        success=False,
                        error=f"MCP tool execution error: {exc}",
                    )
        
        return BaseMCPExecutor(self)

    async def execute_tool(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        session: SessionState | None = None,
    ) -> ToolExecutionResult:
        """Выполнить MCP инструмент напрямую (без SessionState).

        Args:
            session_id: ID сессии (для логирования).
            tool_name: И MCP инструмента (mcp:server:tool).
            arguments: Аргументы инструмента.
            session: Сессия с mcp_manager.

        Returns:
            ToolExecutionResult с результатом выполнения.
        """
        if session is None:
            return ToolExecutionResult(
                success=False,
                error="Session required for MCP tool execution",
            )

        return await self.execute(session, {"tool_name": tool_name, **arguments})

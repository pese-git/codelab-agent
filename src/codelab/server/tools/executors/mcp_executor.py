"""Executor для MCP инструментов.

Адаптирует MCPManager.call_tool() под интерфейс ToolExecutor.
Конвертирует MCP content → ACP content format.
Обрабатывает timeout и errors.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.protocol.state import SessionState
from codelab.server.tools.base import ToolExecutionResult
from codelab.server.tools.executors.base import ToolExecutor

if TYPE_CHECKING:
    from codelab.server.mcp.manager import MCPManager

logger = structlog.get_logger()

# MCP namespace prefix
_MCP_PREFIX = "mcp:"


class MCPToolExecutor(ToolExecutor):
    """Executor для MCP инструментов через MCPManager.

    Делегирует выполнение инструментов MCP серверам через MCPManager.
    Конвертирует результаты MCP в формат ToolExecutionResult.

    Attributes:
        mcp_manager: Менеджер MCP серверов сессии.
        default_timeout: Таймаут выполнения инструмента в секундах.
    """

    def __init__(
        self,
        mcp_manager: MCPManager,
        default_timeout: float = 30.0,
    ) -> None:
        """Инициализировать executor.

        Args:
            mcp_manager: Менеджер MCP серверов сессии.
            default_timeout: Таймаут выполнения в секундах.
        """
        self._mcp_manager = mcp_manager
        self._default_timeout = default_timeout

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
        """Выполнить MCP инструмент.

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
            "executing MCP tool",
            session_id=session.session_id,
            tool_name=tool_name,
        )

        # Убираем tool_name из arguments перед передачей в MCP
        mcp_arguments = {k: v for k, v in arguments.items() if k != "tool_name"}

        try:
            result = await self._mcp_manager.call_tool(tool_name, mcp_arguments)

            # Если результат уже ToolExecutionResult — возвращаем напрямую
            if isinstance(result, ToolExecutionResult):
                return result

            # Конвертируем MCP content в текст
            if hasattr(result, "content") and result.content:
                output = self._convert_mcp_content_to_text(result.content)
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

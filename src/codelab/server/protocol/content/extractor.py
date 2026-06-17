"""Извлечение content из tool execution results."""

from dataclasses import dataclass
from typing import Any

import structlog

from codelab.server.tools.base import ToolExecutionResult

logger = structlog.get_logger(__name__)


@dataclass
class ExtractedContent:
    """Извлеченный content из tool result."""

    tool_call_id: str
    """ID tool call, к которому относится content."""

    content_items: list[dict[str, Any]]
    """Список content элементов (text, diff, image и т.д.)."""

    has_content: bool
    """Флаг наличия content."""


class ContentExtractor:
    """Извлекает content из ToolExecutionResult для отправки клиенту и LLM."""

    async def extract_from_result(
        self,
        tool_call_id: str,
        result: ToolExecutionResult
    ) -> ExtractedContent:
        """
        Извлечь content из tool execution result.

        Args:
            tool_call_id: ID tool call
            result: Результат выполнения tool

        Returns:
            ExtractedContent с content items
        """
        logger.debug(
            "extracting_content_from_result",
            tool_call_id=tool_call_id,
            has_content=bool(result.content)
        )

        # Если content пустой, создать fallback text content из output
        if not result.content:
            content_items = self._create_fallback_content(result)
        else:
            content_items = result.content

        return ExtractedContent(
            tool_call_id=tool_call_id,
            content_items=content_items,
            has_content=bool(result.content)
        )

    def _create_fallback_content(
        self,
        result: ToolExecutionResult
    ) -> list[dict[str, Any]]:
        """
        Создать fallback content из output для backward compatibility.

        Args:
            result: Tool execution result

        Returns:
            Список с одним text content элементом
        """
        # Для старых executors без content поддержки
        text_content = result.output or (result.error if not result.success else "")
        return [
            {
                "type": "text",
                "text": text_content
            }
        ]

    async def extract_batch(
        self,
        results: list[tuple[str, ToolExecutionResult]]
    ) -> list[ExtractedContent]:
        """
        Извлечь content из нескольких results.

        Args:
            results: Список (tool_call_id, result) пар

        Returns:
            Список ExtractedContent
        """
        extracted = []
        for tool_call_id, result in results:
            content = await self.extract_from_result(tool_call_id, result)
            extracted.append(content)

        logger.debug(
            "batch_extraction_complete",
            total=len(extracted),
            with_content=sum(1 for e in extracted if e.has_content)
        )

        return extracted

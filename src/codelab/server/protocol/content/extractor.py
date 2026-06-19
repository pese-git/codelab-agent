"""Извлечение content из tool execution results."""

from dataclasses import dataclass
from typing import Any

import structlog

from codelab.server.mapping.tool_result_mapper import ToolResultMapper
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
        content_items = ToolResultMapper.to_acp_content(result)
        if not content_items:
            content_items = self._create_fallback_content(result)

        logger.debug(
            "extracting_content_from_result",
            tool_call_id=tool_call_id,
            has_content=bool(content_items)
        )

        return ExtractedContent(
            tool_call_id=tool_call_id,
            content_items=content_items,
            has_content=bool(content_items)
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

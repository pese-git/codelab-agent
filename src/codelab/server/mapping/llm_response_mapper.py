"""Mapper между LLM-specific моделями и domain моделями."""

from __future__ import annotations

from codelab.server.domain.tool_call import ToolCall
from codelab.server.domain.value_objects import ToolCallStatus
from codelab.server.llm.models import LLMToolCall


class LLMResponseMapper:
    """Конвертер из LLM-specific моделей в domain модели."""

    @staticmethod
    def to_domain(llm_calls: list[LLMToolCall]) -> list[ToolCall]:
        """Конвертировать LLMToolCall в domain ToolCall."""
        return [
            ToolCall(
                id=call.id,
                tool_name=call.name,
                arguments=dict(call.arguments),
                status=ToolCallStatus.PENDING,
            )
            for call in llm_calls
        ]

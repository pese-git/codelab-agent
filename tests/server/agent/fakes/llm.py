"""FakeLLM — реализация порта `LLMPort` для тестов ядра (без сети/провайдера)."""

from __future__ import annotations

from typing import Any

from codelab.server.agent.contracts.events import AgentResult, TokenUsage
from codelab.server.llm.models import LLMMessage
from codelab.server.tools.base import ToolDefinition


class FakeLLM:
    """`LLMPort`, возвращающий заранее заданный `AgentResult` и запоминающий вход."""

    def __init__(self, result: AgentResult | None = None) -> None:
        self._result = result or AgentResult(
            text="ok", tool_calls=[], usage=TokenUsage(1, 1, 2), stop_reason="end_turn"
        )
        self.last_messages: list[LLMMessage] = []
        self.last_tools: list[ToolDefinition] = []
        self.calls = 0

    async def call(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
        config: dict[str, Any] | None = None,
        parent_span: Any = None,
        session_id: str = "",
    ) -> AgentResult:
        self.calls += 1
        self.last_messages = list(messages)
        self.last_tools = list(tools)
        return self._result

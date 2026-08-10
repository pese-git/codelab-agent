"""FakeToolGateway — реализация порта `ToolGateway` для тестов ядра."""

from __future__ import annotations

from typing import Any

from codelab.server.domain.value_objects import ToolInvocationSubject
from codelab.server.tools.base import ToolDefinition, ToolExecutionResult


class FakeToolGateway:
    """Минимальный `ToolGateway` без реестра/ACP."""

    def __init__(self, tools: list[ToolDefinition] | None = None) -> None:
        self._tools = tools or [
            ToolDefinition(
                name="fs/read_text_file", description="Read", parameters={}, kind="read"
            ),
            ToolDefinition(name="update_plan", description="Plan", parameters={}, kind="plan"),
        ]

    def get_available_tools(
        self, session_id: str, include_permission_required: bool = True
    ) -> list[ToolDefinition]:
        return list(self._tools)

    def to_llm_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {"name": t.name}} for t in tools]

    async def execute_tool(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        session: Any = None,
    subject: ToolInvocationSubject = ToolInvocationSubject.UNKNOWN,
    ) -> ToolExecutionResult:
        return ToolExecutionResult(success=True, output=f"{tool_name}:ok")

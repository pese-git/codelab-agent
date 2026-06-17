"""Тесты покрытия абстрактных методов ToolRegistry."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from codelab.server.tools.base import ToolDefinition, ToolExecutionResult, ToolRegistry


class ConcreteToolRegistry(ToolRegistry):
    """Конкретная реализация для покрытия абстрактных методов."""

    def register(
        self,
        tool: ToolDefinition,
        handler: Callable,
    ) -> None:
        super().register(tool, handler)

    def register_tool(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        kind: str,
        executor: Callable,
        requires_permission: bool = True,
    ) -> None:
        super().register_tool(
            name, description, parameters, kind, executor, requires_permission
        )

    def get_available_tools(
        self,
        session_id: str,
        include_permission_required: bool = True,
    ) -> list[ToolDefinition]:
        return super().get_available_tools(session_id, include_permission_required)

    def get(self, name: str) -> ToolDefinition | None:
        return super().get(name)

    def list_tools(self) -> list[ToolDefinition]:
        return super().list_tools()

    def to_llm_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        return super().to_llm_tools(tools)

    async def execute_tool(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        session: Any = None,
    ) -> ToolExecutionResult:
        return await super().execute_tool(session_id, tool_name, arguments, session)


class TestToolRegistryAbstractMethods:
    """Тесты вызова абстрактных методов базового ToolRegistry."""

    def test_register_pass_executed(self) -> None:
        """Абстрактный register возвращает None через pass."""
        registry = ConcreteToolRegistry()
        tool = ToolDefinition(
            name="test",
            description="desc",
            parameters={},
            kind="other",
        )
        result = registry.register(tool, lambda: None)
        assert result is None

    def test_register_tool_pass_executed(self) -> None:
        """Абстрактный register_tool возвращает None через pass."""
        registry = ConcreteToolRegistry()
        result = registry.register_tool("test", "desc", {}, "other", lambda: None)
        assert result is None

    def test_get_available_tools_pass_executed(self) -> None:
        """Абстрактный get_available_tools возвращает None через pass."""
        registry = ConcreteToolRegistry()
        result = registry.get_available_tools("session")
        assert result is None

    def test_get_pass_executed(self) -> None:
        """Абстрактный get возвращает None через pass."""
        registry = ConcreteToolRegistry()
        result = registry.get("test")
        assert result is None

    def test_list_tools_pass_executed(self) -> None:
        """Абстрактный list_tools возвращает None через pass."""
        registry = ConcreteToolRegistry()
        result = registry.list_tools()
        assert result is None

    def test_to_llm_tools_pass_executed(self) -> None:
        """Абстрактный to_llm_tools возвращает None через pass."""
        registry = ConcreteToolRegistry()
        result = registry.to_llm_tools([])
        assert result is None

    async def test_execute_tool_pass_executed(self) -> None:
        """Абстрактный execute_tool возвращает None через pass."""
        registry = ConcreteToolRegistry()
        result = await registry.execute_tool("session", "test", {})
        assert result is None

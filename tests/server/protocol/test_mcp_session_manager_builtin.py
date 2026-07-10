"""Тесты для MCPSessionManager с CommandRegistry.

Покрывают:
- Получение списка built-in команд из CommandRegistry
- Фильтрацию available_commands при очистке MCP prompts
- Fallback поведение при отсутствии CommandRegistry
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from codelab.server.models import AvailableCommand
from codelab.server.protocol.handlers.slash_commands import CommandRegistry
from codelab.server.protocol.mcp_session_manager import MCPSessionManager


@pytest.fixture
def mock_runtime_registry() -> AsyncMock:
    """Создаёт mock runtime registry."""
    return AsyncMock()


@pytest.fixture
def command_registry() -> CommandRegistry:
    """Создаёт CommandRegistry с тестовыми командами."""
    from codelab.server.protocol.handlers.slash_commands.base import (
        CommandHandler,
        CommandResult,
    )

    class TestHandler(CommandHandler):
        def __init__(self, name: str) -> None:
            self._name = name

        def execute(self, args: list[str], session) -> CommandResult:
            return CommandResult(content=[])

        def get_definition(self) -> AvailableCommand:
            return AvailableCommand(name=self._name, description=f"Test {self._name}")

    registry = CommandRegistry()
    registry.register(TestHandler("status"))
    registry.register(TestHandler("mode"))
    registry.register(TestHandler("help"))
    registry.register(TestHandler("strategy"))
    registry.register(TestHandler("context"))
    return registry


class TestGetBuiltinCommandNames:
    """Тесты для _get_builtin_command_names()."""

    def test_returns_commands_from_registry(
        self,
        mock_runtime_registry: AsyncMock,
        command_registry: CommandRegistry,
    ) -> None:
        """Возвращает команды из CommandRegistry."""
        manager = MCPSessionManager(
            runtime_registry=mock_runtime_registry,
            command_registry=command_registry,
        )

        builtin = manager._get_builtin_command_names()

        assert builtin == {"status", "mode", "help", "strategy", "context"}

    def test_returns_fallback_without_registry(
        self,
        mock_runtime_registry: AsyncMock,
    ) -> None:
        """Возвращает fallback набор при отсутствии CommandRegistry."""
        manager = MCPSessionManager(
            runtime_registry=mock_runtime_registry,
        )

        builtin = manager._get_builtin_command_names()

        assert builtin == {"status", "mode", "help", "strategy", "context"}

    def test_excludes_dynamic_commands(
        self,
        mock_runtime_registry: AsyncMock,
    ) -> None:
        """Исключает динамические команды (без handlers)."""
        registry = CommandRegistry()
        registry.add_dynamic_command(AvailableCommand(name="dynamic_cmd", description="Dynamic"))

        manager = MCPSessionManager(
            runtime_registry=mock_runtime_registry,
            command_registry=registry,
        )

        builtin = manager._get_builtin_command_names()

        assert "dynamic_cmd" not in builtin
        assert builtin == set()


class TestFilterAvailableCommands:
    """Тесты для фильтрации available_commands при очистке MCP prompts."""

    def test_filters_commands_by_builtin_names(
        self,
        mock_runtime_registry: AsyncMock,
        command_registry: CommandRegistry,
    ) -> None:
        """Фильтрует команды по списку built-in."""
        manager = MCPSessionManager(
            runtime_registry=mock_runtime_registry,
            command_registry=command_registry,
        )

        builtin_names = manager._get_builtin_command_names()

        # Симулируем список команд с MCP prompts
        commands = [
            {"name": "status", "description": "Status"},
            {"name": "mode", "description": "Mode"},
            {"name": "mcp_prompt_1", "description": "MCP Prompt"},
            {"name": "context", "description": "Context"},
            {"name": "mcp_prompt_2", "description": "Another MCP Prompt"},
        ]

        filtered = [cmd for cmd in commands if cmd["name"] in builtin_names]

        assert len(filtered) == 3
        assert all(cmd["name"] in {"status", "mode", "context"} for cmd in filtered)
        assert not any(cmd["name"].startswith("mcp_prompt") for cmd in filtered)

"""Дополнительные тесты покрытия для SlashCommandRouter.

Покрывает help-команду с execute_with_handlers, ошибки выполнения
встроенных команд, updates в _build_outcome и свойство registry.
"""

from __future__ import annotations

import pytest

from codelab.server.models import AvailableCommand
from codelab.server.protocol.handlers.slash_commands.base import CommandHandler, CommandResult
from codelab.server.protocol.handlers.slash_commands.registry import CommandRegistry
from codelab.server.protocol.handlers.slash_commands.router import SlashCommandRouter
from codelab.server.protocol.state import SessionState


class HelpWithHandlers(CommandHandler):
    """Handler команды help с execute_with_handlers."""

    def execute(self, args: list[str], session: SessionState) -> CommandResult:
        return CommandResult(content=[])

    def execute_with_handlers(
        self,
        args: list[str],
        session: SessionState,
        mcp_prompt_handlers: dict,
    ) -> CommandResult:
        return CommandResult(content=[{"type": "text", "text": "help result"}])

    def get_definition(self) -> AvailableCommand:
        return AvailableCommand(name="help", description="Show help")


class FailingHandler(CommandHandler):
    """Handler, который бросает исключение при выполнении."""

    def execute(self, args: list[str], session: SessionState) -> CommandResult:
        raise RuntimeError("boom")

    def get_definition(self) -> AvailableCommand:
        return AvailableCommand(name="fail", description="Fail")


class UpdateHandler(CommandHandler):
    """Handler, возвращающий дополнительные updates."""

    def execute(self, args: list[str], session: SessionState) -> CommandResult:
        return CommandResult(
            content=[{"type": "text", "text": "main"}],
            updates=[{"sessionUpdate": "mode_update", "modeId": "standard"}],
        )

    def get_definition(self) -> AvailableCommand:
        return AvailableCommand(name="update", description="Update")


@pytest.fixture
def session() -> SessionState:
    """Создает тестовую сессию."""
    return SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])


class TestSlashCommandRouterCoverage:
    """Тесты покрытия router."""

    async def test_route_help_uses_execute_with_handlers(self, session: SessionState) -> None:
        """Команда help передает mcp_prompt_handlers в execute_with_handlers."""
        registry = CommandRegistry()
        handler = HelpWithHandlers()
        registry.register(handler)
        router = SlashCommandRouter(registry)

        mcp_prompt_handlers = {"prompt": object()}
        outcome = await router.route("help", [], session, mcp_prompt_handlers)

        assert outcome is not None
        assert any(
            n.params.get("update", {}).get("content", {}).get("text") == "help result"
            for n in outcome.notifications
            if n.params is not None
        )

    async def test_route_builtin_exception_returns_error_outcome(
        self,
        session: SessionState,
    ) -> None:
        """Исключение во встроенном handler возвращает outcome с ошибкой."""
        registry = CommandRegistry()
        registry.register(FailingHandler())
        router = SlashCommandRouter(registry)

        outcome = await router.route("fail", [], session)

        assert outcome is not None
        assert any(
            "boom" in (n.params.get("update", {}).get("content", {}).get("text", ""))
            for n in outcome.notifications
            if n.params is not None
        )

    def test_build_outcome_with_updates(self, session: SessionState) -> None:
        """_build_outcome корректно добавляет update-уведомления."""
        registry = CommandRegistry()
        router = SlashCommandRouter(registry)

        result = CommandResult(
            content=[{"type": "text", "text": "hello"}],
            updates=[{"sessionUpdate": "mode_update", "modeId": "standard"}],
        )
        outcome = router._build_outcome(result, session)

        assert len(outcome.notifications) == 2
        updates = [n.params["update"] for n in outcome.notifications if n.params is not None]
        assert any(u.get("sessionUpdate") == "mode_update" for u in updates)
        assert any(u.get("sessionUpdate") == "agent_message_chunk" for u in updates)

    def test_registry_property(self) -> None:
        """Свойство registry возвращает исходный CommandRegistry."""
        registry = CommandRegistry()
        router = SlashCommandRouter(registry)

        assert router.registry is registry

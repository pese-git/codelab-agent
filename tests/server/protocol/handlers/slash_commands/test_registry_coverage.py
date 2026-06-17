"""Дополнительные тесты покрытия для CommandRegistry.

Покрывает unregister динамических команд, callback изменений
и свойство registered_commands.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from codelab.server.models import AvailableCommand, AvailableCommandInput
from codelab.server.protocol.handlers.slash_commands.base import CommandHandler, CommandResult
from codelab.server.protocol.handlers.slash_commands.registry import CommandRegistry


class DummyHandler(CommandHandler):
    """Тестовый handler с фиксированным определением."""

    def execute(self, args: list[str], session) -> CommandResult:
        return CommandResult(content=[])

    def get_definition(self) -> AvailableCommand:
        return AvailableCommand(name="dummy", description="Dummy command")


@pytest.fixture
def registry() -> CommandRegistry:
    """Создает пустой CommandRegistry."""
    return CommandRegistry()


class TestCommandRegistryCoverage:
    """Тесты покрытия недостающих веток."""

    def test_unregister_dynamic_command(self, registry: CommandRegistry) -> None:
        """Удаление динамической команды возвращает True."""
        registry.add_dynamic_command(AvailableCommand(name="dyn", description="Dynamic"))

        assert registry.unregister("dyn") is True
        assert registry.get_handler("dyn") is None
        assert "dyn" not in registry.registered_commands

    def test_set_on_change_callback(self, registry: CommandRegistry) -> None:
        """Callback устанавливается и вызывается при notify_change."""
        callback = MagicMock()
        registry.set_on_change_callback(callback)

        registry.notify_change("sess_1")

        callback.assert_called_once_with("sess_1")

    def test_notify_change_without_callback(self, registry: CommandRegistry) -> None:
        """Вызов notify_change без callback не вызывает ошибок."""
        registry.notify_change("sess_1")

    def test_registered_commands_includes_handlers_and_dynamic(
        self,
        registry: CommandRegistry,
    ) -> None:
        """registered_commands содержит и handlers, и dynamic команды."""
        registry.register(DummyHandler())
        registry.add_dynamic_command(AvailableCommand(name="dyn", description="Dynamic"))

        commands = registry.registered_commands
        assert "dummy" in commands
        assert "dyn" in commands

    def test_get_commands_as_dicts_with_input(self, registry: CommandRegistry) -> None:
        """Динамическая команда с input сериализуется в dict."""
        registry.add_dynamic_command(
            AvailableCommand(
                name="search",
                description="Search",
                input=AvailableCommandInput(hint="query"),
            )
        )

        dicts = registry.get_commands_as_dicts()

        assert len(dicts) == 1
        assert dicts[0]["name"] == "search"
        assert dicts[0]["input"] == {"hint": "query"}

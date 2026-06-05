"""Handler для команды /help.

Показывает список доступных команд или справку по конкретной команде.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codelab.server.models import AvailableCommand, AvailableCommandInput

from ..base import CommandHandler, CommandResult

if TYPE_CHECKING:
    from codelab.server.protocol.state import SessionState

    from ..registry import CommandRegistry


class HelpCommandHandler(CommandHandler):
    """Handler для команды /help.

    Без аргументов: показывает список всех доступных команд.
    С аргументом: показывает справку по конкретной команде.

    Пример использования:
        handler = HelpCommandHandler(registry)
        # Показать все команды
        result = handler.execute([], session)
        # Справка по конкретной команде
        result = handler.execute(["status"], session)
    """

    def __init__(self, registry: CommandRegistry) -> None:
        """Инициализирует handler с реестром команд.

        Args:
            registry: Реестр команд для получения списка
        """
        self._registry = registry

    def execute(
        self,
        args: list[str],
        session: SessionState,
    ) -> CommandResult:
        """Выполняет команду /help.

        Args:
            args: Пустой список для общей справки, или [command_name]
            session: Состояние сессии

        Returns:
            CommandResult со справочной информацией
        """
        # Если указана конкретная команда
        if args:
            command_name = args[0].lstrip("/")
            return self._help_for_command(command_name, session)

        # Общий список команд
        return self._help_all(session)

    def _get_all_commands(self, session: SessionState) -> list[AvailableCommand]:
        """Возвращает все команды: встроенные + MCP prompts.

        Args:
            session: Состояние сессии для получения MCP prompt handlers

        Returns:
            Список всех доступных команд
        """
        # Встроенные команды из registry
        commands = list(self._registry.get_commands())

        # MCP prompts из session
        for handler in session.mcp_prompt_handlers.values():
            commands.append(handler.get_definition())

        return commands

    def _help_all(self, session: SessionState) -> CommandResult:
        """Формирует справку по всем командам."""
        commands = self._get_all_commands(session)

        if not commands:
            return CommandResult(
                content=[{
                    "type": "text",
                    "text": "ℹ️ Нет доступных команд.",
                }]
            )

        lines = [
            "📖 **Доступные команды:**",
            "",
        ]

        for cmd in commands:
            hint = ""
            if cmd.input is not None:
                hint = f" `<{cmd.input.hint}>`"
            lines.append(f"**/{cmd.name}**{hint}")
            lines.append(f"  {cmd.description}")
            lines.append("")

        lines.append("Для справки по команде: `/help <команда>`")

        return CommandResult(
            content=[{"type": "text", "text": "\n".join(lines)}]
        )

    def _help_for_command(self, command_name: str, session: SessionState) -> CommandResult:
        """Формирует справку по конкретной команде."""
        commands = self._get_all_commands(session)
        cmd = next((c for c in commands if c.name == command_name), None)

        if cmd is None:
            return CommandResult(
                content=[{
                    "type": "text",
                    "text": f"❌ Команда `/{command_name}` не найдена.",
                }]
            )

        lines = [
            f"📖 **Справка: /{cmd.name}**",
            "",
            f"**Описание:** {cmd.description}",
        ]

        if cmd.input is not None:
            lines.append(f"**Ввод:** {cmd.input.hint}")
            lines.append("")
            lines.append(f"**Использование:** `/{cmd.name} <{cmd.input.hint}>`")
        else:
            lines.append("")
            lines.append(f"**Использование:** `/{cmd.name}`")

        return CommandResult(
            content=[{"type": "text", "text": "\n".join(lines)}]
        )

    def get_definition(self) -> AvailableCommand:
        """Возвращает определение команды /help."""
        return AvailableCommand(
            name="help",
            description="Показать список доступных команд",
            input=AvailableCommandInput(
                hint="имя команды для подробной справки"
            ),
        )

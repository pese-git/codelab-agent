"""Handler для команды /strategy.

Показывает или изменяет execution strategy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codelab.server.models import AvailableCommand, AvailableCommandInput

from ..base import CommandHandler, CommandResult

if TYPE_CHECKING:
    from codelab.server.agent.strategies.dispatcher import StrategyDispatcher
    from codelab.server.protocol.state import SessionState

# Доступные стратегии выполнения
AVAILABLE_STRATEGIES = ["single", "multi_orchestrated", "hierarchical"]


class StrategyCommandHandler(CommandHandler):
    """Handler для команды /strategy.

    Без аргументов: показывает текущую strategy.
    С аргументом: устанавливает новую strategy.

    Пример использования:
        handler = StrategyCommandHandler(strategy_dispatcher)
        # Показать текущую strategy
        result = handler.execute([], session)
        # Установить strategy
        result = handler.execute(["multi_orchestrated"], session)
    """

    def __init__(self, strategy_dispatcher: StrategyDispatcher) -> None:
        """Инициализация handler.

        Args:
            strategy_dispatcher: StrategyDispatcher для runtime override
        """
        self._strategy_dispatcher = strategy_dispatcher

    def execute(
        self,
        args: list[str],
        session: SessionState,
    ) -> CommandResult:
        """Выполняет команду /strategy.

        Args:
            args: Пустой список для показа strategy, или [strategy_name] для установки
            session: Состояние сессии (не используется, но требуется интерфейсом)

        Returns:
            CommandResult с информацией о strategy или подтверждением смены
        """
        current_strategy = self._strategy_dispatcher.get_strategy()

        # Если аргументов нет — показываем текущую strategy
        if not args:
            lines = [
                f"🎯 **Текущая strategy:** `{current_strategy}`",
                "",
                "**Доступные strategies:**",
            ]
            for strategy in AVAILABLE_STRATEGIES:
                marker = "→" if strategy == current_strategy else " "
                lines.append(f" {marker} `{strategy}`")

            lines.append("")
            lines.append("Для смены: `/strategy <имя>`")

            return CommandResult(
                content=[{"type": "text", "text": "\n".join(lines)}]
            )

        # Устанавливаем новую strategy
        new_strategy = args[0].lower()

        if new_strategy not in AVAILABLE_STRATEGIES:
            return CommandResult(
                content=[{
                    "type": "text",
                    "text": (
                        f"❌ Неизвестная strategy: `{new_strategy}`\n\n"
                        f"Доступные: {', '.join(f'`{s}`' for s in AVAILABLE_STRATEGIES)}"
                    ),
                }]
            )

        if new_strategy == current_strategy:
            return CommandResult(
                content=[{
                    "type": "text",
                    "text": f"ℹ️ Strategy `{current_strategy}` уже активна.",
                }]
            )

        # Устанавливаем новую strategy через dispatcher
        try:
            self._strategy_dispatcher.set_strategy(new_strategy)
        except ValueError as e:
            return CommandResult(
                content=[{"type": "text", "text": f"❌ {e}"}]
            )

        return CommandResult(
            content=[{
                "type": "text",
                "text": f"✅ Strategy изменена: `{current_strategy}` → `{new_strategy}`",
            }]
        )

    def get_definition(self) -> AvailableCommand:
        """Возвращает определение команды /strategy."""
        return AvailableCommand(
            name="strategy",
            description="Показать или изменить execution strategy",
            input=AvailableCommandInput(
                hint="имя strategy (single, multi_orchestrated, hierarchical)"
            ),
        )

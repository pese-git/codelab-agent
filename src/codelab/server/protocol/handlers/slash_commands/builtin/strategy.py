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


class StrategyCommandHandler(CommandHandler):
    """Handler для команды /strategy.

    Без аргументов: показывает текущую strategy.
    С аргументом: устанавливает новую strategy.

    Пример использования:
        handler = StrategyCommandHandler(strategy_dispatcher)
        # Показать текущую strategy
        result = handler.execute([], session)
        # Установить strategy
        result = handler.execute(["hierarchical"], session)
    """

    def __init__(self, strategy_dispatcher: StrategyDispatcher) -> None:
        """Инициализация handler.

        Args:
            strategy_dispatcher: StrategyDispatcher для выбора и установки strategy
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
            session: Состояние сессии для установки config_values

        Returns:
            CommandResult с информацией о strategy или подтверждением смены
        """
        current_strategy = self._strategy_dispatcher.get_strategy()
        available_strategies = self._strategy_dispatcher.get_available_strategies()

        # Если аргументов нет — показываем текущую strategy
        if not args:
            lines = [
                f"🎯 **Текущая strategy:** `{current_strategy}`",
                "",
                "**Доступные strategies:**",
            ]
            for strategy in available_strategies:
                marker = "→" if strategy == current_strategy else " "
                lines.append(f" {marker} `{strategy}`")

            lines.append("")
            lines.append("Для смены: `/strategy <имя>`")

            return CommandResult(
                content=[{"type": "text", "text": "\n".join(lines)}]
            )

        # Устанавливаем новую strategy
        new_strategy = args[0].lower()

        # Проверить доступность через dispatcher
        if new_strategy not in available_strategies:
            return CommandResult(
                content=[{
                    "type": "text",
                    "text": (
                        f"❌ Strategy `{new_strategy}` недоступна.\n\n"
                        f"Доступные: {', '.join(f'`{s}`' for s in available_strategies)}"
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
        if not self._strategy_dispatcher.set_current_strategy(new_strategy):
            return CommandResult(
                content=[{
                    "type": "text",
                    "text": f"❌ Не удалось установить strategy `{new_strategy}`",
                }]
            )

        # Сохраняем в session.config_values для persistence между turn'ами
        session.config_values["_active_strategy"] = new_strategy

        return CommandResult(
            content=[{
                "type": "text",
                "text": f"✅ Strategy изменена: `{current_strategy}` → `{new_strategy}`",
            }]
        )

    def get_definition(self) -> AvailableCommand:
        """Возвращает определение команды /strategy."""
        # Получаем доступные стратегии для hint
        available = self._strategy_dispatcher.get_available_strategies()
        hint = f"имя strategy ({', '.join(available)})"
        
        return AvailableCommand(
            name="strategy",
            description="Показать или изменить execution strategy",
            input=AvailableCommandInput(hint=hint),
        )

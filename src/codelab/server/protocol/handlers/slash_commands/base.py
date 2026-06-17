"""Базовые классы для slash commands.

Определяет интерфейс CommandHandler и результат выполнения CommandResult.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codelab.server.models import AvailableCommand
    from codelab.server.protocol.state import SessionState


@dataclass
class CommandResult:
    """Результат выполнения slash-команды.

    Содержит контент для отправки клиенту и опциональные
    дополнительные session/update уведомления.

    Пример использования:
        result = CommandResult(
            content=[{"type": "text", "text": "Status: OK"}],
            stop_reason="end_turn"
        )
    """

    content: list[dict[str, Any]]
    """Контент для отправки в session/update с role='assistant'."""

    updates: list[dict[str, Any]] = field(default_factory=list)
    """Дополнительные session/update уведомления (например, mode_update)."""

    stop_reason: str = "end_turn"
    """Причина завершения turn. По умолчанию 'end_turn'."""


class CommandHandler(ABC):
    """Базовый класс для обработчиков slash-команд.

    Каждый обработчик реализует логику выполнения конкретной команды
    и предоставляет её определение для регистрации.

    Пример реализации:
        class StatusCommandHandler(CommandHandler):
            def execute(self, args, session):
                return CommandResult(
                    content=[{"type": "text", "text": f"Session: {session.session_id}"}]
                )

            def get_definition(self):
                return AvailableCommand(name="status", description="Show status")
    """

    @abstractmethod
    def execute(
        self,
        args: list[str],
        session: SessionState,
    ) -> CommandResult:
        """Выполняет команду.

        Args:
            args: Аргументы команды после имени (например, для "/mode code" args=["code"])
            session: Текущее состояние сессии

        Returns:
            CommandResult с контентом для отправки клиенту
        """
        ...

    @abstractmethod
    def get_definition(self) -> AvailableCommand:
        """Возвращает определение команды для регистрации.

        Returns:
            AvailableCommand с name, description и опциональным input
        """
        ...

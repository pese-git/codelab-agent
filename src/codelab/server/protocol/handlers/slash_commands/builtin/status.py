"""Handler для команды /status.

Показывает состояние текущей сессии.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codelab.server.models import AvailableCommand

from ..base import CommandHandler, CommandResult

if TYPE_CHECKING:
    from codelab.server.protocol.state import SessionState


class StatusCommandHandler(CommandHandler):
    """Handler для команды /status.

    Возвращает информацию о текущей сессии:
    - ID сессии
    - Заголовок
    - Время последнего изменения
    - Количество сообщений в истории
    - Активные tool calls

    Пример использования:
        handler = StatusCommandHandler()
        result = handler.execute([], session)
    """

    def execute(
        self,
        args: list[str],
        session: SessionState,
    ) -> CommandResult:
        """Выполняет команду /status.

        Args:
            args: Аргументы (игнорируются)
            session: Состояние сессии

        Returns:
            CommandResult с информацией о сессии
        """
        # Формируем текстовый отчёт о состоянии сессии
        lines = [
            "📊 **Состояние сессии**",
            "",
            f"**ID:** `{session.session_id}`",
        ]

        if session.title:
            lines.append(f"**Заголовок:** {session.title}")

        lines.append(f"**Обновлено:** {session.updated_at}")
        lines.append(f"**Сообщений в истории:** {len(session.history)}")

        # Информация о tool calls
        active_calls = [
            tc for tc in session.tool_calls.values()
            if tc.status in ("pending", "in_progress")
        ]
        if active_calls:
            lines.append(f"**Активных tool calls:** {len(active_calls)}")

        # Информация о config values
        if session.config_values:
            config_str = ", ".join(
                f"{k}={v}" for k, v in session.config_values.items()
            )
            lines.append(f"**Конфигурация:** {config_str}")

        # Информация о permission policy
        if session.permission_policy:
            policy_str = ", ".join(
                f"{k}={v}" for k, v in session.permission_policy.items()
            )
            lines.append(f"**Permission policy:** {policy_str}")

        content = [{"type": "text", "text": "\n".join(lines)}]

        return CommandResult(content=content)

    def get_definition(self) -> AvailableCommand:
        """Возвращает определение команды /status."""
        return AvailableCommand(
            name="status",
            description="Показать состояние текущей сессии",
        )

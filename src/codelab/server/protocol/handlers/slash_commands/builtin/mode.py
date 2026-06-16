"""Handler для команды /mode.

Показывает или изменяет режим сессии (ACP Protocol mode).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codelab.server.models import AvailableCommand, AvailableCommandInput
from codelab.server.protocol.mode import (
    DEFAULT_MODE,
    MODE_DESCRIPTIONS,
    VALID_MODES,
    normalize_mode,
)

from ..base import CommandHandler, CommandResult

if TYPE_CHECKING:
    from codelab.server.protocol.state import SessionState


class ModeCommandHandler(CommandHandler):
    """Handler для команды /mode.

    Без аргументов: показывает текущий режим.
    С аргументом: устанавливает новый режим.

    Доступные режимы: plan, standard, bypass
    """

    def execute(
        self,
        args: list[str],
        session: SessionState,
    ) -> CommandResult:
        """Выполняет команду /mode.

        Args:
            args: Пустой список для показа режима, или [mode_name] для установки
            session: Состояние сессии

        Returns:
            CommandResult с информацией о режиме или подтверждением смены
        """
        current_mode = session.config_values.get("mode", DEFAULT_MODE)

        # Если аргументов нет — показываем текущий режим
        if not args:
            lines = [
                f"🎯 **Текущий режим:** `{current_mode}`",
                "",
                "**Доступные режимы:**",
            ]
            for mode_id in sorted(VALID_MODES):
                info = MODE_DESCRIPTIONS.get(mode_id, {})
                marker = "→" if mode_id == current_mode else " "
                lines.append(f" {marker} `{mode_id}` — {info.get('name', mode_id)}")

            lines.append("")
            lines.append("Для смены режима: `/mode <имя_режима>`")

            return CommandResult(
                content=[{"type": "text", "text": "\n".join(lines)}]
            )

        # Устанавливаем новый режим
        new_mode = args[0].lower()
        normalized = normalize_mode(new_mode)

        if new_mode not in VALID_MODES and new_mode not in ("ask", "code", "architect", "debug"):
            valid_list = ", ".join(f"`{m}`" for m in sorted(VALID_MODES))
            return CommandResult(
                content=[{
                    "type": "text",
                    "text": (
                        f"❌ Неизвестный режим: `{new_mode}`\n\n"
                        f"Доступные режимы: {valid_list}"
                    ),
                }]
            )

        if normalized == current_mode:
            return CommandResult(
                content=[{
                    "type": "text",
                    "text": f"ℹ️ Режим `{current_mode}` уже активен.",
                }]
            )

        # Устанавливаем новый режим в config_values
        session.config_values["mode"] = normalized

        # Формируем update для клиента
        mode_update = {
            "sessionUpdate": "current_mode_update",
            "mode": normalized,
        }

        msg = f"✅ Режим изменён: `{current_mode}` → `{normalized}`"
        if normalized != new_mode:
            msg += f" (нормализовано из `{new_mode}`)"

        return CommandResult(
            content=[{
                "type": "text",
                "text": msg,
            }],
            updates=[mode_update],
        )

    def get_definition(self) -> AvailableCommand:
        """Возвращает определение команды /mode."""
        return AvailableCommand(
            name="mode",
            description="Показать или изменить режим сессии",
            input=AvailableCommandInput(
                hint="режим (plan, standard, bypass)"
            ),
        )

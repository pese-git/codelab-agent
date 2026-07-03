"""SessionInfoHandler - обработчик информационных обновлений сессии.

Обрабатывает типы обновлений:
- available_commands_update: обновление списка доступных команд
- session_info_update: обновление информации о сессии (title, updatedAt)

Эти обновления носят информационный характер и не требуют изменения
состояния чата. Handler просто логирует их для отладки.
"""

from __future__ import annotations

from typing import Any

from codelab.client.presentation.chat.context import ChatUpdateContext


class SessionInfoHandler:
    """Обработчик информационных обновлений сессии.

    Обрабатывает обновления которые не влияют на состояние чата,
    но могут быть полезны для логирования и отладки.
    """

    def can_handle(self, update_type: str) -> bool:
        """Проверяет, может ли handler обработать этот тип update.

        Args:
            update_type: Тип обновления из update.sessionUpdate

        Returns:
            True если update_type это available_commands_update или session_info_update
        """
        return update_type in ("available_commands_update", "session_info_update")

    def handle(self, update_data: dict[str, Any], context: ChatUpdateContext) -> None:
        """Обрабатывает информационное update.

        Args:
            update_data: Полные данные обновления от сервера
            context: Контекст с состоянием и сервисами
        """
        update = update_data.get("params", {}).get("update", {})
        update_type = update.get("sessionUpdate")

        context.logger.debug(
            "session_info_update_received",
            session_id=context.session_id,
            update_type=update_type,
        )

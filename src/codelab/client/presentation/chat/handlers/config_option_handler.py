"""ConfigOptionHandler - обработчик обновлений конфигурации.

Обрабатывает тип обновления:
- config_option_update: обновление опций конфигурации сессии
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from codelab.client.presentation.chat.context import ChatUpdateContext


class ConfigOptionHandler:
    """Обработчик обновлений конфигурации сессии.

    Публикует событие ConfigOptionUpdatedEvent в EventBus
    для уведомления других компонентов (например, ModelSelectorViewModel).
    """

    def can_handle(self, update_type: str) -> bool:
        """Проверяет, может ли handler обработать этот тип update.

        Args:
            update_type: Тип обновления из update.sessionUpdate

        Returns:
            True если update_type это config_option_update
        """
        return update_type == "config_option_update"

    def handle(self, update_data: dict[str, Any], context: ChatUpdateContext) -> None:
        """Обрабатывает update конфигурации.

        Args:
            update_data: Полные данные обновления от сервера
            context: Контекст с состоянием и сервисами
        """
        update = update_data.get("params", {}).get("update", {})
        config_options = update.get("configOptions", [])

        context.logger.info(
            "config_option_update_received",
            session_id=context.session_id,
            config_options_count=len(config_options),
        )

        if not config_options:
            context.logger.debug(
                "config_option_update_empty",
                session_id=context.session_id,
            )
            return

        if context.event_bus is None:
            context.logger.debug(
                "event_bus_not_available",
                session_id=context.session_id,
            )
            return

        # Импортируем событие здесь чтобы избежать циклических зависимостей
        try:
            from codelab.client.domain.events import ConfigOptionUpdatedEvent

            event = ConfigOptionUpdatedEvent(
                aggregate_id=context.session_id,
                occurred_at=datetime.now(),
                session_id=context.session_id,
                config_options=config_options,
            )

            # EventBus.publish может быть async, поэтому используем ensure_future
            import asyncio

            asyncio.ensure_future(context.event_bus.publish(event))

            context.logger.info(
                "config_option_event_published",
                session_id=context.session_id,
                config_options_count=len(config_options),
            )

        except ImportError:
            context.logger.debug(
                "config_option_updated_event_not_available",
                session_id=context.session_id,
            )

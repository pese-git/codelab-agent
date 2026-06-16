"""Менеджер сохранения и воспроизведения session/update уведомлений.

Централизует логику:
- Сохранение всех типов session/update в events_history
- Воспроизведение истории при session/load
- Фильтрация и сортировка событий для replay

Согласно спецификации ACP (protocol/03-Session Setup.md):
"The Agent MUST replay the entire conversation to the Client
in the form of session/update notifications"
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from ...messages import ACPMessage
from ..state import SessionState

# Используем structlog для структурированного логирования
logger = structlog.get_logger()


class ReplayManager:
    """Управляет сохранением и воспроизведением session/update уведомлений.

    Ответственность:
    - Сохранение всех типов updates в events_history
    - Воспроизведение полной истории при session/load
    - Обеспечение порядка и полноты replay

    Поддерживаемые типы updates (согласно ACP protocol):
    - user_message_chunk: сообщения пользователя
    - agent_message_chunk: ответы агента
    - tool_call: создание tool call
    - tool_call_update: обновление статуса tool call
    - plan: обновление плана агента
    - session_info: метаданные сессии
    - config_option_update: изменение конфигурации
    - current_mode_update: смена режима
    - available_commands_update: обновление доступных команд

    Пример использования:
        >>> manager = ReplayManager()
        >>> manager.save_user_message_chunk(session, content_block)
        >>> manager.save_agent_message_chunk(session, text_content)
        >>> manager.save_tool_call(session, tool_call_id, title, kind, status)
        >>> notifications = manager.replay_history(session)
    """

    # Типы updates, которые должны реплеиться в порядке их возникновения
    _REPLAYABLE_UPDATE_TYPES: frozenset[str] = frozenset({
        "user_message_chunk",
        "agent_message_chunk",
        "tool_call",
        "tool_call_update",
        "plan",
        "session_info",
    })

    def save_user_message_chunk(
        self,
        session: SessionState,
        content: dict[str, Any],
    ) -> None:
        """Сохраняет user_message_chunk в events_history.

        Args:
            session: Состояние сессии
            content: Content block (например, {"type": "text", "text": "..."})
        """
        self._save_update(
            session,
            {
                "sessionUpdate": "user_message_chunk",
                "content": content,
            },
        )

    def save_agent_message_chunk(
        self,
        session: SessionState,
        content: dict[str, Any],
    ) -> None:
        """Сохраняет agent_message_chunk в events_history.

        Args:
            session: Состояние сессии
            content: Content block (например, {"type": "text", "text": "..."})
        """
        self._save_update(
            session,
            {
                "sessionUpdate": "agent_message_chunk",
                "content": content,
            },
        )

    def save_tool_call(
        self,
        session: SessionState,
        tool_call_id: str,
        title: str,
        kind: str,
        status: str,
        *,
        content: list[dict[str, Any]] | None = None,
    ) -> None:
        """Сохраняет tool_call в events_history.

        Args:
            session: Состояние сессии
            tool_call_id: ID tool call
            title: Заголовок для UI
            kind: Категория tool (read, edit, execute, etc.)
            status: Начальный статус (обычно "pending")
            content: Опциональный контент tool call
        """
        update: dict[str, Any] = {
            "sessionUpdate": "tool_call",
            "toolCallId": tool_call_id,
            "title": title,
            "kind": kind,
            "status": status,
        }
        if content:
            update["content"] = content
        self._save_update(session, update)

    def save_tool_call_update(
        self,
        session: SessionState,
        tool_call_id: str,
        status: str,
        *,
        content: list[dict[str, Any]] | None = None,
    ) -> None:
        """Сохраняет tool_call_update в events_history.

        Args:
            session: Состояние сессии
            tool_call_id: ID tool call
            status: Новый статус (in_progress, completed, failed, cancelled)
            content: Опциональный контент результата
        """
        update: dict[str, Any] = {
            "sessionUpdate": "tool_call_update",
            "toolCallId": tool_call_id,
            "status": status,
        }
        if content:
            update["content"] = content
        self._save_update(session, update)

    def save_plan(
        self,
        session: SessionState,
        entries: list[dict[str, Any]],
    ) -> None:
        """Сохраняет plan update в events_history.

        Args:
            session: Состояние сессии
            entries: Список шагов плана
        """
        self._save_update(
            session,
            {
                "sessionUpdate": "plan",
                "entries": entries,
            },
        )

    def save_session_info(
        self,
        session: SessionState,
        title: str | None,
        updated_at: str | None,
    ) -> None:
        """Сохраняет session_info update в events_history.

        Args:
            session: Состояние сессии
            title: Заголовок сессии
            updated_at: Время последнего обновления
        """
        self._save_update(
            session,
            {
                "sessionUpdate": "session_info",
                "title": title,
                "updated_at": updated_at,
            },
        )

    def save_config_option_update(
        self,
        session: SessionState,
        config_options: list[dict[str, Any]],
    ) -> None:
        """Сохраняет config_option_update в events_history.

        Args:
            session: Состояние сессии
            config_options: Список опций конфигурации
        """
        self._save_update(
            session,
            {
                "sessionUpdate": "config_option_update",
                "configOptions": config_options,
            },
        )

    def save_current_mode_update(
        self,
        session: SessionState,
        mode_id: str,
    ) -> None:
        """Сохраняет current_mode_update в events_history.

        Args:
            session: Состояние сессии
            mode_id: ID нового режима
        """
        self._save_update(
            session,
            {
                "sessionUpdate": "current_mode_update",
                "modeId": mode_id,
            },
        )

    def save_available_commands_update(
        self,
        session: SessionState,
        available_commands: list[dict[str, Any]],
    ) -> None:
        """Сохраняет available_commands_update в events_history.

        Args:
            session: Состояние сессии
            available_commands: Список доступных команд
        """
        self._save_update(
            session,
            {
                "sessionUpdate": "available_commands_update",
                "availableCommands": available_commands,
            },
        )

    def replay_history(
        self,
        session: SessionState,
    ) -> list[ACPMessage]:
        """Воспроизводит полную историю session/update уведомлений.

        Согласно спецификации ACP (protocol/03-Session Setup.md):
        "The Agent MUST replay the entire conversation to the Client
        in the form of session/update notifications"

        Порядок replay:
        1. Все события из events_history в хронологическом порядке
        2. События фильтруются по _REPLAYABLE_UPDATE_TYPES

        Args:
            session: Состояние сессии

        Returns:
            Список ACPMessage notifications для отправки клиенту
        """
        notifications: list[ACPMessage] = []
        session_id = session.session_id

        # Replay из events_history - восстанавливаем полную историю
        for event in session.events_history:
            event_type = event.get("type")

            if event_type == "session_update":
                update_data = event.get("update", {})
                if not update_data:
                    continue

                # Проверяем что это replayable update type
                session_update_type = update_data.get("sessionUpdate")
                if session_update_type in self._REPLAYABLE_UPDATE_TYPES:
                    notifications.append(
                        ACPMessage.notification(
                            "session/update",
                            {"sessionId": session_id, "update": update_data},
                        )
                    )

        logger.debug(
            "replay_history completed",
            session_id=session_id,
            events_count=len(session.events_history),
            notifications_count=len(notifications),
        )

        return notifications

    def replay_latest_plan(
        self,
        session: SessionState,
    ) -> ACPMessage | None:
        """Воспроизводит последний план если он есть.

        Отдельный метод для плана, так как latest_plan хранится
        отдельно от events_history для быстрого доступа.

        Args:
            session: Состояние сессии

        Returns:
            ACPMessage с plan update или None если плана нет
        """
        if not session.latest_plan:
            return None

        return ACPMessage.notification(
            "session/update",
            {
                "sessionId": session.session_id,
                "update": {
                    "sessionUpdate": "plan",
                    "entries": session.latest_plan,
                },
            },
        )

    def _save_update(
        self,
        session: SessionState,
        update: dict[str, Any],
    ) -> None:
        """Сохраняет session/update в events_history.

        Добавляет временную метку к каждому событию.

        Args:
            session: Состояние сессии
            update: Данные update (sessionUpdate, ...)
        """
        event_entry = {
            "type": "session_update",
            "update": update,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        session.events_history.append(event_entry)

        logger.debug(
            "update saved to events_history",
            session_id=session.session_id,
            update_type=update.get("sessionUpdate"),
        )

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

from codelab.server.mapping.plan_mapper import PlanMapper

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
    _REPLAYABLE_UPDATE_TYPES: frozenset[str] = frozenset(
        {
            "user_message_chunk",
            "agent_message_chunk",
            "tool_call",
            "tool_call_update",
            "plan",
            "session_info",
        }
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

        # `latest_plan` шире ACP-формы (PlanStep | dict, а после переключения резидента —
        # доменные PlanEntry). Приведение — единственным швом Plan↔ACP: без него
        # ACPMessage.to_json падал с "PlanStep is not JSON serializable", а pre-P2-26
        # записи уходили клиенту без обязательных по ACP полей.
        entries = PlanMapper.entries_to_acp(list(session.latest_plan))

        return ACPMessage.notification(
            "session/update",
            {
                "sessionId": session.session_id,
                "update": {
                    "sessionUpdate": "plan",
                    "entries": entries,
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

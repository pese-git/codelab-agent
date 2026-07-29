"""Воспроизведение накопленной истории при `session/load` (read-половина).

Согласно спецификации ACP (protocol/03-Session Setup.md):
"The Agent MUST replay the entire conversation to the Client
in the form of session/update notifications"

Read-половина расщеплённого `ReplayManager` (фаза C ADR-006): вызывается только
из `session/load`, тогда как write-половина (`EventHistoryWriter`) обслуживает
prompt-turn и resume. Наборы вызывающих не пересекались и до расщепления.
"""

from __future__ import annotations

import structlog

from codelab.server.mapping.plan_mapper import PlanMapper

from ...messages import ACPMessage
from ..state import SessionState

logger = structlog.get_logger()


class SessionReplayer:
    """Воспроизводит историю сессии как `session/update` уведомления.

    Пример использования:
        >>> replayer = SessionReplayer()
        >>> notifications = replayer.replay_history(session)
        >>> plan_notification = replayer.replay_latest_plan(session)
    """

    # Типы updates, которые реплеятся в порядке их возникновения.
    #
    # `session_info_update` в набор НЕ входит намеренно: исторические метаданные
    # устарели уже к моменту загрузки, а `session/load` в конце реплея сам
    # эмитит свежий `session_info_update`. Отсюда постоянная разница между
    # `events_history` и `history_notifications` в логе `session_loaded` —
    # это ожидаемое поведение, а не потеря событий.
    #
    # Мёртвое значение `session_info` (в таком виде не пишет никто; единственным
    # писателем был удалённый в фазе A `ReplayManager.save_session_info`) снято.
    _REPLAYABLE_UPDATE_TYPES: frozenset[str] = frozenset(
        {
            "user_message_chunk",
            "agent_message_chunk",
            "tool_call",
            "tool_call_update",
            "plan",
        }
    )

    def replay_history(
        self,
        session: SessionState,
    ) -> list[ACPMessage]:
        """Воспроизводит полную историю session/update уведомлений.

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
            if event.get("type") != "session_update":
                continue

            update_data = event.get("update", {})
            if not update_data:
                continue

            if update_data.get("sessionUpdate") in self._REPLAYABLE_UPDATE_TYPES:
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

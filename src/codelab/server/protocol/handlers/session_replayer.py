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

from codelab.server.domain.session import Session as DomainSession
from codelab.server.mapping.journal_mapper import JournalMapper
from codelab.server.mapping.plan_mapper import PlanMapper

from ...messages import ACPMessage

logger = structlog.get_logger()


class SessionReplayer:
    """Воспроизводит историю сессии как `session/update` уведомления.

    Пример использования:
        >>> replayer = SessionReplayer()
        >>> notifications = replayer.replay_history(session)
        >>> plan_notification = replayer.replay_latest_plan(session)
    """

    def replay_history(
        self,
        session: DomainSession,
    ) -> list[ACPMessage]:
        """Воспроизводит полную историю session/update уведомлений.

        Порядок replay:
        1. Записи журнала разбираются в доменные события в хронологическом порядке
        2. В поток попадают те, у которых есть реплей-проекция

        Прежний фильтр по набору строк `_REPLAYABLE_UPDATE_TYPES` снят: какие
        события реплеятся, теперь решает наличие реплей-формы у события
        (`JournalMapper.to_replay_updates`) — то есть модель, а не список имён в
        читателе. Единственное событие без такой формы — `SessionInfoRecorded`:
        исторические метаданные устарели уже к моменту загрузки, а `session/load`
        в конце реплея сам эмитит свежий `session_info_update`. Отсюда постоянная
        разница между `events_history` и `history_notifications` в логе
        `session_loaded` — ожидаемое поведение, а не потеря событий.

        Args:
            session: Состояние сессии

        Returns:
            Список ACPMessage notifications для отправки клиенту
        """
        notifications: list[ACPMessage] = []
        session_id = str(session.id)

        for entry in session.journal.entries():
            # Событие описывает сообщение, а ACP передаёт его чанками, поэтому
            # проекция отдаёт список: многоблочный промпт — по чанку на блок.
            for update_data in JournalMapper.to_replay_updates(entry.event):
                notifications.append(
                    ACPMessage.notification(
                        "session/update",
                        {"sessionId": session_id, "update": update_data},
                    )
                )

        logger.debug(
            "replay_history completed",
            session_id=session_id,
            events_count=len(session.journal),
            notifications_count=len(notifications),
        )

        return notifications

    def replay_latest_plan(
        self,
        session: DomainSession,
    ) -> ACPMessage | None:
        """Воспроизводит последний план если он есть.

        Отдельный метод для плана, так как latest_plan хранится
        отдельно от events_history для быстрого доступа.

        Args:
            session: Состояние сессии

        Returns:
            ACPMessage с plan update или None если плана нет
        """
        if not session.plan.get_steps():
            return None

        # Приведение — единственным швом Plan↔ACP: без него ACPMessage.to_json падал
        # с "PlanStep is not JSON serializable", а pre-P2-26 записи уходили клиенту
        # без обязательных по ACP полей.
        entries = PlanMapper.to_acp(session.plan.get_steps())

        return ACPMessage.notification(
            "session/update",
            {
                "sessionId": str(session.id),
                "update": {
                    "sessionUpdate": "plan",
                    "entries": entries,
                },
            },
        )

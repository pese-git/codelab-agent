"""Тесты для SessionReplayer (read-половина, фаза C ADR-006).

Проверяет воспроизведение накопленной истории на `session/load` согласно
спецификации ACP (protocol/03-Session Setup.md). Историю сеет
`EventHistoryWriter` — тот же писатель, что и в проде.
"""

from __future__ import annotations

import pytest

from codelab.server.domain.session import AgentPlan
from codelab.server.domain.session import Session as DomainSession
from codelab.server.mapping.plan_mapper import PlanMapper
from codelab.server.protocol.handlers.event_history_writer import EventHistoryWriter
from codelab.server.protocol.handlers.session_replayer import SessionReplayer
from tests.server._domain_sessions import make_domain_session


@pytest.fixture
def session() -> DomainSession:
    """Создает тестовую сессию (доменный агрегат — носитель реплея, ADR-006 D5)."""
    return make_domain_session(
        session_id="sess_test_001",
        cwd="/tmp/test",
        mcp_servers=[],
    )


@pytest.fixture
def history_writer() -> EventHistoryWriter:
    """Писатель истории: сеет события так же, как прод-путь turn'а."""
    return EventHistoryWriter()


@pytest.fixture
def replayer() -> SessionReplayer:
    """Создает экземпляр SessionReplayer."""
    return SessionReplayer()


class TestReplayHistory:
    """Тесты для replay_history."""

    def test_replays_empty_history(
        self,
        replayer: SessionReplayer,
        history_writer: EventHistoryWriter,
        session: DomainSession,
    ) -> None:
        """Проверяет replay пустой истории."""
        notifications = replayer.replay_history(session)

        assert notifications == []

    def test_replays_user_and_agent_messages(
        self,
        replayer: SessionReplayer,
        history_writer: EventHistoryWriter,
        session: DomainSession,
    ) -> None:
        """Проверяет replay сообщений пользователя и агента."""
        # Сохраняем историю
        history_writer.save_user_message_chunk(session, {"type": "text", "text": "User question"})
        history_writer.save_agent_message_chunk(session, {"type": "text", "text": "Agent answer"})

        # Воспроизводим
        notifications = replayer.replay_history(session)

        assert len(notifications) == 2

        # Проверяем user_message_chunk
        assert notifications[0].method == "session/update"
        assert notifications[0].params["sessionId"] == "sess_test_001"
        assert notifications[0].params["update"]["sessionUpdate"] == "user_message_chunk"

        # Проверяем agent_message_chunk
        assert notifications[1].params["update"]["sessionUpdate"] == "agent_message_chunk"

    def test_replays_tool_call_lifecycle(
        self,
        replayer: SessionReplayer,
        history_writer: EventHistoryWriter,
        session: DomainSession,
    ) -> None:
        """Проверяет replay полного жизненного цикла tool call."""
        # Сохраняем события tool call
        history_writer.save_tool_call(
            session=session,
            tool_call_id="call_001",
            title="fs/read_text_file",
            kind="read",
            status="pending",
        )
        history_writer.save_tool_call_update(
            session=session,
            tool_call_id="call_001",
            status="in_progress",
        )
        history_writer.save_tool_call_update(
            session=session,
            tool_call_id="call_001",
            status="completed",
            content=[{"type": "text", "text": "File content"}],
        )

        # Воспроизводим
        notifications = replayer.replay_history(session)

        assert len(notifications) == 3
        assert notifications[0].params["update"]["sessionUpdate"] == "tool_call"
        assert notifications[1].params["update"]["sessionUpdate"] == "tool_call_update"
        assert notifications[1].params["update"]["status"] == "in_progress"
        assert notifications[2].params["update"]["sessionUpdate"] == "tool_call_update"
        assert notifications[2].params["update"]["status"] == "completed"

    def test_replays_full_conversation(
        self,
        replayer: SessionReplayer,
        history_writer: EventHistoryWriter,
        session: DomainSession,
    ) -> None:
        """Проверяет replay полной беседы с tool calls."""
        # Симулируем полную беседу
        history_writer.save_user_message_chunk(session, {"type": "text", "text": "Read file.txt"})
        history_writer.save_tool_call(
            session=session,
            tool_call_id="call_001",
            title="fs/read_text_file",
            kind="read",
            status="pending",
        )
        history_writer.save_tool_call_update(
            session=session,
            tool_call_id="call_001",
            status="completed",
        )
        history_writer.save_agent_message_chunk(
            session, {"type": "text", "text": "Here is the file content..."}
        )
        history_writer.save_session_info_update(
            session, title="Read file.txt", updated_at="2024-01-01T00:00:00Z"
        )

        # Воспроизводим
        notifications = replayer.replay_history(session)

        # session_info_update не реплеится: метаданные устарели, а session/load
        # эмитит свежий в конце реплея (фаза C ADR-006).
        assert len(notifications) == 4

        # Проверяем порядок
        update_types = [n.params["update"]["sessionUpdate"] for n in notifications]
        assert update_types == [
            "user_message_chunk",
            "tool_call",
            "tool_call_update",
            "agent_message_chunk",
        ]

    def test_filters_non_replayable_events(
        self,
        replayer: SessionReplayer,
        history_writer: EventHistoryWriter,
        session: DomainSession,
    ) -> None:
        """Проверяет что запись без реплей-формы в поток не попадает."""
        # Добавляем событие напрямую в events_history с неизвестным типом
        session.runtime.events_history.append(
            {
                "type": "session_update",
                "update": {"sessionUpdate": "unknown_type", "data": "test"},
                "timestamp": "2024-01-01T00:00:00Z",
            }
        )
        # И валидное событие
        history_writer.save_user_message_chunk(session, {"type": "text", "text": "Hello"})

        notifications = replayer.replay_history(session)

        # Только валидное событие должно быть в replay
        assert len(notifications) == 1
        assert notifications[0].params["update"]["sessionUpdate"] == "user_message_chunk"


class TestReplayLatestPlan:
    """Тесты для replay_latest_plan."""

    def test_returns_none_for_empty_plan(
        self,
        replayer: SessionReplayer,
        history_writer: EventHistoryWriter,
        session: DomainSession,
    ) -> None:
        """Проверяет возврат None когда плана нет."""
        result = replayer.replay_latest_plan(session)

        assert result is None

    def test_replays_latest_plan(
        self,
        replayer: SessionReplayer,
        history_writer: EventHistoryWriter,
        session: DomainSession,
    ) -> None:
        """Проверяет replay последнего плана в ACP-форме (P2-26)."""
        plan_entries = [
            {"content": "Step 1", "priority": "high", "status": "completed"},
            {"content": "Step 2", "priority": "medium", "status": "pending"},
        ]
        session.plan = AgentPlan(steps=PlanMapper.from_acp(plan_entries))

        notification = replayer.replay_latest_plan(session)

        assert notification is not None
        assert notification.method == "session/update"
        assert notification.params["sessionId"] == "sess_test_001"
        assert notification.params["update"]["sessionUpdate"] == "plan"
        assert notification.params["update"]["entries"] == plan_entries

    def test_replays_plan_with_planstep_objects_is_serializable(
        self,
        replayer: SessionReplayer,
        history_writer: EventHistoryWriter,
        session: DomainSession,
    ) -> None:
        """Регресс: пре-P2-26 план (форма `description`) сериализуется после загрузки.

        Ранее session/load сессии с планом крашил WS-соединение с
        `TypeError: Object of type PlanStep is not JSON serializable`. Носитель
        реплея — доменный агрегат (ADR-006, D5), поэтому старая wire-форма
        приходит сюда так же, как из хранилища: через маппер.
        """
        from codelab.server.models import PlanStep

        session.plan = AgentPlan(
            steps=PlanMapper.from_acp(
                PlanMapper.entries_to_acp(
                    [
                        PlanStep(description="Step 1", status="completed"),
                        PlanStep(description="Step 2", status="pending"),
                    ]
                )
            )
        )

        notification = replayer.replay_latest_plan(session)

        assert notification is not None
        # Не должно падать: entries сериализованы в dict.
        payload = notification.to_json()
        assert "Step 1" in payload
        entries = notification.params["update"]["entries"]
        assert entries == [
            {"content": "Step 1", "priority": "medium", "status": "completed"},
            {"content": "Step 2", "priority": "medium", "status": "pending"},
        ]

    def test_replays_domain_plan_entries(
        self,
        replayer: SessionReplayer,
        history_writer: EventHistoryWriter,
        session: DomainSession,
    ) -> None:
        """Доменные PlanEntry проходят путь реплея (блокер фазы D снят).

        До шага Plan↔ACP путь звал `model_dump()`, поэтому доменная запись —
        не-pydantic dataclass — уходила в wire как есть и роняла `to_json`.
        """
        from codelab.server.domain.plan import PlanEntry
        from codelab.server.domain.value_objects import PlanPriority, PlanStatus

        session.plan = AgentPlan(
            steps=[
                PlanEntry(
                    content="Step 1", priority=PlanPriority.HIGH, status=PlanStatus.IN_PROGRESS
                )
            ]
        )

        notification = replayer.replay_latest_plan(session)

        assert notification is not None
        notification.to_json()
        assert notification.params["update"]["entries"] == [
            {"content": "Step 1", "priority": "high", "status": "in_progress"}
        ]


class TestIntegrationWithSessionLoad:
    """Интеграционные тесты для использования в session/load."""

    def test_full_session_replay_scenario(
        self,
        replayer: SessionReplayer,
        history_writer: EventHistoryWriter,
        session: DomainSession,
    ) -> None:
        """Проверяет полный сценарий replay для session/load."""
        # Симулируем историю сессии
        # Turn 1: Пользователь спрашивает, агент отвечает
        history_writer.save_user_message_chunk(
            session, {"type": "text", "text": "What is in config.json?"}
        )
        history_writer.save_tool_call(
            session=session,
            tool_call_id="call_001",
            title="fs/read_text_file",
            kind="read",
            status="pending",
        )
        history_writer.save_tool_call_update(
            session=session,
            tool_call_id="call_001",
            status="in_progress",
        )
        history_writer.save_tool_call_update(
            session=session,
            tool_call_id="call_001",
            status="completed",
            content=[{"type": "text", "text": '{"key": "value"}'}],
        )
        history_writer.save_agent_message_chunk(
            session, {"type": "text", "text": "The config contains..."}
        )

        # Turn 2: Пользователь просит изменить
        history_writer.save_user_message_chunk(
            session, {"type": "text", "text": "Change key to newvalue"}
        )
        history_writer.save_tool_call(
            session=session,
            tool_call_id="call_002",
            title="fs/write_text_file",
            kind="edit",
            status="pending",
        )
        history_writer.save_tool_call_update(
            session=session,
            tool_call_id="call_002",
            status="completed",
        )
        history_writer.save_agent_message_chunk(
            session, {"type": "text", "text": "Done! The file has been updated."}
        )

        # Session info
        history_writer.save_session_info_update(
            session, title="What is in config.json?", updated_at="2024-01-01T12:00:00Z"
        )

        # Воспроизводим историю
        notifications = replayer.replay_history(session)

        # Turn 1: user_message_chunk, tool_call, tool_call_update x2, agent_message_chunk (5)
        # Turn 2: user_message_chunk, tool_call, tool_call_update, agent_message_chunk (4)
        # session_info_update не реплеится: у события нет реплей-формы (шаг 3a ADR-008)
        assert len(notifications) == 9

        # Проверяем что все sessionId корректны
        for notification in notifications:
            assert notification.params["sessionId"] == "sess_test_001"

        # Проверяем порядок событий
        update_types = [n.params["update"]["sessionUpdate"] for n in notifications]
        assert "session_info_update" not in update_types
        assert update_types[-1] == "agent_message_chunk"
        # Проверяем что все типы валидны
        assert update_types[0] == "user_message_chunk"  # Turn 1 start
        assert update_types[1] == "tool_call"
        assert update_types[4] == "agent_message_chunk"  # Turn 1 end

"""Тесты для ReplayManager.

Проверяет функциональность сохранения и воспроизведения session/update уведомлений
для session/load согласно спецификации ACP (protocol/03-Session Setup.md).
"""

from __future__ import annotations

import pytest

from codelab.server.protocol.handlers.replay_manager import ReplayManager
from codelab.server.protocol.state import SessionState


@pytest.fixture
def session() -> SessionState:
    """Создает тестовую сессию."""
    return SessionState(
        session_id="sess_test_001",
        cwd="/tmp/test",
        mcp_servers=[],
    )


@pytest.fixture
def replay_manager() -> ReplayManager:
    """Создает экземпляр ReplayManager."""
    return ReplayManager()


class TestSaveUserMessageChunk:
    """Тесты для save_user_message_chunk."""

    def test_saves_text_content(
        self,
        replay_manager: ReplayManager,
        session: SessionState,
    ) -> None:
        """Проверяет сохранение текстового сообщения пользователя."""
        content = {"type": "text", "text": "Hello, agent!"}
        
        replay_manager.save_user_message_chunk(session, content)
        
        assert len(session.events_history) == 1
        event = session.events_history[0]
        assert event["type"] == "session_update"
        assert event["update"]["sessionUpdate"] == "user_message_chunk"
        assert event["update"]["content"] == content
        assert "timestamp" in event

    def test_saves_multiple_chunks(
        self,
        replay_manager: ReplayManager,
        session: SessionState,
    ) -> None:
        """Проверяет сохранение нескольких content chunks."""
        chunks = [
            {"type": "text", "text": "First message"},
            {"type": "image", "data": "base64data", "mimeType": "image/png"},
        ]
        
        for chunk in chunks:
            replay_manager.save_user_message_chunk(session, chunk)
        
        assert len(session.events_history) == 2


class TestSaveAgentMessageChunk:
    """Тесты для save_agent_message_chunk."""

    def test_saves_agent_response(
        self,
        replay_manager: ReplayManager,
        session: SessionState,
    ) -> None:
        """Проверяет сохранение ответа агента."""
        content = {"type": "text", "text": "Agent response"}
        
        replay_manager.save_agent_message_chunk(session, content)
        
        assert len(session.events_history) == 1
        event = session.events_history[0]
        assert event["update"]["sessionUpdate"] == "agent_message_chunk"
        assert event["update"]["content"] == content


class TestSaveToolCall:
    """Тесты для save_tool_call."""

    def test_saves_tool_call(
        self,
        replay_manager: ReplayManager,
        session: SessionState,
    ) -> None:
        """Проверяет сохранение tool_call события."""
        replay_manager.save_tool_call(
            session=session,
            tool_call_id="call_001",
            title="fs/read_text_file",
            kind="read",
            status="pending",
        )
        
        assert len(session.events_history) == 1
        event = session.events_history[0]
        assert event["update"]["sessionUpdate"] == "tool_call"
        assert event["update"]["toolCallId"] == "call_001"
        assert event["update"]["title"] == "fs/read_text_file"
        assert event["update"]["kind"] == "read"
        assert event["update"]["status"] == "pending"

    def test_saves_tool_call_with_content(
        self,
        replay_manager: ReplayManager,
        session: SessionState,
    ) -> None:
        """Проверяет сохранение tool_call с контентом."""
        content = [{"type": "text", "text": "Initial content"}]
        
        replay_manager.save_tool_call(
            session=session,
            tool_call_id="call_002",
            title="Test tool",
            kind="other",
            status="pending",
            content=content,
        )
        
        event = session.events_history[0]
        assert event["update"]["content"] == content


class TestSaveToolCallUpdate:
    """Тесты для save_tool_call_update."""

    def test_saves_in_progress_update(
        self,
        replay_manager: ReplayManager,
        session: SessionState,
    ) -> None:
        """Проверяет сохранение in_progress обновления."""
        replay_manager.save_tool_call_update(
            session=session,
            tool_call_id="call_001",
            status="in_progress",
        )
        
        event = session.events_history[0]
        assert event["update"]["sessionUpdate"] == "tool_call_update"
        assert event["update"]["toolCallId"] == "call_001"
        assert event["update"]["status"] == "in_progress"

    def test_saves_completed_update_with_content(
        self,
        replay_manager: ReplayManager,
        session: SessionState,
    ) -> None:
        """Проверяет сохранение completed обновления с контентом."""
        content = [{"type": "content", "content": {"type": "text", "text": "Result"}}]
        
        replay_manager.save_tool_call_update(
            session=session,
            tool_call_id="call_001",
            status="completed",
            content=content,
        )
        
        event = session.events_history[0]
        assert event["update"]["status"] == "completed"
        assert event["update"]["content"] == content


class TestSavePlan:
    """Тесты для save_plan."""

    def test_saves_plan_entries(
        self,
        replay_manager: ReplayManager,
        session: SessionState,
    ) -> None:
        """Проверяет сохранение плана."""
        entries = [
            {"title": "Step 1", "description": "First step"},
            {"title": "Step 2", "description": "Second step"},
        ]
        
        replay_manager.save_plan(session, entries)
        
        event = session.events_history[0]
        assert event["update"]["sessionUpdate"] == "plan"
        assert event["update"]["entries"] == entries


class TestSaveSessionInfo:
    """Тесты для save_session_info."""

    def test_saves_session_info(
        self,
        replay_manager: ReplayManager,
        session: SessionState,
    ) -> None:
        """Проверяет сохранение информации о сессии."""
        replay_manager.save_session_info(
            session=session,
            title="Test session",
            updated_at="2024-01-01T00:00:00Z",
        )
        
        event = session.events_history[0]
        assert event["update"]["sessionUpdate"] == "session_info"
        assert event["update"]["title"] == "Test session"
        assert event["update"]["updated_at"] == "2024-01-01T00:00:00Z"


class TestReplayHistory:
    """Тесты для replay_history."""

    def test_replays_empty_history(
        self,
        replay_manager: ReplayManager,
        session: SessionState,
    ) -> None:
        """Проверяет replay пустой истории."""
        notifications = replay_manager.replay_history(session)
        
        assert notifications == []

    def test_replays_user_and_agent_messages(
        self,
        replay_manager: ReplayManager,
        session: SessionState,
    ) -> None:
        """Проверяет replay сообщений пользователя и агента."""
        # Сохраняем историю
        replay_manager.save_user_message_chunk(
            session, {"type": "text", "text": "User question"}
        )
        replay_manager.save_agent_message_chunk(
            session, {"type": "text", "text": "Agent answer"}
        )
        
        # Воспроизводим
        notifications = replay_manager.replay_history(session)
        
        assert len(notifications) == 2
        
        # Проверяем user_message_chunk
        assert notifications[0].method == "session/update"
        assert notifications[0].params["sessionId"] == "sess_test_001"
        assert notifications[0].params["update"]["sessionUpdate"] == "user_message_chunk"
        
        # Проверяем agent_message_chunk
        assert notifications[1].params["update"]["sessionUpdate"] == "agent_message_chunk"

    def test_replays_tool_call_lifecycle(
        self,
        replay_manager: ReplayManager,
        session: SessionState,
    ) -> None:
        """Проверяет replay полного жизненного цикла tool call."""
        # Сохраняем события tool call
        replay_manager.save_tool_call(
            session=session,
            tool_call_id="call_001",
            title="fs/read_text_file",
            kind="read",
            status="pending",
        )
        replay_manager.save_tool_call_update(
            session=session,
            tool_call_id="call_001",
            status="in_progress",
        )
        replay_manager.save_tool_call_update(
            session=session,
            tool_call_id="call_001",
            status="completed",
            content=[{"type": "text", "text": "File content"}],
        )
        
        # Воспроизводим
        notifications = replay_manager.replay_history(session)
        
        assert len(notifications) == 3
        assert notifications[0].params["update"]["sessionUpdate"] == "tool_call"
        assert notifications[1].params["update"]["sessionUpdate"] == "tool_call_update"
        assert notifications[1].params["update"]["status"] == "in_progress"
        assert notifications[2].params["update"]["sessionUpdate"] == "tool_call_update"
        assert notifications[2].params["update"]["status"] == "completed"

    def test_replays_full_conversation(
        self,
        replay_manager: ReplayManager,
        session: SessionState,
    ) -> None:
        """Проверяет replay полной беседы с tool calls."""
        # Симулируем полную беседу
        replay_manager.save_user_message_chunk(
            session, {"type": "text", "text": "Read file.txt"}
        )
        replay_manager.save_tool_call(
            session=session,
            tool_call_id="call_001",
            title="fs/read_text_file",
            kind="read",
            status="pending",
        )
        replay_manager.save_tool_call_update(
            session=session,
            tool_call_id="call_001",
            status="completed",
        )
        replay_manager.save_agent_message_chunk(
            session, {"type": "text", "text": "Here is the file content..."}
        )
        replay_manager.save_session_info(
            session, title="Read file.txt", updated_at="2024-01-01T00:00:00Z"
        )
        
        # Воспроизводим
        notifications = replay_manager.replay_history(session)
        
        assert len(notifications) == 5
        
        # Проверяем порядок
        update_types = [
            n.params["update"]["sessionUpdate"] for n in notifications
        ]
        assert update_types == [
            "user_message_chunk",
            "tool_call",
            "tool_call_update",
            "agent_message_chunk",
            "session_info",
        ]

    def test_filters_non_replayable_events(
        self,
        replay_manager: ReplayManager,
        session: SessionState,
    ) -> None:
        """Проверяет что события не из _REPLAYABLE_UPDATE_TYPES пропускаются."""
        # Добавляем событие напрямую в events_history с неизвестным типом
        session.events_history.append({
            "type": "session_update",
            "update": {"sessionUpdate": "unknown_type", "data": "test"},
            "timestamp": "2024-01-01T00:00:00Z",
        })
        # И валидное событие
        replay_manager.save_user_message_chunk(
            session, {"type": "text", "text": "Hello"}
        )
        
        notifications = replay_manager.replay_history(session)
        
        # Только валидное событие должно быть в replay
        assert len(notifications) == 1
        assert notifications[0].params["update"]["sessionUpdate"] == "user_message_chunk"


class TestReplayLatestPlan:
    """Тесты для replay_latest_plan."""

    def test_returns_none_for_empty_plan(
        self,
        replay_manager: ReplayManager,
        session: SessionState,
    ) -> None:
        """Проверяет возврат None когда плана нет."""
        result = replay_manager.replay_latest_plan(session)
        
        assert result is None

    def test_replays_latest_plan(
        self,
        replay_manager: ReplayManager,
        session: SessionState,
    ) -> None:
        """Проверяет replay последнего плана."""
        session.latest_plan = [
            {"title": "Step 1", "status": "completed"},
            {"title": "Step 2", "status": "pending"},
        ]
        
        notification = replay_manager.replay_latest_plan(session)
        
        assert notification is not None
        assert notification.method == "session/update"
        assert notification.params["sessionId"] == "sess_test_001"
        assert notification.params["update"]["sessionUpdate"] == "plan"
        assert notification.params["update"]["entries"] == session.latest_plan


class TestIntegrationWithSessionLoad:
    """Интеграционные тесты для использования в session/load."""

    def test_full_session_replay_scenario(
        self,
        replay_manager: ReplayManager,
        session: SessionState,
    ) -> None:
        """Проверяет полный сценарий replay для session/load."""
        # Симулируем историю сессии
        # Turn 1: Пользователь спрашивает, агент отвечает
        replay_manager.save_user_message_chunk(
            session, {"type": "text", "text": "What is in config.json?"}
        )
        replay_manager.save_tool_call(
            session=session,
            tool_call_id="call_001",
            title="fs/read_text_file",
            kind="read",
            status="pending",
        )
        replay_manager.save_tool_call_update(
            session=session,
            tool_call_id="call_001",
            status="in_progress",
        )
        replay_manager.save_tool_call_update(
            session=session,
            tool_call_id="call_001",
            status="completed",
            content=[{"type": "text", "text": '{"key": "value"}'}],
        )
        replay_manager.save_agent_message_chunk(
            session, {"type": "text", "text": "The config contains..."}
        )
        
        # Turn 2: Пользователь просит изменить
        replay_manager.save_user_message_chunk(
            session, {"type": "text", "text": "Change key to newvalue"}
        )
        replay_manager.save_tool_call(
            session=session,
            tool_call_id="call_002",
            title="fs/write_text_file",
            kind="edit",
            status="pending",
        )
        replay_manager.save_tool_call_update(
            session=session,
            tool_call_id="call_002",
            status="completed",
        )
        replay_manager.save_agent_message_chunk(
            session, {"type": "text", "text": "Done! The file has been updated."}
        )
        
        # Session info
        replay_manager.save_session_info(
            session, title="What is in config.json?", updated_at="2024-01-01T12:00:00Z"
        )
        
        # Воспроизводим историю
        notifications = replay_manager.replay_history(session)
        
        # Проверяем количество - 10 событий
        # Turn 1: user_message_chunk, tool_call, tool_call_update x2, agent_message_chunk (5)
        # Turn 2: user_message_chunk, tool_call, tool_call_update, agent_message_chunk (4)
        # session_info (1)
        assert len(notifications) == 10
        
        # Проверяем что все sessionId корректны
        for notification in notifications:
            assert notification.params["sessionId"] == "sess_test_001"
        
        # Проверяем порядок событий
        update_types = [n.params["update"]["sessionUpdate"] for n in notifications]
        # session_info в REPLAYABLE, проверяем последний
        assert update_types[-1] == "session_info"
        # Проверяем что все типы валидны
        assert update_types[0] == "user_message_chunk"  # Turn 1 start
        assert update_types[1] == "tool_call"
        assert update_types[4] == "agent_message_chunk"  # Turn 1 end

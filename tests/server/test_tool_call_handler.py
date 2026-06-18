"""Unit-тесты для ToolCallHandler.

Тестирует создание tool calls, управление их статусами, построение notifications
и обработку executor/policy modes.
"""

from __future__ import annotations

import pytest

from codelab.server.protocol.handlers.tool_call_handler import ToolCallHandler
from codelab.server.protocol.state import ClientRuntimeCapabilities, SessionState


@pytest.fixture
def handler() -> ToolCallHandler:
    """Фикстура для создания ToolCallHandler."""
    return ToolCallHandler()


@pytest.fixture
def session() -> SessionState:
    """Фикстура для создания базовой сессии с runtime capabilities."""
    sess = SessionState(
        session_id="test_session",
        cwd="/tmp",
        mcp_servers=[],
    )
    sess.runtime_capabilities = ClientRuntimeCapabilities(
        terminal=True,
        fs_read=True,
        fs_write=True,
    )
    return sess


class TestToolCallHandlerCreation:
    """Тесты создания tool calls."""

    def test_create_tool_call_incremental_id(
        self, handler: ToolCallHandler, session: SessionState
    ) -> None:
        """Проверяет генерацию монотонных ID при создании tool calls."""
        # Создаем несколько tool calls
        id1 = handler.create_tool_call(session, title="First", kind="execute")
        id2 = handler.create_tool_call(session, title="Second", kind="read")
        id3 = handler.create_tool_call(session, title="Third", kind="delete")

        # Проверяем монотонный формат ID
        assert id1 == "call_001"
        assert id2 == "call_002"
        assert id3 == "call_003"

    def test_create_tool_call_records_in_session(
        self, handler: ToolCallHandler, session: SessionState
    ) -> None:
        """Проверяет, что созданный tool call записывается в session.tool_calls."""
        tool_call_id = handler.create_tool_call(session, title="Demo", kind="execute")

        # Проверяем наличие в tool_calls
        assert tool_call_id in session.tool_calls
        tool_call = session.tool_calls[tool_call_id]
        assert tool_call.tool_call_id == tool_call_id
        assert tool_call.title == "Demo"
        assert tool_call.kind == "execute"
        assert tool_call.status == "pending"
        assert tool_call.content == []

    def test_create_tool_call_increments_counter(
        self, handler: ToolCallHandler, session: SessionState
    ) -> None:
        """Проверяет, что счетчик tool_call_counter увеличивается."""
        initial_counter = session.tool_call_counter
        handler.create_tool_call(session, title="Test", kind="other")
        assert session.tool_call_counter == initial_counter + 1


class TestToolCallHandlerStatusUpdates:
    """Тесты обновления статуса tool call."""

    def test_update_pending_to_in_progress(
        self, handler: ToolCallHandler, session: SessionState
    ) -> None:
        """Проверяет переход pending → in_progress."""
        tool_call_id = handler.create_tool_call(session, title="Test", kind="execute")

        handler.update_tool_call_status(session, tool_call_id, "in_progress")

        assert session.tool_calls[tool_call_id].status == "in_progress"

    def test_update_in_progress_to_completed(
        self, handler: ToolCallHandler, session: SessionState
    ) -> None:
        """Проверяет переход in_progress → completed."""
        tool_call_id = handler.create_tool_call(session, title="Test", kind="execute")
        handler.update_tool_call_status(session, tool_call_id, "in_progress")

        content = [{"type": "content", "content": {"type": "text", "text": "Done"}}]
        handler.update_tool_call_status(session, tool_call_id, "completed", content=content)

        assert session.tool_calls[tool_call_id].status == "completed"
        assert session.tool_calls[tool_call_id].content == content

    def test_update_pending_to_cancelled(
        self, handler: ToolCallHandler, session: SessionState
    ) -> None:
        """Проверяет переход pending → cancelled."""
        tool_call_id = handler.create_tool_call(session, title="Test", kind="execute")

        handler.update_tool_call_status(session, tool_call_id, "cancelled")

        assert session.tool_calls[tool_call_id].status == "cancelled"

    def test_update_pending_to_failed(
        self, handler: ToolCallHandler, session: SessionState
    ) -> None:
        """Проверяет переход pending → failed."""
        tool_call_id = handler.create_tool_call(session, title="Test", kind="execute")

        handler.update_tool_call_status(session, tool_call_id, "failed")

        assert session.tool_calls[tool_call_id].status == "failed"

    def test_reject_invalid_transition_completed_to_in_progress(
        self, handler: ToolCallHandler, session: SessionState
    ) -> None:
        """Проверяет отказ от невалидного перехода completed → in_progress."""
        tool_call_id = handler.create_tool_call(session, title="Test", kind="execute")
        handler.update_tool_call_status(session, tool_call_id, "in_progress")
        handler.update_tool_call_status(session, tool_call_id, "completed")

        # Попытаемся вернуться в in_progress (должно быть отклонено)
        handler.update_tool_call_status(session, tool_call_id, "in_progress")

        # Статус остается completed
        assert session.tool_calls[tool_call_id].status == "completed"

    def test_reject_invalid_transition_cancelled_to_in_progress(
        self, handler: ToolCallHandler, session: SessionState
    ) -> None:
        """Проверяет отказ от невалидного перехода cancelled → in_progress."""
        tool_call_id = handler.create_tool_call(session, title="Test", kind="execute")
        handler.update_tool_call_status(session, tool_call_id, "cancelled")

        # Попытаемся перейти в in_progress (должно быть отклонено)
        handler.update_tool_call_status(session, tool_call_id, "in_progress")

        assert session.tool_calls[tool_call_id].status == "cancelled"

    def test_update_with_content(self, handler: ToolCallHandler, session: SessionState) -> None:
        """Проверяет обновление статуса с контентом."""
        tool_call_id = handler.create_tool_call(session, title="Test", kind="execute")

        content = [{"type": "content", "content": {"type": "text", "text": "Result"}}]
        handler.update_tool_call_status(session, tool_call_id, "in_progress", content=content)

        assert session.tool_calls[tool_call_id].content == content

    def test_update_nonexistent_tool_call(
        self, handler: ToolCallHandler, session: SessionState
    ) -> None:
        """Проверяет, что обновление несуществующего tool call игнорируется."""
        # Попытаемся обновить несуществующий tool call
        handler.update_tool_call_status(session, "nonexistent", "completed")

        # Ничего не должно случиться (no exception, no change)
        assert "nonexistent" not in session.tool_calls


class TestToolCallHandlerExecutorMode:
    """Тесты executor mode для tool calls."""

    def test_executor_mode_in_progress_then_completed(
        self, handler: ToolCallHandler, session: SessionState
    ) -> None:
        """Проверяет executor mode: pending → in_progress → completed."""
        tool_call_id = handler.create_tool_call(session, title="Test", kind="execute")

        updates = handler.build_executor_execution_updates(
            session=session,
            session_id="test_session",
            tool_call_id=tool_call_id,
            leave_running=False,
        )

        # Должны быть 2 notification: in_progress и completed
        assert len(updates) == 2
        assert updates[0].method == "session/update"
        assert updates[1].method == "session/update"

        # Проверяем статусы в session
        assert session.tool_calls[tool_call_id].status == "completed"

    def test_executor_mode_leave_running(
        self, handler: ToolCallHandler, session: SessionState
    ) -> None:
        """Проверяет executor mode с leave_running=True."""
        tool_call_id = handler.create_tool_call(session, title="Test", kind="execute")

        updates = handler.build_executor_execution_updates(
            session=session,
            session_id="test_session",
            tool_call_id=tool_call_id,
            leave_running=True,
        )

        # Должна быть только 1 notification: in_progress
        assert len(updates) == 1
        assert session.tool_calls[tool_call_id].status == "in_progress"


class TestToolCallHandlerPolicyMode:
    """Тесты policy mode для tool calls."""

    def test_policy_allowed_in_progress_then_completed(
        self, handler: ToolCallHandler, session: SessionState
    ) -> None:
        """Проверяет policy mode с разрешением: pending → in_progress → completed."""
        tool_call_id = handler.create_tool_call(session, title="Test", kind="execute")

        updates = handler.build_policy_execution_updates(
            session=session,
            session_id="test_session",
            tool_call_id=tool_call_id,
            allowed=True,
        )

        # Должны быть 2 notification: in_progress и completed
        assert len(updates) == 2
        assert session.tool_calls[tool_call_id].status == "completed"

    def test_policy_rejected_cancelled(
        self, handler: ToolCallHandler, session: SessionState
    ) -> None:
        """Проверяет policy mode с отказом: pending → cancelled."""
        tool_call_id = handler.create_tool_call(session, title="Test", kind="execute")

        updates = handler.build_policy_execution_updates(
            session=session,
            session_id="test_session",
            tool_call_id=tool_call_id,
            allowed=False,
        )

        # Должна быть 1 notification: cancelled
        assert len(updates) == 1
        assert session.tool_calls[tool_call_id].status == "cancelled"


class TestToolCallHandlerCancellation:
    """Тесты отмены tool calls."""

    def test_cancel_all_active_tools(self, handler: ToolCallHandler, session: SessionState) -> None:
        """Проверяет отмену всех активных tool calls."""
        # Создаем несколько tool calls в разных статусах
        id1 = handler.create_tool_call(session, title="Test1", kind="execute")
        id2 = handler.create_tool_call(session, title="Test2", kind="read")
        id3 = handler.create_tool_call(session, title="Test3", kind="delete")

        # Переводим в разные статусы
        handler.update_tool_call_status(session, id1, "in_progress")
        handler.update_tool_call_status(session, id2, "in_progress")
        handler.update_tool_call_status(session, id2, "completed")

        # Отменяем все активные
        updates = handler.cancel_active_tools(session, "test_session")

        # Должны быть отмены для id1 и id3 (в_progress и pending)
        assert len(updates) == 2
        assert session.tool_calls[id1].status == "cancelled"
        assert session.tool_calls[id2].status == "completed"  # не изменился
        assert session.tool_calls[id3].status == "cancelled"

    def test_cancel_ignores_completed_tools(
        self, handler: ToolCallHandler, session: SessionState
    ) -> None:
        """Проверяет, что отмена игнорирует завершенные tool calls."""
        id1 = handler.create_tool_call(session, title="Test", kind="execute")
        handler.update_tool_call_status(session, id1, "in_progress")
        handler.update_tool_call_status(session, id1, "completed")

        updates = handler.cancel_active_tools(session, "test_session")

        # Не должно быть notifications, так как tool call уже завершен
        assert len(updates) == 0
        assert session.tool_calls[id1].status == "completed"

    def test_cancel_empty_session(self, handler: ToolCallHandler, session: SessionState) -> None:
        """Проверяет отмену в пустой сессии (без tool calls)."""
        updates = handler.cancel_active_tools(session, "test_session")

        assert len(updates) == 0


class TestToolCallHandlerNotifications:
    """Тесты построения notifications."""

    def test_tool_call_notification_structure(self, handler: ToolCallHandler) -> None:
        """Проверяет структуру tool_call notification."""
        msg = handler.build_tool_call_notification(
            session_id="sess_1",
            tool_call_id="call_001",
            title="Test Tool",
            kind="execute",
        )

        assert msg.method == "session/update"
        assert msg.params is not None
        assert msg.params["sessionId"] == "sess_1"

        update = msg.params["update"]
        assert update["sessionUpdate"] == "tool_call"
        assert update["toolCallId"] == "call_001"
        assert update["title"] == "Test Tool"
        assert update["kind"] == "execute"
        assert update["status"] == "pending"

    def test_tool_call_notification_with_locations(self, handler: ToolCallHandler) -> None:
        """Проверяет tool_call notification с locations."""
        locations = [{"path": "/tmp/file.txt"}]
        msg = handler.build_tool_call_notification(
            session_id="sess_1",
            tool_call_id="call_001",
            title="Read File",
            kind="read",
            locations=locations,
        )

        update = msg.params["update"]
        assert update["locations"] == locations

    def test_tool_update_notification_structure(self, handler: ToolCallHandler) -> None:
        """Проверяет структуру tool_call_update notification."""
        msg = handler.build_tool_update_notification(
            session_id="sess_1",
            tool_call_id="call_001",
            status="in_progress",
        )

        assert msg.method == "session/update"
        assert msg.params is not None
        assert msg.params["sessionId"] == "sess_1"

        update = msg.params["update"]
        assert update["sessionUpdate"] == "tool_call_update"
        assert update["toolCallId"] == "call_001"
        assert update["status"] == "in_progress"

    def test_tool_update_notification_with_content(self, handler: ToolCallHandler) -> None:
        """Проверяет tool_call_update notification с контентом."""
        content = [{"type": "content", "content": {"type": "text", "text": "Result"}}]
        msg = handler.build_tool_update_notification(
            session_id="sess_1",
            tool_call_id="call_001",
            status="completed",
            content=content,
        )

        update = msg.params["update"]
        assert update["content"] == content


class TestToolCallHandlerCapabilities:
    """Тесты проверки runtime capabilities."""

    def test_can_run_tools_with_all_capabilities(
        self, handler: ToolCallHandler, session: SessionState
    ) -> None:
        """Проверяет can_run_tools когда все capabilities доступны."""
        session.runtime_capabilities = ClientRuntimeCapabilities(
            terminal=True,
            fs_read=True,
            fs_write=True,
        )
        assert handler.can_run_tools(session) is True

    def test_can_run_tools_with_terminal_only(
        self, handler: ToolCallHandler, session: SessionState
    ) -> None:
        """Проверяет can_run_tools с только terminal capability."""
        session.runtime_capabilities = ClientRuntimeCapabilities(
            terminal=True,
            fs_read=False,
            fs_write=False,
        )
        assert handler.can_run_tools(session) is True

    def test_can_run_tools_with_no_capabilities(
        self, handler: ToolCallHandler, session: SessionState
    ) -> None:
        """Проверяет can_run_tools когда нет capabilities."""
        session.runtime_capabilities = ClientRuntimeCapabilities(
            terminal=False,
            fs_read=False,
            fs_write=False,
        )
        assert handler.can_run_tools(session) is False

    def test_can_run_tools_with_none_capabilities(
        self, handler: ToolCallHandler, session: SessionState
    ) -> None:
        """Проверяет can_run_tools когда runtime_capabilities не установлены."""
        session.runtime_capabilities = None
        assert handler.can_run_tools(session) is False

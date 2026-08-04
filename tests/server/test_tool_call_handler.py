"""Unit-тесты для ToolCallHandler.

Тестирует создание tool calls, управление их статусами, построение notifications
и обработку executor/policy modes.
"""

from __future__ import annotations

import pytest
import structlog

from codelab.server.domain.session import Session as DomainSession
from codelab.server.domain.value_objects import ToolCallStatus
from codelab.server.protocol.handlers.tool_call_handler import ToolCallHandler
from codelab.server.storage.document import ClientRuntimeCapabilities
from tests.server._domain_sessions import make_domain_session


@pytest.fixture
def handler() -> ToolCallHandler:
    """Фикстура для создания ToolCallHandler."""
    return ToolCallHandler()


@pytest.fixture
def session() -> DomainSession:
    """Фикстура для создания базовой сессии с runtime capabilities."""
    sess = make_domain_session(
        session_id="test_session",
        cwd="/tmp",
        mcp_servers=[],
        runtime_capabilities=ClientRuntimeCapabilities(
        terminal=True,
        fs_read=True,
        fs_write=True,
    ),
    )
    return sess


class TestToolCallHandlerCreation:
    """Тесты создания tool calls."""

    def test_create_tool_call_incremental_id(
        self, handler: ToolCallHandler, session: DomainSession
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
        self, handler: ToolCallHandler, session: DomainSession
    ) -> None:
        """Проверяет, что созданный tool call записывается в session.tool_calls."""
        tool_call_id = handler.create_tool_call(session, title="Demo", kind="execute")

        # Проверяем наличие в tool_calls
        assert tool_call_id in session.tool_calls.calls
        tool_call = session.tool_calls.calls[tool_call_id]
        assert tool_call.id == tool_call_id
        assert tool_call.title == "Demo"
        assert tool_call.kind == "execute"
        assert tool_call.status == "pending"
        assert tool_call.result is None

    def test_create_tool_call_increments_counter(
        self, handler: ToolCallHandler, session: DomainSession
    ) -> None:
        """Проверяет, что счетчик tool_call_counter увеличивается."""
        initial_counter = session.tool_calls.counter
        handler.create_tool_call(session, title="Test", kind="other")
        assert session.tool_calls.counter == initial_counter + 1


class TestToolCallHandlerStatusUpdates:
    """Тесты обновления статуса tool call."""

    def test_update_pending_to_in_progress(
        self, handler: ToolCallHandler, session: DomainSession
    ) -> None:
        """Проверяет переход pending → in_progress."""
        tool_call_id = handler.create_tool_call(session, title="Test", kind="execute")

        handler.update_tool_call_status(session, tool_call_id, "in_progress")

        assert session.tool_calls.calls[tool_call_id].status == "in_progress"

    def test_update_in_progress_to_completed(
        self, handler: ToolCallHandler, session: DomainSession
    ) -> None:
        """Проверяет переход in_progress → completed."""
        tool_call_id = handler.create_tool_call(session, title="Test", kind="execute")
        handler.update_tool_call_status(session, tool_call_id, "in_progress")

        content = [{"type": "content", "content": {"type": "text", "text": "Done"}}]
        handler.update_tool_call_status(session, tool_call_id, "completed", content=content)

        assert session.tool_calls.calls[tool_call_id].status == "completed"
        assert session.tool_calls.calls[tool_call_id].result.content == content

    def test_update_pending_to_cancelled(
        self, handler: ToolCallHandler, session: DomainSession
    ) -> None:
        """Проверяет переход pending → cancelled."""
        tool_call_id = handler.create_tool_call(session, title="Test", kind="execute")

        handler.update_tool_call_status(session, tool_call_id, "cancelled")

        assert session.tool_calls.calls[tool_call_id].status == "cancelled"

    def test_update_pending_to_failed(
        self, handler: ToolCallHandler, session: DomainSession
    ) -> None:
        """Проверяет переход pending → failed."""
        tool_call_id = handler.create_tool_call(session, title="Test", kind="execute")

        handler.update_tool_call_status(session, tool_call_id, "failed")

        assert session.tool_calls.calls[tool_call_id].status == "failed"

    def test_reject_invalid_transition_completed_to_in_progress(
        self, handler: ToolCallHandler, session: DomainSession
    ) -> None:
        """Проверяет отказ от невалидного перехода completed → in_progress."""
        tool_call_id = handler.create_tool_call(session, title="Test", kind="execute")
        handler.update_tool_call_status(session, tool_call_id, "in_progress")
        handler.update_tool_call_status(session, tool_call_id, "completed")

        # Попытаемся вернуться в in_progress (должно быть отклонено)
        handler.update_tool_call_status(session, tool_call_id, "in_progress")

        # Статус остается completed
        assert session.tool_calls.calls[tool_call_id].status == "completed"

    def test_reject_invalid_transition_cancelled_to_in_progress(
        self, handler: ToolCallHandler, session: DomainSession
    ) -> None:
        """Проверяет отказ от невалидного перехода cancelled → in_progress."""
        tool_call_id = handler.create_tool_call(session, title="Test", kind="execute")
        handler.update_tool_call_status(session, tool_call_id, "cancelled")

        # Попытаемся перейти в in_progress (должно быть отклонено)
        handler.update_tool_call_status(session, tool_call_id, "in_progress")

        assert session.tool_calls.calls[tool_call_id].status == "cancelled"

    def test_pending_to_completed_is_rejected(
        self, handler: ToolCallHandler, session: DomainSession
    ) -> None:
        """pending → completed запрещён: завершение возможно только из in_progress."""
        tool_call_id = handler.create_tool_call(session, title="Test", kind="execute")

        handler.update_tool_call_status(session, tool_call_id, "completed")

        assert session.tool_calls.calls[tool_call_id].status == "pending"

    def test_rejected_transition_is_logged(
        self, handler: ToolCallHandler, session: DomainSession
    ) -> None:
        """Отклонённый переход пишет warning.

        Молчаливый отказ однажды рассинхронизировал состояние с wire-историей:
        resume-путь слал клиенту completed, а состояние оставалось pending.
        """
        tool_call_id = handler.create_tool_call(session, title="Test", kind="execute")

        with structlog.testing.capture_logs() as logs:
            handler.update_tool_call_status(session, tool_call_id, "completed")

        entry = next(log for log in logs if log["event"] == "tool_call_status_transition_rejected")
        assert entry["log_level"] == "warning"
        assert entry["tool_call_id"] == tool_call_id
        assert entry["current_status"] == "pending"
        assert entry["requested_status"] == "completed"

    def test_update_with_content(self, handler: ToolCallHandler, session: DomainSession) -> None:
        """Проверяет обновление статуса с контентом."""
        tool_call_id = handler.create_tool_call(session, title="Test", kind="execute")

        content = [{"type": "content", "content": {"type": "text", "text": "Result"}}]
        handler.update_tool_call_status(session, tool_call_id, "in_progress", content=content)

        assert session.tool_calls.calls[tool_call_id].result.content == content

    def test_update_nonexistent_tool_call(
        self, handler: ToolCallHandler, session: DomainSession
    ) -> None:
        """Проверяет, что обновление несуществующего tool call игнорируется."""
        # Попытаемся обновить несуществующий tool call
        handler.update_tool_call_status(session, "nonexistent", "completed")

        # Ничего не должно случиться (no exception, no change)
        assert "nonexistent" not in session.tool_calls.calls


class TestToolCallHandlerCancellation:
    """Тесты отмены tool calls."""

    def test_cancel_all_active_tools(
        self,
        handler: ToolCallHandler,
        session: DomainSession,
    ) -> None:
        """Проверяет отмену всех активных tool calls."""
        # Создаем несколько tool calls в разных статусах
        id1 = handler.create_tool_call(session, title="Test1", kind="execute")
        id2 = handler.create_tool_call(session, title="Test2", kind="read")
        id3 = handler.create_tool_call(session, title="Test3", kind="delete")

        # Переводим в разные статусы
        handler.update_tool_call_status(session, id1, "in_progress")
        handler.update_tool_call_status(session, id2, "in_progress")
        handler.update_tool_call_status(session, id2, "completed")

        # Отмена работает тем же агрегатом, что и остальной turn-путь
        domain = session
        updates = handler.cancel_active_tools(domain, "test_session")

        # Должны быть отмены для id1 и id3 (in_progress и pending)
        assert len(updates) == 2
        assert domain.tool_calls.get(id1).status == ToolCallStatus.CANCELLED
        assert domain.tool_calls.get(id2).status == ToolCallStatus.COMPLETED  # не изменился
        assert domain.tool_calls.get(id3).status == ToolCallStatus.CANCELLED

    def test_cancel_ignores_completed_tools(
        self, handler: ToolCallHandler, session: DomainSession
    ) -> None:
        """Проверяет, что отмена игнорирует завершенные tool calls."""
        id1 = handler.create_tool_call(session, title="Test", kind="execute")
        handler.update_tool_call_status(session, id1, "in_progress")
        handler.update_tool_call_status(session, id1, "completed")

        domain = session
        updates = handler.cancel_active_tools(domain, "test_session")

        # Не должно быть notifications, так как tool call уже завершен
        assert len(updates) == 0
        assert domain.tool_calls.get(id1).status == ToolCallStatus.COMPLETED

    def test_cancel_empty_session(self, handler: ToolCallHandler, session: DomainSession) -> None:
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

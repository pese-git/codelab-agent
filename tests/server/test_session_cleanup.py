"""Тесты для проверки очистки незавершенных операций при переключении сессии.

Проверяет функцию _cleanup_session_state() из session.py для предотвращения
race conditions, утечек памяти и зависающих операций при session_load().
"""

from codelab.server.protocol.handlers.session import _cleanup_session_state
from codelab.server.protocol.state import (
    ActiveTurnState,
    PendingClientRequestState,
    SessionState,
    ToolCallState,
)


class TestSessionCleanup:
    """Тесты очистки состояния сессии при переключении."""

    def test_cleanup_clears_active_turn(self) -> None:
        """Проверяет, что активный turn обнуляется при очистке."""
        # Arrange
        session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        session.active_turn = ActiveTurnState(prompt_request_id="req_1", session_id="sess_1")

        # Act
        _cleanup_session_state(session)

        # Assert
        assert session.active_turn is None

    def test_cleanup_marks_active_turn_as_cancelled(self) -> None:
        """Проверяет, что active turn отмечается как cancelled перед очисткой."""
        # Arrange
        session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        active_turn = ActiveTurnState(prompt_request_id="req_1", session_id="sess_1")
        session.active_turn = active_turn

        # Act
        _cleanup_session_state(session)

        # Assert
        # После очистки active_turn должен быть None
        assert session.active_turn is None

    def test_cleanup_cancels_pending_tool_calls(self) -> None:
        """Проверяет, что pending tool calls отмечаются как cancelled."""
        # Arrange
        session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        session.tool_calls = {
            "call_1": ToolCallState(
                tool_call_id="call_1",
                title="Task 1",
                kind="other",
                status="pending",
            ),
            "call_2": ToolCallState(
                tool_call_id="call_2",
                title="Task 2",
                kind="other",
                status="in_progress",
            ),
            "call_3": ToolCallState(
                tool_call_id="call_3",
                title="Task 3",
                kind="other",
                status="completed",
            ),
        }

        # Act
        _cleanup_session_state(session)

        # Assert
        # Только pending должен стать cancelled
        assert session.tool_calls["call_1"].status == "cancelled"
        # in_progress и completed остаются без изменений
        assert session.tool_calls["call_2"].status == "in_progress"
        assert session.tool_calls["call_3"].status == "completed"

    def test_cleanup_adds_permission_request_to_cancelled_set(self) -> None:
        """Проверяет, что permission request ID добавляется в cancelled set."""
        # Arrange
        session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
            permission_request_id="perm_req_1",
        )

        # Act
        _cleanup_session_state(session)

        # Assert
        assert "perm_req_1" in session.cancelled_permission_requests

    def test_cleanup_adds_client_rpc_request_to_cancelled_set(self) -> None:
        """Проверяет, что client RPC request ID добавляется в cancelled set."""
        # Arrange
        session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        pending_request = PendingClientRequestState(
            request_id="rpc_req_1",
            kind="fs_read",
            tool_call_id="call_1",
            path="/tmp/file.txt",
        )
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
            pending_client_request=pending_request,
        )

        # Act
        _cleanup_session_state(session)

        # Assert
        assert "rpc_req_1" in session.cancelled_client_rpc_requests

    def test_cleanup_handles_both_permission_and_rpc_requests(self) -> None:
        """Проверяет, что обрабатываются и permission и RPC requests одновременно."""
        # Arrange
        session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        pending_request = PendingClientRequestState(
            request_id="rpc_req_1",
            kind="fs_write",
            tool_call_id="call_1",
            path="/tmp/file.txt",
        )
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
            permission_request_id="perm_req_1",
            pending_client_request=pending_request,
        )

        # Act
        _cleanup_session_state(session)

        # Assert
        assert "perm_req_1" in session.cancelled_permission_requests
        assert "rpc_req_1" in session.cancelled_client_rpc_requests
        assert session.active_turn is None

    def test_cleanup_handles_null_active_turn(self) -> None:
        """Проверяет безопасную обработку NULL active turn."""
        # Arrange
        session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        assert session.active_turn is None

        # Act & Assert (не должно быть исключений)
        _cleanup_session_state(session)
        assert session.active_turn is None

    def test_cleanup_handles_active_turn_without_permission_request(self) -> None:
        """Проверяет очистку active turn без permission request."""
        # Arrange
        session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1", session_id="sess_1", permission_request_id=None
        )
        initial_cancelled_perms = len(session.cancelled_permission_requests)

        # Act
        _cleanup_session_state(session)

        # Assert
        assert session.active_turn is None
        assert len(session.cancelled_permission_requests) == initial_cancelled_perms

    def test_cleanup_preserves_existing_cancelled_requests(self) -> None:
        """Проверяет, что очистка сохраняет уже отмененные requests."""
        # Arrange
        session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        session.cancelled_permission_requests.add("old_perm_1")
        session.cancelled_client_rpc_requests.add("old_rpc_1")

        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
            permission_request_id="new_perm_1",
        )
        pending_request = PendingClientRequestState(
            request_id="new_rpc_1",
            kind="fs_read",
            tool_call_id="call_1",
            path="/tmp/file.txt",
        )
        session.active_turn.pending_client_request = pending_request

        # Act
        _cleanup_session_state(session)

        # Assert
        assert "old_perm_1" in session.cancelled_permission_requests
        assert "new_perm_1" in session.cancelled_permission_requests
        assert "old_rpc_1" in session.cancelled_client_rpc_requests
        assert "new_rpc_1" in session.cancelled_client_rpc_requests

    def test_cleanup_comprehensive_scenario(self) -> None:
        """Полный сценарий очистки с активным turn и multiple tool calls."""
        # Arrange
        session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])

        # Добавляем несколько tool calls в разных состояниях
        session.tool_calls = {
            "call_pending_1": ToolCallState(
                tool_call_id="call_pending_1",
                title="Pending Task",
                kind="other",
                status="pending",
            ),
            "call_pending_2": ToolCallState(
                tool_call_id="call_pending_2",
                title="Another Pending",
                kind="execute",
                status="pending",
            ),
            "call_completed": ToolCallState(
                tool_call_id="call_completed",
                title="Completed Task",
                kind="other",
                status="completed",
            ),
        }

        # Активный turn с permission и RPC requests
        pending_request = PendingClientRequestState(
            request_id="rpc_req_1",
            kind="terminal",
            tool_call_id="call_pending_1",
            path="",
            terminal_id="term_1",
        )
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
            cancel_requested=False,
            permission_request_id="perm_req_1",
            permission_tool_call_id="call_pending_1",
            phase="running",
            pending_client_request=pending_request,
        )

        # Act
        _cleanup_session_state(session)

        # Assert
        # Active turn должен быть очищен
        assert session.active_turn is None

        # Все pending tool calls должны быть отмечены как cancelled
        assert session.tool_calls["call_pending_1"].status == "cancelled"
        assert session.tool_calls["call_pending_2"].status == "cancelled"

        # Completed остается без изменений
        assert session.tool_calls["call_completed"].status == "completed"

        # Cancelled requests должны быть зафиксированы
        assert "perm_req_1" in session.cancelled_permission_requests
        assert "rpc_req_1" in session.cancelled_client_rpc_requests

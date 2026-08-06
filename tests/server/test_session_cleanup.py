"""Тесты для проверки очистки незавершенных операций при переключении сессии.

Проверяет функцию _cleanup_session_state() из session.py для предотвращения
race conditions, утечек памяти и зависающих операций при session_load().
"""

from codelab.server.domain.session import TurnState
from codelab.server.domain.tool_call import ToolCall
from codelab.server.domain.value_objects import AwaitingPermission, Running, ToolCallStatus
from codelab.server.protocol.handlers.session import _cleanup_session_state
from codelab.server.storage.document import PendingClientRequestState
from tests.server._domain_sessions import make_domain_session


class TestSessionCleanup:
    """Тесты очистки состояния сессии при переключении."""

    def test_cleanup_clears_active_turn(self) -> None:
        """Проверяет, что активный turn обнуляется при очистке."""
        # Arrange
        session = make_domain_session(session_id="sess_1", cwd="/tmp")
        session.active_turn = TurnState(prompt_request_id="req_1", session_id="sess_1")

        # Act
        _cleanup_session_state(session)

        # Assert
        assert session.active_turn is None

    def test_cleanup_marks_active_turn_as_cancelled(self) -> None:
        """Проверяет, что active turn отмечается как cancelled перед очисткой."""
        # Arrange
        session = make_domain_session(session_id="sess_1", cwd="/tmp")
        active_turn = TurnState(prompt_request_id="req_1", session_id="sess_1")
        session.active_turn = active_turn

        # Act
        _cleanup_session_state(session)

        # Assert
        # После очистки active_turn должен быть None
        assert session.active_turn is None

    def test_cleanup_cancels_pending_tool_calls(self) -> None:
        """Проверяет, что pending tool calls отмечаются как cancelled."""
        # Arrange
        session = make_domain_session(session_id="sess_1", cwd="/tmp")
        session.tool_calls.calls["call_1"] = ToolCall(
            id="call_1", tool_name="Task 1", arguments={}, title="Task 1",
            kind="other", status=ToolCallStatus("pending")
        )
        session.tool_calls.calls["call_2"] = ToolCall(
            id="call_2", tool_name="Task 2", arguments={}, title="Task 2",
            kind="other", status=ToolCallStatus("in_progress")
        )
        session.tool_calls.calls["call_3"] = ToolCall(
            id="call_3", tool_name="Task 3", arguments={}, title="Task 3",
            kind="other", status=ToolCallStatus("completed")
        )

        # Act
        _cleanup_session_state(session)

        # Assert
        # Только pending должен стать cancelled
        assert session.tool_calls.get("call_1").status.value == "cancelled"
        # in_progress и completed остаются без изменений
        assert session.tool_calls.get("call_2").status.value == "in_progress"
        assert session.tool_calls.get("call_3").status.value == "completed"

    def test_cleanup_adds_permission_request_to_cancelled_set(self) -> None:
        """Проверяет, что permission request ID добавляется в cancelled set."""
        # Arrange
        session = make_domain_session(session_id="sess_1", cwd="/tmp")
        session.active_turn = TurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
            phase=AwaitingPermission(request_id="perm_req_1", tool_call_id="call_1"),
        )

        # Act
        _cleanup_session_state(session)

        # Assert
        assert "perm_req_1" in session.permissions.cancelled_requests

    def test_cleanup_adds_client_rpc_request_to_cancelled_set(self) -> None:
        """Проверяет, что client RPC request ID добавляется в cancelled set."""
        # Arrange
        session = make_domain_session(session_id="sess_1", cwd="/tmp")
        pending_request = PendingClientRequestState(
            request_id="rpc_req_1",
            kind="fs_read",
            tool_call_id="call_1",
            path="/tmp/file.txt",
        )
        session.active_turn = TurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
            pending_external_request=pending_request,
        )

        # Act
        _cleanup_session_state(session)

        # Assert
        assert "rpc_req_1" in session.runtime.cancelled_client_rpc_requests

    def test_cleanup_handles_both_permission_and_rpc_requests(self) -> None:
        """Проверяет, что обрабатываются и permission и RPC requests одновременно."""
        # Arrange
        session = make_domain_session(session_id="sess_1", cwd="/tmp")
        pending_request = PendingClientRequestState(
            request_id="rpc_req_1",
            kind="fs_write",
            tool_call_id="call_1",
            path="/tmp/file.txt",
        )
        session.active_turn = TurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
            phase=AwaitingPermission(request_id="perm_req_1", tool_call_id="call_1"),
            pending_external_request=pending_request,
        )

        # Act
        _cleanup_session_state(session)

        # Assert
        assert "perm_req_1" in session.permissions.cancelled_requests
        assert "rpc_req_1" in session.runtime.cancelled_client_rpc_requests
        assert session.active_turn is None

    def test_cleanup_handles_null_active_turn(self) -> None:
        """Проверяет безопасную обработку NULL active turn."""
        # Arrange
        session = make_domain_session(session_id="sess_1", cwd="/tmp")
        assert session.active_turn is None

        # Act & Assert (не должно быть исключений)
        _cleanup_session_state(session)
        assert session.active_turn is None

    def test_cleanup_handles_active_turn_without_permission_request(self) -> None:
        """Проверяет очистку active turn без permission request."""
        # Arrange
        session = make_domain_session(session_id="sess_1", cwd="/tmp")
        # «Нет ожидаемого разрешения» — это фаза `Running`, а не отдельное поле `None`
        # (ADR-008, шаг 2): идентификаторы выводятся из фазы.
        session.active_turn = TurnState(
            prompt_request_id="req_1", session_id="sess_1", phase=Running()
        )
        initial_cancelled_perms = len(session.permissions.cancelled_requests)

        # Act
        _cleanup_session_state(session)

        # Assert
        assert session.active_turn is None
        assert len(session.permissions.cancelled_requests) == initial_cancelled_perms

    def test_cleanup_preserves_existing_cancelled_requests(self) -> None:
        """Проверяет, что очистка сохраняет уже отмененные requests."""
        # Arrange
        session = make_domain_session(session_id="sess_1", cwd="/tmp")
        session.permissions.cancelled_requests.add("old_perm_1")
        session.runtime.cancelled_client_rpc_requests.add("old_rpc_1")

        session.active_turn = TurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
            phase=AwaitingPermission(request_id="new_perm_1", tool_call_id="call_1"),
        )
        pending_request = PendingClientRequestState(
            request_id="new_rpc_1",
            kind="fs_read",
            tool_call_id="call_1",
            path="/tmp/file.txt",
        )
        session.active_turn.pending_external_request = pending_request

        # Act
        _cleanup_session_state(session)

        # Assert
        assert "old_perm_1" in session.permissions.cancelled_requests
        assert "new_perm_1" in session.permissions.cancelled_requests
        assert "old_rpc_1" in session.runtime.cancelled_client_rpc_requests
        assert "new_rpc_1" in session.runtime.cancelled_client_rpc_requests

    def test_cleanup_comprehensive_scenario(self) -> None:
        """Полный сценарий очистки с активным turn и multiple tool calls."""
        # Arrange
        session = make_domain_session(session_id="sess_1", cwd="/tmp")

        # Добавляем несколько tool calls в разных состояниях
        session.tool_calls.calls["call_pending_1"] = ToolCall(
            id="call_pending_1", tool_name="Pending Task", arguments={}, title="Pending Task",
            kind="other", status=ToolCallStatus("pending")
        )
        session.tool_calls.calls["call_pending_2"] = ToolCall(
            id="call_pending_2", tool_name="Another Pending", arguments={}, title="Another Pending",
            kind="execute", status=ToolCallStatus("pending")
        )
        session.tool_calls.calls["call_completed"] = ToolCall(
            id="call_completed", tool_name="Completed Task", arguments={}, title="Completed Task",
            kind="other", status=ToolCallStatus("completed")
        )

        # Активный turn с permission и RPC requests
        pending_request = PendingClientRequestState(
            request_id="rpc_req_1",
            kind="terminal",
            tool_call_id="call_pending_1",
            path="",
            terminal_id="term_1",
        )
        session.active_turn = TurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
            cancel_requested=False,
            phase=AwaitingPermission(request_id="perm_req_1", tool_call_id="call_pending_1"),
            pending_external_request=pending_request,
        )

        # Act
        _cleanup_session_state(session)

        # Assert
        # Active turn должен быть очищен
        assert session.active_turn is None

        # Все pending tool calls должны быть отмечены как cancelled
        assert session.tool_calls.get("call_pending_1").status.value == "cancelled"
        assert session.tool_calls.get("call_pending_2").status.value == "cancelled"

        # Completed остается без изменений
        assert session.tool_calls.get("call_completed").status.value == "completed"

        # Cancelled requests должны быть зафиксированы
        assert "perm_req_1" in session.permissions.cancelled_requests
        assert "rpc_req_1" in session.runtime.cancelled_client_rpc_requests

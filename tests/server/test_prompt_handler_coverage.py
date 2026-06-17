"""Тесты для непокрытых веток обработчика prompt-turn.

Покрывают guard-ветки в build_fs_client_request, build_terminal_client_request
и обработку ответов на agent->client RPC для терминала.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from codelab.server.protocol.handlers.prompt import (
    build_fs_client_request,
    build_terminal_client_request,
    resolve_pending_client_rpc_response_impl,
)
from codelab.server.protocol.state import (
    ActiveTurnState,
    PendingClientRequestState,
    PromptDirectives,
    SessionState,
)


class TestBuildFsClientRequestGuards:
    """Тесты guard-веток в build_fs_client_request."""

    @pytest.fixture
    def session(self) -> SessionState:
        """Сессия с активным turn."""
        return SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            active_turn=ActiveTurnState(prompt_request_id="req_0", session_id="sess_1"),
        )

    def test_fs_read_invalid_path_returns_none(self, session: SessionState) -> None:
        """При пустом пути чтения возвращается None."""
        directives = PromptDirectives(fs_read_path="   ")

        result = build_fs_client_request(
            session=session,
            session_id="sess_1",
            directives=directives,
        )

        assert result is None

    def test_fs_write_invalid_path_returns_none(self, session: SessionState) -> None:
        """При пустом пути записи возвращается None."""
        directives = PromptDirectives(
            fs_write_path="   ",
            fs_write_content="data",
        )

        result = build_fs_client_request(
            session=session,
            session_id="sess_1",
            directives=directives,
        )

        assert result is None

    def test_fs_read_request_without_id_returns_none(
        self,
        session: SessionState,
    ) -> None:
        """Если ACPMessage.request для fs/read не получил id, возвращается None."""
        directives = PromptDirectives(fs_read_path="file.txt")

        with patch(
            "codelab.server.protocol.handlers.prompt.ACPMessage.request",
            return_value=MagicMock(id=None),
        ):
            result = build_fs_client_request(
                session=session,
                session_id="sess_1",
                directives=directives,
            )

        assert result is None

    def test_fs_write_request_without_id_returns_none(
        self,
        session: SessionState,
    ) -> None:
        """Если ACPMessage.request для fs/write не получил id, возвращается None."""
        directives = PromptDirectives(
            fs_write_path="file.txt",
            fs_write_content="data",
        )

        with patch(
            "codelab.server.protocol.handlers.prompt.ACPMessage.request",
            return_value=MagicMock(id=None),
        ):
            result = build_fs_client_request(
                session=session,
                session_id="sess_1",
                directives=directives,
            )

        assert result is None


class TestBuildTerminalClientRequestGuards:
    """Тесты guard-веток в build_terminal_client_request."""

    @pytest.fixture
    def session(self) -> SessionState:
        """Сессия с активным turn."""
        return SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            active_turn=ActiveTurnState(prompt_request_id="req_0", session_id="sess_1"),
        )

    def test_terminal_create_request_without_id_returns_none(
        self,
        session: SessionState,
    ) -> None:
        """Если ACPMessage.request для terminal/create не получил id, возвращается None."""
        directives = PromptDirectives(terminal_command="ls")

        with patch(
            "codelab.server.protocol.handlers.prompt.ACPMessage.request",
            return_value=MagicMock(id=None),
        ):
            result = build_terminal_client_request(
                session=session,
                session_id="sess_1",
                directives=directives,
            )

        assert result is None


class TestResolvePendingClientRpcTerminalGuards:
    """Тесты guard-веток terminal_* в resolve_pending_client_rpc_response_impl."""

    @pytest.fixture
    def session(self) -> SessionState:
        """Сессия с активным turn."""
        sess = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            active_turn=ActiveTurnState(
                prompt_request_id="req_0",
                session_id="sess_1",
            ),
        )
        return sess

    def test_terminal_create_output_request_without_id_returns_none(
        self,
        session: SessionState,
    ) -> None:
        """При отсутствии id у terminal/output запроса возвращается None."""
        session.active_turn.pending_client_request = PendingClientRequestState(
            request_id="req_create",
            kind="terminal_create",
            tool_call_id="call_001",
            path="ls",
        )

        with patch(
            "codelab.server.protocol.handlers.prompt.ACPMessage.request",
            return_value=MagicMock(id=None),
        ):
            result = resolve_pending_client_rpc_response_impl(
                session=session,
                request_id="req_create",
                result={"terminalId": "term_1"},
                error=None,
            )

        assert result is None

    def test_terminal_output_missing_terminal_id_returns_none(
        self,
        session: SessionState,
    ) -> None:
        """Если у pending terminal_output отсутствует terminal_id, возвращается None."""
        session.active_turn.pending_client_request = PendingClientRequestState(
            request_id="req_output",
            kind="terminal_output",
            tool_call_id="call_001",
            path="ls",
            terminal_id=None,
        )

        result = resolve_pending_client_rpc_response_impl(
            session=session,
            request_id="req_output",
            result={"output": "hello"},
            error=None,
        )

        assert result is None

    def test_terminal_output_invalid_exit_code_type_fails(
        self,
        session: SessionState,
    ) -> None:
        """Некорректный тип exitCode в terminal/output завершает turn с ошибкой."""
        session.active_turn.pending_client_request = PendingClientRequestState(
            request_id="req_output",
            kind="terminal_output",
            tool_call_id="call_001",
            path="ls",
            terminal_id="term_1",
        )

        result = resolve_pending_client_rpc_response_impl(
            session=session,
            request_id="req_output",
            result={
                "output": "out",
                "exitStatus": {"exitCode": "not_int", "signal": None},
            },
            error=None,
        )

        assert result is not None
        assert any(
            n.params.get("update", {}).get("status") == "failed"
            for n in result.notifications
        )

    def test_terminal_output_invalid_signal_type_fails(
        self,
        session: SessionState,
    ) -> None:
        """Некорректный тип signal в terminal/output завершает turn с ошибкой."""
        session.active_turn.pending_client_request = PendingClientRequestState(
            request_id="req_output",
            kind="terminal_output",
            tool_call_id="call_001",
            path="ls",
            terminal_id="term_1",
        )

        result = resolve_pending_client_rpc_response_impl(
            session=session,
            request_id="req_output",
            result={
                "output": "out",
                "exitStatus": {"exitCode": 0, "signal": 123},
            },
            error=None,
        )

        assert result is not None
        assert any(
            n.params.get("update", {}).get("status") == "failed"
            for n in result.notifications
        )

    def test_terminal_output_release_request_without_id_returns_none(
        self,
        session: SessionState,
    ) -> None:
        """При отсутствии id у release-запроса после terminal/output возвращается None."""
        session.active_turn.pending_client_request = PendingClientRequestState(
            request_id="req_output",
            kind="terminal_output",
            tool_call_id="call_001",
            path="ls",
            terminal_id="term_1",
        )

        with patch(
            "codelab.server.protocol.handlers.prompt.ACPMessage.request",
            return_value=MagicMock(id=None),
        ):
            result = resolve_pending_client_rpc_response_impl(
                session=session,
                request_id="req_output",
                result={
                    "output": "out",
                    "exitStatus": {"exitCode": 0, "signal": None},
                },
                error=None,
            )

        assert result is None

    def test_terminal_output_wait_request_without_id_returns_none(
        self,
        session: SessionState,
    ) -> None:
        """При отсутствии id у wait-запроса после terminal/output возвращается None."""
        session.active_turn.pending_client_request = PendingClientRequestState(
            request_id="req_output",
            kind="terminal_output",
            tool_call_id="call_001",
            path="ls",
            terminal_id="term_1",
        )

        with patch(
            "codelab.server.protocol.handlers.prompt.ACPMessage.request",
            return_value=MagicMock(id=None),
        ):
            result = resolve_pending_client_rpc_response_impl(
                session=session,
                request_id="req_output",
                result={"output": "out"},
                error=None,
            )

        assert result is None

    def test_terminal_wait_for_exit_missing_terminal_id_returns_none(
        self,
        session: SessionState,
    ) -> None:
        """При отсутствии terminal_id у terminal_wait_for_exit возвращается None."""
        session.active_turn.pending_client_request = PendingClientRequestState(
            request_id="req_wait",
            kind="terminal_wait_for_exit",
            tool_call_id="call_001",
            path="ls",
            terminal_id=None,
        )

        result = resolve_pending_client_rpc_response_impl(
            session=session,
            request_id="req_wait",
            result={"exitCode": 0, "signal": None},
            error=None,
        )

        assert result is None

    def test_terminal_wait_for_exit_non_dict_result_fails(
        self,
        session: SessionState,
    ) -> None:
        """Некорректный result при terminal_wait_for_exit завершает turn с ошибкой."""
        session.active_turn.pending_client_request = PendingClientRequestState(
            request_id="req_wait",
            kind="terminal_wait_for_exit",
            tool_call_id="call_001",
            path="ls",
            terminal_id="term_1",
        )

        result = resolve_pending_client_rpc_response_impl(
            session=session,
            request_id="req_wait",
            result="bad",
            error=None,
        )

        assert result is not None
        assert any(
            n.params.get("update", {}).get("status") == "failed"
            for n in result.notifications
        )

    def test_terminal_wait_for_exit_valid_signal(
        self,
        session: SessionState,
    ) -> None:
        """Корректный signal при terminal_wait_for_exit сохраняется в pending."""
        session.active_turn.pending_client_request = PendingClientRequestState(
            request_id="req_wait",
            kind="terminal_wait_for_exit",
            tool_call_id="call_001",
            path="ls",
            terminal_id="term_1",
            terminal_output="out",
        )

        result = resolve_pending_client_rpc_response_impl(
            session=session,
            request_id="req_wait",
            result={"exitCode": 0, "signal": "SIGTERM"},
            error=None,
        )

        assert result is not None
        assert any(
            n.method == "terminal/release"
            for n in result.notifications
        )
        next_pending = session.active_turn.pending_client_request
        assert next_pending is not None
        assert next_pending.terminal_signal == "SIGTERM"

    def test_terminal_wait_for_exit_release_request_without_id_returns_none(
        self,
        session: SessionState,
    ) -> None:
        """При отсутствии id у release-запроса после wait_for_exit возвращается None."""
        session.active_turn.pending_client_request = PendingClientRequestState(
            request_id="req_wait",
            kind="terminal_wait_for_exit",
            tool_call_id="call_001",
            path="ls",
            terminal_id="term_1",
        )

        with patch(
            "codelab.server.protocol.handlers.prompt.ACPMessage.request",
            return_value=MagicMock(id=None),
        ):
            result = resolve_pending_client_rpc_response_impl(
                session=session,
                request_id="req_wait",
                result={"exitCode": 0, "signal": None},
                error=None,
            )

        assert result is None

    def test_terminal_release_missing_terminal_id_returns_none(
        self,
        session: SessionState,
    ) -> None:
        """При отсутствии terminal_id у terminal_release возвращается None."""
        session.active_turn.pending_client_request = PendingClientRequestState(
            request_id="req_release",
            kind="terminal_release",
            tool_call_id="call_001",
            path="ls",
            terminal_id=None,
        )

        result = resolve_pending_client_rpc_response_impl(
            session=session,
            request_id="req_release",
            result={},
            error=None,
        )

        assert result is None

    def test_terminal_release_non_dict_result_fails(
        self,
        session: SessionState,
    ) -> None:
        """Некорректный result при terminal_release завершает turn с ошибкой."""
        session.active_turn.pending_client_request = PendingClientRequestState(
            request_id="req_release",
            kind="terminal_release",
            tool_call_id="call_001",
            path="ls",
            terminal_id="term_1",
            terminal_output="out",
            terminal_exit_code=0,
        )

        result = resolve_pending_client_rpc_response_impl(
            session=session,
            request_id="req_release",
            result="bad",
            error=None,
        )

        assert result is not None
        assert any(
            n.params.get("update", {}).get("status") == "failed"
            for n in result.notifications
        )

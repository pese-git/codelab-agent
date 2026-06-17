"""Дополнительные тесты покрытия для ClientRPCHandler.

Покрывает ранее непокрытые ветви: неизвестный kind в can_use_fs_rpc,
невалидные пути и отсутствующий request.id при подготовке RPC-запросов,
а также успешные сценарии обработки ответов клиента.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codelab.server.protocol.handlers.client_rpc_handler import ClientRPCHandler
from codelab.server.protocol.state import (
    ActiveTurnState,
    ClientRuntimeCapabilities,
    PendingClientRequestState,
    PromptDirectives,
    SessionState,
    ToolCallState,
)


@pytest.fixture
def handler() -> ClientRPCHandler:
    """Фикстура для создания ClientRPCHandler."""
    return ClientRPCHandler()


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


@pytest.fixture
def directives() -> PromptDirectives:
    """Фикстура для создания базовых directives."""
    return PromptDirectives()


class TestClientRPCHandlerEdgeCases:
    """Тесты для непокрытых граничных случаев."""

    async def test_can_use_fs_rpc_unknown_kind_returns_false(
        self,
        handler: ClientRPCHandler,
        session: SessionState,
    ) -> None:
        """Проверяет, что неизвестный kind возвращает False."""
        assert handler.can_use_fs_rpc(session, "unknown") is False

    async def test_prepare_fs_read_request_returns_none_when_request_id_missing(
        self,
        handler: ClientRPCHandler,
        session: SessionState,
        directives: PromptDirectives,
    ) -> None:
        """Проверяет, что prepare_fs_read_request возвращает None без request.id."""
        directives.fs_read_path = "/tmp/file.txt"

        request_mock = MagicMock()
        request_mock.id = None
        with patch(
            "codelab.server.protocol.handlers.client_rpc_handler.ACPMessage.request",
            return_value=request_mock,
        ):
            prepared = handler.prepare_fs_read_request(session, "sess_1", directives)

        assert prepared is None

    async def test_prepare_fs_write_request_returns_none_for_invalid_path(
        self,
        handler: ClientRPCHandler,
        session: SessionState,
        directives: PromptDirectives,
    ) -> None:
        """Проверяет, что невалидный путь возвращает None для fs_write."""
        directives.fs_write_path = ""
        directives.fs_write_content = "content"

        prepared = handler.prepare_fs_write_request(session, "sess_1", directives)

        assert prepared is None

    async def test_prepare_fs_write_request_returns_none_when_request_id_missing(
        self,
        handler: ClientRPCHandler,
        session: SessionState,
        directives: PromptDirectives,
    ) -> None:
        """Проверяет, что prepare_fs_write_request возвращает None без request.id."""
        directives.fs_write_path = "/tmp/file.txt"
        directives.fs_write_content = "content"

        request_mock = AsyncMock()
        request_mock.id = None
        with patch(
            "codelab.server.protocol.handlers.client_rpc_handler.ACPMessage.request",
            return_value=request_mock,
        ):
            prepared = handler.prepare_fs_write_request(session, "sess_1", directives)

        assert prepared is None

    async def test_prepare_terminal_request_returns_none_when_request_id_missing(
        self,
        handler: ClientRPCHandler,
        session: SessionState,
        directives: PromptDirectives,
    ) -> None:
        """Проверяет, что prepare_terminal_request возвращает None без request.id."""
        directives.terminal_command = "ls -la"

        request_mock = AsyncMock()
        request_mock.id = None
        with patch(
            "codelab.server.protocol.handlers.client_rpc_handler.ACPMessage.request",
            return_value=request_mock,
        ):
            prepared = handler.prepare_terminal_request(session, "sess_1", directives)

        assert prepared is None


class TestClientRPCHandlerResponseSuccess:
    """Тесты успешной обработки ответов на agent->client RPC запросы."""

    def _setup_active_turn(
        self,
        session: SessionState,
        kind: str,
        path: str = "/tmp/file.txt",
    ) -> PendingClientRequestState:
        """Создает active_turn с pending запросом и in_progress tool call."""
        tool_call_id = "call_001"
        tool_kind = "read" if kind == "fs_read" else "edit" if kind == "fs_write" else "execute"
        session.tool_calls[tool_call_id] = ToolCallState(
            tool_call_id=tool_call_id,
            title="Test tool call",
            kind=tool_kind,
            status="in_progress",
        )
        pending = PendingClientRequestState(
            request_id="req_1",
            kind=kind,
            tool_call_id=tool_call_id,
            path=path,
        )
        session.active_turn = ActiveTurnState(
            prompt_request_id="prompt_1",
            session_id=session.session_id,
            pending_client_request=pending,
        )
        return pending

    async def test_handle_response_fs_read_success(
        self,
        handler: ClientRPCHandler,
        session: SessionState,
    ) -> None:
        """Проверяет успешную обработку fs_read response с валидным content."""
        self._setup_active_turn(session, "fs_read")

        updates = handler.handle_pending_response(
            session,
            session.session_id,
            "fs_read",
            {"content": "file data"},
            None,
        )

        assert len(updates) == 1
        assert updates[0].params["update"]["status"] == "completed"
        assert session.tool_calls["call_001"].status == "completed"

    async def test_handle_response_fs_read_invalid_format(
        self,
        handler: ClientRPCHandler,
        session: SessionState,
    ) -> None:
        """Проверяет обработку fs_read response без строкового content."""
        self._setup_active_turn(session, "fs_read")

        updates = handler.handle_pending_response(
            session,
            session.session_id,
            "fs_read",
            {"content": 123},
            None,
        )

        assert len(updates) == 1
        assert updates[0].params["update"]["status"] == "failed"
        assert session.tool_calls["call_001"].status == "failed"

    async def test_handle_response_fs_read_non_dict_result(
        self,
        handler: ClientRPCHandler,
        session: SessionState,
    ) -> None:
        """Проверяет обработку fs_read response с невалидным типом result."""
        self._setup_active_turn(session, "fs_read")

        updates = handler.handle_pending_response(
            session,
            session.session_id,
            "fs_read",
            "not a dict",
            None,
        )

        assert len(updates) == 1
        assert updates[0].params["update"]["status"] == "failed"

    async def test_handle_response_fs_write_success(
        self,
        handler: ClientRPCHandler,
        session: SessionState,
    ) -> None:
        """Проверяет успешную обработку fs_write response."""
        self._setup_active_turn(session, "fs_write")

        updates = handler.handle_pending_response(
            session,
            session.session_id,
            "fs_write",
            {"ok": True},
            None,
        )

        assert len(updates) == 1
        assert updates[0].params["update"]["status"] == "completed"
        assert session.tool_calls["call_001"].status == "completed"

    async def test_handle_response_fs_write_invalid_format(
        self,
        handler: ClientRPCHandler,
        session: SessionState,
    ) -> None:
        """Проверяет обработку fs_write response с невалидным типом result."""
        self._setup_active_turn(session, "fs_write")

        updates = handler.handle_pending_response(
            session,
            session.session_id,
            "fs_write",
            "not a dict",
            None,
        )

        assert len(updates) == 1
        assert updates[0].params["update"]["status"] == "failed"
        assert session.tool_calls["call_001"].status == "failed"

    async def test_handle_response_terminal_create_with_output(
        self,
        handler: ClientRPCHandler,
        session: SessionState,
    ) -> None:
        """Проверяет успешную обработку terminal_create response с output."""
        self._setup_active_turn(session, "terminal_create", path="ls -la")

        updates = handler.handle_pending_response(
            session,
            session.session_id,
            "terminal_create",
            {"output": "line1\nline2"},
            None,
        )

        assert len(updates) == 1
        update = updates[0].params["update"]
        assert update["status"] == "completed"
        assert update["content"][0]["content"]["text"] == "line1\nline2"
        assert session.tool_calls["call_001"].status == "completed"

    async def test_handle_response_terminal_create_without_output(
        self,
        handler: ClientRPCHandler,
        session: SessionState,
    ) -> None:
        """Проверяет обработку terminal_create response без поля output."""
        self._setup_active_turn(session, "terminal_create", path="pwd")

        updates = handler.handle_pending_response(
            session,
            session.session_id,
            "terminal_create",
            {},
            None,
        )

        assert len(updates) == 1
        update = updates[0].params["update"]
        assert update["status"] == "completed"
        assert update["content"][0]["content"]["text"] == "Terminal command executed"

    async def test_handle_response_terminal_create_non_dict_result(
        self,
        handler: ClientRPCHandler,
        session: SessionState,
    ) -> None:
        """Проверяет обработку terminal_create response с невалидным типом result."""
        self._setup_active_turn(session, "terminal_create", path="whoami")

        updates = handler.handle_pending_response(
            session,
            session.session_id,
            "terminal_create",
            None,
            None,
        )

        assert len(updates) == 1
        update = updates[0].params["update"]
        assert update["status"] == "completed"
        assert update["content"][0]["content"]["text"] == "Terminal command executed"

    async def test_handle_response_unknown_kind_returns_empty(
        self,
        handler: ClientRPCHandler,
        session: SessionState,
    ) -> None:
        """Проверяет, что неизвестный kind возвращает пустой список notifications."""
        self._setup_active_turn(session, "terminal_create")

        updates = handler.handle_pending_response(
            session,
            session.session_id,
            "unknown_kind",
            {"output": "ignored"},
            None,
        )

        assert updates == []

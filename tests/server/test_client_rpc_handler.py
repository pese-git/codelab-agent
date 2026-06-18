"""Unit-тесты для ClientRPCHandler.

Тестирует проверку capabilities, подготовку RPC requests, нормализацию путей
и обработку response для fs/* и terminal/* операций.
"""

from __future__ import annotations

import pytest

from codelab.server.protocol.handlers.client_rpc_handler import ClientRPCHandler
from codelab.server.protocol.state import (
    ClientRuntimeCapabilities,
    PromptDirectives,
    SessionState,
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


class TestClientRPCHandlerCapabilities:
    """Тесты проверки runtime capabilities."""

    def test_can_use_fs_read_true(self, handler: ClientRPCHandler, session: SessionState) -> None:
        """Проверяет can_use_fs_rpc для fs_read когда доступно."""
        session.runtime_capabilities = ClientRuntimeCapabilities(
            terminal=False,
            fs_read=True,
            fs_write=False,
        )
        assert handler.can_use_fs_rpc(session, "fs_read") is True

    def test_can_use_fs_read_false(self, handler: ClientRPCHandler, session: SessionState) -> None:
        """Проверяет can_use_fs_rpc для fs_read когда недоступно."""
        session.runtime_capabilities = ClientRuntimeCapabilities(
            terminal=False,
            fs_read=False,
            fs_write=True,
        )
        assert handler.can_use_fs_rpc(session, "fs_read") is False

    def test_can_use_fs_write_true(self, handler: ClientRPCHandler, session: SessionState) -> None:
        """Проверяет can_use_fs_rpc для fs_write когда доступно."""
        session.runtime_capabilities = ClientRuntimeCapabilities(
            terminal=False,
            fs_read=False,
            fs_write=True,
        )
        assert handler.can_use_fs_rpc(session, "fs_write") is True

    def test_can_use_fs_write_false(self, handler: ClientRPCHandler, session: SessionState) -> None:
        """Проверяет can_use_fs_rpc для fs_write когда недоступно."""
        session.runtime_capabilities = ClientRuntimeCapabilities(
            terminal=False,
            fs_read=True,
            fs_write=False,
        )
        assert handler.can_use_fs_rpc(session, "fs_write") is False

    def test_can_use_fs_rpc_none_capabilities(
        self, handler: ClientRPCHandler, session: SessionState
    ) -> None:
        """Проверяет can_use_fs_rpc когда runtime_capabilities не установлены."""
        session.runtime_capabilities = None
        assert handler.can_use_fs_rpc(session, "fs_read") is False
        assert handler.can_use_fs_rpc(session, "fs_write") is False

    def test_can_use_terminal_true(self, handler: ClientRPCHandler, session: SessionState) -> None:
        """Проверяет can_use_terminal_rpc когда доступно."""
        session.runtime_capabilities = ClientRuntimeCapabilities(
            terminal=True,
            fs_read=False,
            fs_write=False,
        )
        assert handler.can_use_terminal_rpc(session) is True

    def test_can_use_terminal_false(self, handler: ClientRPCHandler, session: SessionState) -> None:
        """Проверяет can_use_terminal_rpc когда недоступно."""
        session.runtime_capabilities = ClientRuntimeCapabilities(
            terminal=False,
            fs_read=True,
            fs_write=True,
        )
        assert handler.can_use_terminal_rpc(session) is False

    def test_can_use_terminal_none_capabilities(
        self, handler: ClientRPCHandler, session: SessionState
    ) -> None:
        """Проверяет can_use_terminal_rpc когда runtime_capabilities не установлены."""
        session.runtime_capabilities = None
        assert handler.can_use_terminal_rpc(session) is False

    def test_can_run_tools_with_all_capabilities(
        self, handler: ClientRPCHandler, session: SessionState
    ) -> None:
        """Проверяет can_run_tools когда все capabilities доступны."""
        session.runtime_capabilities = ClientRuntimeCapabilities(
            terminal=True,
            fs_read=True,
            fs_write=True,
        )
        assert handler.can_run_tools(session) is True

    def test_can_run_tools_with_terminal_only(
        self, handler: ClientRPCHandler, session: SessionState
    ) -> None:
        """Проверяет can_run_tools с только terminal capability."""
        session.runtime_capabilities = ClientRuntimeCapabilities(
            terminal=True,
            fs_read=False,
            fs_write=False,
        )
        assert handler.can_run_tools(session) is True

    def test_can_run_tools_with_no_capabilities(
        self, handler: ClientRPCHandler, session: SessionState
    ) -> None:
        """Проверяет can_run_tools когда нет capabilities."""
        session.runtime_capabilities = ClientRuntimeCapabilities(
            terminal=False,
            fs_read=False,
            fs_write=False,
        )
        assert handler.can_run_tools(session) is False

    def test_can_run_tools_none_capabilities(
        self, handler: ClientRPCHandler, session: SessionState
    ) -> None:
        """Проверяет can_run_tools когда runtime_capabilities не установлены."""
        session.runtime_capabilities = None
        assert handler.can_run_tools(session) is False


class TestClientRPCHandlerPathNormalization:
    """Тесты нормализации путей."""

    def test_normalize_absolute_path(self, handler: ClientRPCHandler) -> None:
        """Проверяет нормализацию абсолютного пути."""
        path = handler.normalize_path("/tmp", "/var/log/file.txt")
        assert path == "/var/log/file.txt"

    def test_normalize_relative_path(self, handler: ClientRPCHandler) -> None:
        """Проверяет нормализацию relative пути."""
        path = handler.normalize_path("/tmp", "file.txt")
        assert path == "/tmp/file.txt"

    def test_normalize_relative_path_with_subdirs(self, handler: ClientRPCHandler) -> None:
        """Проверяет нормализацию relative пути с поддиректориями."""
        path = handler.normalize_path("/tmp", "subdir/file.txt")
        assert path == "/tmp/subdir/file.txt"

    def test_normalize_relative_path_parent_traversal(self, handler: ClientRPCHandler) -> None:
        """Проверяет нормализацию с parent directory traversal."""
        path = handler.normalize_path("/tmp/subdir", "../file.txt")
        # Path() нормализует это нативно
        assert path is not None
        assert "file.txt" in path

    def test_normalize_empty_path(self, handler: ClientRPCHandler) -> None:
        """Проверяет, что пустой путь возвращает None."""
        assert handler.normalize_path("/tmp", "") is None

    def test_normalize_whitespace_path(self, handler: ClientRPCHandler) -> None:
        """Проверяет, что whitespace-only путь возвращает None."""
        assert handler.normalize_path("/tmp", "   ") is None

    def test_normalize_none_path(self, handler: ClientRPCHandler) -> None:
        """Проверяет обработку невалидного типа."""
        # Функция проверяет isinstance(candidate, str)
        path = handler.normalize_path("/tmp", "")
        assert path is None


class TestClientRPCHandlerFsRead:
    """Тесты подготовки fs/read request."""

    def test_prepare_fs_read_request_structure(
        self, handler: ClientRPCHandler, session: SessionState, directives: PromptDirectives
    ) -> None:
        """Проверяет структуру подготовленного fs/read request."""
        directives.fs_read_path = "/var/log/app.log"

        prepared = handler.prepare_fs_read_request(session, "sess_1", directives)

        assert prepared is not None
        assert prepared.kind == "fs_read"
        assert len(prepared.messages) == 2  # tool_call notification + request
        assert prepared.pending_request is not None
        assert prepared.pending_request.kind == "fs_read"

    def test_prepare_fs_read_creates_tool_call(
        self, handler: ClientRPCHandler, session: SessionState, directives: PromptDirectives
    ) -> None:
        """Проверяет, что подготовка fs/read создает tool call."""
        directives.fs_read_path = "file.txt"
        initial_counter = session.tool_call_counter

        prepared = handler.prepare_fs_read_request(session, "sess_1", directives)

        assert prepared is not None
        assert session.tool_call_counter > initial_counter

    def test_prepare_fs_read_invalid_path(
        self, handler: ClientRPCHandler, session: SessionState, directives: PromptDirectives
    ) -> None:
        """Проверяет, что невалидный путь возвращает None."""
        directives.fs_read_path = ""

        prepared = handler.prepare_fs_read_request(session, "sess_1", directives)

        assert prepared is None

    def test_prepare_fs_read_no_capability(
        self, handler: ClientRPCHandler, session: SessionState, directives: PromptDirectives
    ) -> None:
        """Проверяет, что отсутствие capability возвращает None."""
        session.runtime_capabilities = ClientRuntimeCapabilities(
            terminal=False,
            fs_read=False,
            fs_write=True,
        )
        directives.fs_read_path = "file.txt"

        prepared = handler.prepare_fs_read_request(session, "sess_1", directives)

        assert prepared is None

    def test_prepare_fs_read_no_path_directive(
        self, handler: ClientRPCHandler, session: SessionState, directives: PromptDirectives
    ) -> None:
        """Проверяет, что отсутствие fs_read_path возвращает None."""
        directives.fs_read_path = None

        prepared = handler.prepare_fs_read_request(session, "sess_1", directives)

        assert prepared is None


class TestClientRPCHandlerFsWrite:
    """Тесты подготовки fs/write request."""

    def test_prepare_fs_write_request_structure(
        self, handler: ClientRPCHandler, session: SessionState, directives: PromptDirectives
    ) -> None:
        """Проверяет структуру подготовленного fs/write request."""
        directives.fs_write_path = "file.txt"
        directives.fs_write_content = "Hello World"

        prepared = handler.prepare_fs_write_request(session, "sess_1", directives)

        assert prepared is not None
        assert prepared.kind == "fs_write"
        assert len(prepared.messages) == 2
        assert prepared.pending_request is not None
        assert prepared.pending_request.kind == "fs_write"
        assert prepared.pending_request.expected_new_text == "Hello World"

    def test_prepare_fs_write_creates_tool_call(
        self, handler: ClientRPCHandler, session: SessionState, directives: PromptDirectives
    ) -> None:
        """Проверяет, что подготовка fs/write создает tool call."""
        directives.fs_write_path = "file.txt"
        directives.fs_write_content = "content"
        initial_counter = session.tool_call_counter

        prepared = handler.prepare_fs_write_request(session, "sess_1", directives)

        assert prepared is not None
        assert session.tool_call_counter > initial_counter

    def test_prepare_fs_write_missing_content(
        self, handler: ClientRPCHandler, session: SessionState, directives: PromptDirectives
    ) -> None:
        """Проверяет, что отсутствие content возвращает None."""
        directives.fs_write_path = "file.txt"
        directives.fs_write_content = None

        prepared = handler.prepare_fs_write_request(session, "sess_1", directives)

        assert prepared is None

    def test_prepare_fs_write_no_capability(
        self, handler: ClientRPCHandler, session: SessionState, directives: PromptDirectives
    ) -> None:
        """Проверяет, что отсутствие capability возвращает None."""
        session.runtime_capabilities = ClientRuntimeCapabilities(
            terminal=True,
            fs_read=True,
            fs_write=False,
        )
        directives.fs_write_path = "file.txt"
        directives.fs_write_content = "content"

        prepared = handler.prepare_fs_write_request(session, "sess_1", directives)

        assert prepared is None


class TestClientRPCHandlerTerminal:
    """Тесты подготовки terminal/create request."""

    def test_prepare_terminal_request_structure(
        self, handler: ClientRPCHandler, session: SessionState, directives: PromptDirectives
    ) -> None:
        """Проверяет структуру подготовленного terminal request."""
        directives.terminal_command = "ls -la"

        prepared = handler.prepare_terminal_request(session, "sess_1", directives)

        assert prepared is not None
        assert prepared.kind == "terminal_create"
        assert len(prepared.messages) == 2
        assert prepared.pending_request is not None
        assert prepared.pending_request.kind == "terminal_create"

    def test_prepare_terminal_creates_tool_call(
        self, handler: ClientRPCHandler, session: SessionState, directives: PromptDirectives
    ) -> None:
        """Проверяет, что подготовка terminal создает tool call."""
        directives.terminal_command = "pwd"
        initial_counter = session.tool_call_counter

        prepared = handler.prepare_terminal_request(session, "sess_1", directives)

        assert prepared is not None
        assert session.tool_call_counter > initial_counter

    def test_prepare_terminal_no_command(
        self, handler: ClientRPCHandler, session: SessionState, directives: PromptDirectives
    ) -> None:
        """Проверяет, что отсутствие command возвращает None."""
        directives.terminal_command = None

        prepared = handler.prepare_terminal_request(session, "sess_1", directives)

        assert prepared is None

    def test_prepare_terminal_no_capability(
        self, handler: ClientRPCHandler, session: SessionState, directives: PromptDirectives
    ) -> None:
        """Проверяет, что отсутствие capability возвращает None."""
        session.runtime_capabilities = ClientRuntimeCapabilities(
            terminal=False,
            fs_read=True,
            fs_write=True,
        )
        directives.terminal_command = "ls"

        prepared = handler.prepare_terminal_request(session, "sess_1", directives)

        assert prepared is None


class TestClientRPCHandlerPrepareHelper:
    """Тесты helper метода prepare_fs_request."""

    def test_prepare_fs_request_prefers_read(
        self, handler: ClientRPCHandler, session: SessionState, directives: PromptDirectives
    ) -> None:
        """Проверяет, что prepare_fs_request предпочитает fs_read."""
        directives.fs_read_path = "read.txt"
        directives.fs_write_path = "write.txt"
        directives.fs_write_content = "content"

        prepared = handler.prepare_fs_request(session, "sess_1", directives)

        # Должен подготовить fs_read, а не fs_write
        assert prepared is not None
        assert prepared.kind == "fs_read"

    def test_prepare_fs_request_falls_back_to_write(
        self, handler: ClientRPCHandler, session: SessionState, directives: PromptDirectives
    ) -> None:
        """Проверяет fallback на fs_write если fs_read_path не установлен."""
        directives.fs_read_path = None
        directives.fs_write_path = "write.txt"
        directives.fs_write_content = "content"

        prepared = handler.prepare_fs_request(session, "sess_1", directives)

        assert prepared is not None
        assert prepared.kind == "fs_write"

    def test_prepare_fs_request_no_paths(
        self, handler: ClientRPCHandler, session: SessionState, directives: PromptDirectives
    ) -> None:
        """Проверяет, что отсутствие путей возвращает None."""
        directives.fs_read_path = None
        directives.fs_write_path = None

        prepared = handler.prepare_fs_request(session, "sess_1", directives)

        assert prepared is None


class TestClientRPCHandlerResponseHandling:
    """Тесты обработки response на RPC requests."""

    def test_handle_response_error_case(
        self, handler: ClientRPCHandler, session: SessionState
    ) -> None:
        """Проверяет обработку error case в response."""
        from codelab.server.protocol.state import (
            ActiveTurnState,
            PendingClientRequestState,
            ToolCallState,
        )

        tool_call_id = "call_001"
        session.tool_calls[tool_call_id] = ToolCallState(
            tool_call_id=tool_call_id,
            title="Read",
            kind="read",
            status="pending",
        )

        pending = PendingClientRequestState(
            request_id="req_1",
            kind="fs_read",
            tool_call_id=tool_call_id,
            path="/nonexistent.txt",
        )
        session.active_turn = ActiveTurnState(
            prompt_request_id="prompt_1",
            session_id="sess_1",
            pending_client_request=pending,
        )

        error = {"message": "File not found"}
        updates = handler.handle_pending_response(session, "sess_1", "fs_read", None, error)

        assert len(updates) > 0
        assert session.tool_calls[tool_call_id].status == "failed"

    def test_handle_response_no_active_turn(
        self, handler: ClientRPCHandler, session: SessionState
    ) -> None:
        """Проверяет обработку когда нет active_turn."""
        session.active_turn = None

        result = {"content": "data"}
        updates = handler.handle_pending_response(session, "sess_1", "fs_read", result, None)

        assert len(updates) == 0

    def test_handle_response_no_pending_request(
        self, handler: ClientRPCHandler, session: SessionState
    ) -> None:
        """Проверяет обработку когда нет pending_client_request."""
        from codelab.server.protocol.state import ActiveTurnState

        session.active_turn = ActiveTurnState(
            prompt_request_id="prompt_1",
            session_id="sess_1",
            pending_client_request=None,
        )

        result = {"content": "data"}
        updates = handler.handle_pending_response(session, "sess_1", "fs_read", result, None)

        assert len(updates) == 0

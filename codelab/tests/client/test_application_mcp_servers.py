"""Тесты для CreateSessionUseCase и SessionCoordinator с MCP серверами.

Проверяет:
- CreateSessionUseCase передаёт mcpServers в session/new
- LoadSessionUseCase передаёт mcpServers в session/load
- SessionCoordinator.create_session передаёт mcp_servers
- SessionCoordinator.load_session передаёт mcp_servers
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from codelab.client.application.dto import (
    CreateSessionRequest,
    CreateSessionResponse,
    LoadSessionRequest,
    LoadSessionResponse,
)
from codelab.client.application.session_coordinator import SessionCoordinator
from codelab.client.application.use_cases import CreateSessionUseCase, LoadSessionUseCase
from codelab.client.domain import Session, SessionRepository

# ─────────────────────────────────────────────
# CreateSessionUseCase — mcp_servers
# ─────────────────────────────────────────────


class TestCreateSessionUseCaseMcpServers:
    """Проверки передачи MCP-серверов в session/new."""

    @pytest.mark.asyncio
    async def test_execute_passes_mcp_servers_to_session_new(self) -> None:
        """UseCase передаёт mcpServers в params session/new."""
        transport = AsyncMock()
        session_repo = AsyncMock()
        use_case = CreateSessionUseCase(transport=transport, session_repo=session_repo)

        transport.is_initialized = Mock(return_value=True)
        transport.is_connected = Mock(return_value=True)
        transport.get_server_capabilities = Mock(return_value={})
        transport.receive = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": "req_1",
            "result": {"sessionId": "sess_abc", "configOptions": [], "modes": {}},
        })

        mcp_servers = [
            {
                "name": "filesystem",
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            },
        ]

        request = CreateSessionRequest(
            server_host="127.0.0.1",
            server_port=8765,
            cwd="/tmp/project",
            mcp_servers=mcp_servers,
        )

        response = await use_case.execute(request)

        assert response.session_id == "sess_abc"

        # Проверить что send был вызван с правильными params
        send_calls = transport.send.call_args_list
        session_new_call = None
        for call in send_calls:
            args = call[0]
            if args and isinstance(args[0], dict) and args[0].get("method") == "session/new":
                session_new_call = args[0]
                break

        assert session_new_call is not None
        assert session_new_call["params"]["mcpServers"] == mcp_servers

    @pytest.mark.asyncio
    async def test_execute_passes_empty_list_when_mcp_servers_is_none(self) -> None:
        """UseCase передаёт пустой список если mcp_servers=None."""
        transport = AsyncMock()
        session_repo = AsyncMock()
        use_case = CreateSessionUseCase(transport=transport, session_repo=session_repo)

        transport.is_initialized = Mock(return_value=True)
        transport.is_connected = Mock(return_value=True)
        transport.get_server_capabilities = Mock(return_value={})
        transport.receive = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": "req_1",
            "result": {"sessionId": "sess_def", "configOptions": [], "modes": {}},
        })

        request = CreateSessionRequest(
            server_host="127.0.0.1",
            server_port=8765,
            cwd="/tmp/project",
            mcp_servers=None,
        )

        await use_case.execute(request)

        send_calls = transport.send.call_args_list
        session_new_call = None
        for call in send_calls:
            args = call[0]
            if args and isinstance(args[0], dict) and args[0].get("method") == "session/new":
                session_new_call = args[0]
                break

        assert session_new_call is not None
        assert session_new_call["params"]["mcpServers"] == []

    @pytest.mark.asyncio
    async def test_execute_passes_multiple_mcp_servers(self) -> None:
        """UseCase передаёт несколько MCP-серверов корректно."""
        transport = AsyncMock()
        session_repo = AsyncMock()
        use_case = CreateSessionUseCase(transport=transport, session_repo=session_repo)

        transport.is_initialized = Mock(return_value=True)
        transport.is_connected = Mock(return_value=True)
        transport.get_server_capabilities = Mock(return_value={})
        transport.receive = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": "req_1",
            "result": {"sessionId": "sess_ghi", "configOptions": [], "modes": {}},
        })

        mcp_servers = [
            {"name": "filesystem", "type": "stdio", "command": "npx", "args": ["fs-server"]},
            {"name": "github", "type": "http", "url": "https://api.githubcopilot.com/mcp"},
            {"name": "database", "type": "stdio", "command": "python", "args": ["-m", "db-server"]},
        ]

        request = CreateSessionRequest(
            server_host="127.0.0.1",
            server_port=8765,
            cwd="/tmp/project",
            mcp_servers=mcp_servers,
        )

        await use_case.execute(request)

        send_calls = transport.send.call_args_list
        session_new_call = None
        for call in send_calls:
            args = call[0]
            if args and isinstance(args[0], dict) and args[0].get("method") == "session/new":
                session_new_call = args[0]
                break

        assert session_new_call is not None
        assert len(session_new_call["params"]["mcpServers"]) == 3
        assert session_new_call["params"]["mcpServers"][1]["name"] == "github"


# ─────────────────────────────────────────────
# LoadSessionUseCase — mcp_servers
# ─────────────────────────────────────────────


class TestLoadSessionUseCaseMcpServers:
    """Проверки передачи MCP-серверов в session/load."""

    @pytest.mark.asyncio
    async def test_execute_passes_mcp_servers_to_session_load(self) -> None:
        """UseCase передаёт mcpServers в params session/load."""
        transport = AsyncMock()
        session_repo = AsyncMock()
        use_case = LoadSessionUseCase(transport=transport, session_repo=session_repo)

        session = Session.create(
            server_host="127.0.0.1",
            server_port=8765,
            client_capabilities={},
            server_capabilities={"sessionCapabilities": {"load": True}},
            session_id="sess_abc123",
        )
        session_repo.load.return_value = session
        transport.is_initialized = Mock(return_value=True)
        transport.is_connected = Mock(return_value=True)

        captured_params: dict[str, object] = {}

        async def request_with_callbacks_side_effect(
            *,
            method: str,
            params: dict[str, object],
            on_update,
            **_: object,
        ) -> dict[str, object]:
            captured_params.update(params)
            return {
                "jsonrpc": "2.0",
                "id": "req_1",
                "result": {
                    "configOptions": [],
                    "modes": {"availableModes": [], "currentModeId": "ask"},
                },
            }

        transport.request_with_callbacks.side_effect = request_with_callbacks_side_effect

        mcp_servers = [
            {"name": "filesystem", "type": "stdio", "command": "npx", "args": ["fs-server"]},
        ]

        response = await use_case.execute(
            LoadSessionRequest(
                session_id="sess_abc123",
                server_host="127.0.0.1",
                server_port=8765,
                cwd="/tmp",
                mcp_servers=mcp_servers,
            )
        )

        assert response.session_id == "sess_abc123"
        assert captured_params["mcpServers"] == mcp_servers

    @pytest.mark.asyncio
    async def test_execute_passes_empty_list_when_mcp_servers_is_none(self) -> None:
        """UseCase передаёт пустой список если mcp_servers=None."""
        transport = AsyncMock()
        session_repo = AsyncMock()
        use_case = LoadSessionUseCase(transport=transport, session_repo=session_repo)

        session = Session.create(
            server_host="127.0.0.1",
            server_port=8765,
            client_capabilities={},
            server_capabilities={"sessionCapabilities": {"load": True}},
            session_id="sess_xyz",
        )
        session_repo.load.return_value = session
        transport.is_initialized = Mock(return_value=True)
        transport.is_connected = Mock(return_value=True)

        captured_params: dict[str, object] = {}

        async def request_with_callbacks_side_effect(
            *,
            method: str,
            params: dict[str, object],
            on_update,
            **_: object,
        ) -> dict[str, object]:
            captured_params.update(params)
            return {
                "jsonrpc": "2.0",
                "id": "req_1",
                "result": {
                    "configOptions": [],
                    "modes": {"availableModes": [], "currentModeId": "ask"},
                },
            }

        transport.request_with_callbacks.side_effect = request_with_callbacks_side_effect

        await use_case.execute(
            LoadSessionRequest(
                session_id="sess_xyz",
                server_host="127.0.0.1",
                server_port=8765,
                cwd="/tmp",
                mcp_servers=None,
            )
        )

        assert captured_params["mcpServers"] == []


# ─────────────────────────────────────────────
# SessionCoordinator — mcp_servers
# ─────────────────────────────────────────────


class TestSessionCoordinatorMcpServers:
    """Проверки передачи MCP-серверов через SessionCoordinator."""

    @pytest.fixture
    def mock_transport(self) -> Mock:
        return Mock()

    @pytest.fixture
    def mock_session_repo(self) -> Mock:
        return Mock(spec=SessionRepository)

    @pytest.fixture
    def coordinator(
        self, mock_transport: Mock, mock_session_repo: Mock
    ) -> SessionCoordinator:
        return SessionCoordinator(
            transport=mock_transport,
            session_repo=mock_session_repo,
            permission_handler=None,
        )

    @pytest.mark.asyncio
    async def test_create_session_passes_mcp_servers(
        self, coordinator: SessionCoordinator, mock_transport: Mock
    ) -> None:
        """create_session передаёт mcp_servers в CreateSessionRequest."""
        mock_use_case = AsyncMock()
        mock_use_case.execute.return_value = CreateSessionResponse(
            session_id="sess_new",
            server_capabilities={},
            is_authenticated=False,
        )
        coordinator.create_session_use_case = mock_use_case

        mcp_servers = [
            {"name": "github", "type": "http", "url": "https://api.githubcopilot.com/mcp"},
        ]

        result = await coordinator.create_session(
            server_host="127.0.0.1",
            server_port=8765,
            cwd="/tmp/project",
            mcp_servers=mcp_servers,
        )

        assert result["session_id"] == "sess_new"
        mock_use_case.execute.assert_awaited_once()
        call_request = mock_use_case.execute.call_args[0][0]
        assert call_request.mcp_servers == mcp_servers

    @pytest.mark.asyncio
    async def test_load_session_passes_mcp_servers(
        self, coordinator: SessionCoordinator, mock_transport: Mock
    ) -> None:
        """load_session передаёт mcp_servers в LoadSessionRequest."""
        mock_use_case = AsyncMock()
        mock_use_case.execute.return_value = LoadSessionResponse(
            session_id="sess_load",
            server_capabilities={},
            is_authenticated=False,
            replay_updates=[],
        )
        coordinator.load_session_use_case = mock_use_case

        mcp_servers = [
            {"name": "filesystem", "type": "stdio", "command": "npx", "args": ["fs"]},
            {"name": "database", "type": "stdio", "command": "python", "args": ["db"]},
        ]

        result = await coordinator.load_session(
            session_id="sess_load",
            server_host="127.0.0.1",
            server_port=8765,
            cwd="/tmp/project",
            mcp_servers=mcp_servers,
        )

        assert result["session_id"] == "sess_load"
        mock_use_case.execute.assert_awaited_once()
        call_request = mock_use_case.execute.call_args[0][0]
        assert call_request.mcp_servers == mcp_servers

    @pytest.mark.asyncio
    async def test_create_session_with_none_mcp_servers(
        self, coordinator: SessionCoordinator
    ) -> None:
        """create_session корректно обрабатывает mcp_servers=None."""
        mock_use_case = AsyncMock()
        mock_use_case.execute.return_value = CreateSessionResponse(
            session_id="sess_none",
            server_capabilities={},
            is_authenticated=False,
        )
        coordinator.create_session_use_case = mock_use_case

        await coordinator.create_session(
            server_host="127.0.0.1",
            server_port=8765,
            cwd="/tmp",
            mcp_servers=None,
        )

        call_request = mock_use_case.execute.call_args[0][0]
        assert call_request.mcp_servers is None

    @pytest.mark.asyncio
    async def test_load_session_with_none_mcp_servers(
        self, coordinator: SessionCoordinator
    ) -> None:
        """load_session корректно обрабатывает mcp_servers=None."""
        mock_use_case = AsyncMock()
        mock_use_case.execute.return_value = LoadSessionResponse(
            session_id="sess_none",
            server_capabilities={},
            is_authenticated=False,
            replay_updates=[],
        )
        coordinator.load_session_use_case = mock_use_case

        await coordinator.load_session(
            session_id="sess_none",
            server_host="127.0.0.1",
            server_port=8765,
            cwd="/tmp",
            mcp_servers=None,
        )

        call_request = mock_use_case.execute.call_args[0][0]
        assert call_request.mcp_servers is None

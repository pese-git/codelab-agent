"""Тесты для CreateSessionUseCase."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from codelab.client.application.dto import CreateSessionRequest
from codelab.client.application.use_cases import CreateSessionUseCase


class TestCreateSessionUseCase:
    """Проверки сценария создания сессии через `session/new`."""

    @pytest.mark.asyncio
    async def test_execute_creates_session_and_saves_to_repo(self) -> None:
        """UseCase создаёт сессию и сохраняет в repository."""
        transport = AsyncMock()
        transport.is_initialized = Mock(return_value=True)
        transport.is_connected = Mock(return_value=True)
        transport.get_server_capabilities = Mock(return_value={"test": True})
        transport.send = AsyncMock()
        transport.receive = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": "req_1",
            "result": {"sessionId": "sess_new_123"},
        })

        session_repo = AsyncMock()
        session_repo.save = AsyncMock()

        use_case = CreateSessionUseCase(transport=transport, session_repo=session_repo)

        request = CreateSessionRequest(
            server_host="127.0.0.1",
            server_port=8765,
            cwd="/tmp/test",
        )
        response = await use_case.execute(request)

        assert response.session_id == "sess_new_123"
        assert response.server_capabilities == {"test": True}
        assert response.is_authenticated is False
        session_repo.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_raises_when_transport_not_initialized(self) -> None:
        """UseCase поднимает ошибку если транспорт не инициализирован."""
        transport = AsyncMock()
        transport.is_initialized = Mock(return_value=False)
        session_repo = AsyncMock()

        use_case = CreateSessionUseCase(transport=transport, session_repo=session_repo)

        request = CreateSessionRequest(
            server_host="127.0.0.1",
            server_port=8765,
            cwd="/tmp",
        )

        with pytest.raises(RuntimeError, match="Transport not initialized"):
            await use_case.execute(request)

    @pytest.mark.asyncio
    async def test_execute_raises_when_transport_not_connected(self) -> None:
        """UseCase поднимает ошибку если транспорт не подключён."""
        transport = AsyncMock()
        transport.is_initialized = Mock(return_value=True)
        transport.is_connected = Mock(return_value=False)
        session_repo = AsyncMock()

        use_case = CreateSessionUseCase(transport=transport, session_repo=session_repo)

        request = CreateSessionRequest(
            server_host="127.0.0.1",
            server_port=8765,
            cwd="/tmp",
        )

        with pytest.raises(RuntimeError, match="Transport not connected"):
            await use_case.execute(request)

    @pytest.mark.asyncio
    async def test_execute_with_authentication(self) -> None:
        """UseCase выполняет аутентификацию если указаны credentials."""
        transport = AsyncMock()
        transport.is_initialized = Mock(return_value=True)
        transport.is_connected = Mock(return_value=True)
        transport.get_server_capabilities = Mock(return_value={})
        transport.send = AsyncMock()
        transport.receive = AsyncMock(side_effect=[
            # Auth response
            {
                "jsonrpc": "2.0",
                "id": "auth_req",
                "result": {"authenticated": True},
            },
            # Session response
            {
                "jsonrpc": "2.0",
                "id": "session_req",
                "result": {"sessionId": "sess_auth_123"},
            },
        ])

        session_repo = AsyncMock()
        session_repo.save = AsyncMock()

        use_case = CreateSessionUseCase(transport=transport, session_repo=session_repo)

        request = CreateSessionRequest(
            server_host="127.0.0.1",
            server_port=8765,
            cwd="/tmp",
            auth_method="api_key",
            auth_credentials={"key": "test_key"},
        )
        response = await use_case.execute(request)

        assert response.session_id == "sess_auth_123"
        assert response.is_authenticated is True
        # Должно быть 2 вызова send: auth + session/new
        assert transport.send.await_count == 2

    @pytest.mark.asyncio
    async def test_execute_raises_on_auth_failure(self) -> None:
        """UseCase поднимает ошибку при неудачной аутентификации."""
        transport = AsyncMock()
        transport.is_initialized = Mock(return_value=True)
        transport.is_connected = Mock(return_value=True)
        transport.get_server_capabilities = Mock(return_value={})
        transport.send = AsyncMock()
        transport.receive = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": "auth_req",
            "error": {
                "code": -32000,
                "message": "Invalid credentials",
            },
        })

        session_repo = AsyncMock()

        use_case = CreateSessionUseCase(transport=transport, session_repo=session_repo)

        request = CreateSessionRequest(
            server_host="127.0.0.1",
            server_port=8765,
            cwd="/tmp",
            auth_method="api_key",
            auth_credentials={"key": "wrong_key"},
        )

        with pytest.raises(RuntimeError, match="Authentication failed"):
            await use_case.execute(request)

    @pytest.mark.asyncio
    async def test_execute_raises_on_session_creation_error(self) -> None:
        """UseCase поднимает ошибку при ошибке создания сессии."""
        transport = AsyncMock()
        transport.is_initialized = Mock(return_value=True)
        transport.is_connected = Mock(return_value=True)
        transport.get_server_capabilities = Mock(return_value={})
        transport.send = AsyncMock()
        transport.receive = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": "session_req",
            "error": {
                "code": -32600,
                "message": "Invalid Request",
            },
        })

        session_repo = AsyncMock()

        use_case = CreateSessionUseCase(transport=transport, session_repo=session_repo)

        request = CreateSessionRequest(
            server_host="127.0.0.1",
            server_port=8765,
            cwd="/tmp",
        )

        with pytest.raises(RuntimeError, match="Session creation failed"):
            await use_case.execute(request)

    @pytest.mark.asyncio
    async def test_execute_raises_on_missing_session_id(self) -> None:
        """UseCase поднимает ошибку если ответ не содержит sessionId."""
        transport = AsyncMock()
        transport.is_initialized = Mock(return_value=True)
        transport.is_connected = Mock(return_value=True)
        transport.get_server_capabilities = Mock(return_value={})
        transport.send = AsyncMock()
        transport.receive = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": "session_req",
            "result": {},  # Нет sessionId
        })

        session_repo = AsyncMock()

        use_case = CreateSessionUseCase(transport=transport, session_repo=session_repo)

        request = CreateSessionRequest(
            server_host="127.0.0.1",
            server_port=8765,
            cwd="/tmp",
        )

        with pytest.raises(RuntimeError, match="missing sessionId"):
            await use_case.execute(request)

    @pytest.mark.asyncio
    async def test_execute_with_mcp_servers(self) -> None:
        """UseCase передаёт mcpServers в session/new."""
        transport = AsyncMock()
        transport.is_initialized = Mock(return_value=True)
        transport.is_connected = Mock(return_value=True)
        transport.get_server_capabilities = Mock(return_value={})
        transport.send = AsyncMock()
        transport.receive = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": "session_req",
            "result": {"sessionId": "sess_mcp_123"},
        })

        session_repo = AsyncMock()
        session_repo.save = AsyncMock()

        use_case = CreateSessionUseCase(transport=transport, session_repo=session_repo)

        mcp_servers = [
            {
                "name": "filesystem",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem"],
            }
        ]
        request = CreateSessionRequest(
            server_host="127.0.0.1",
            server_port=8765,
            cwd="/tmp",
            mcp_servers=mcp_servers,
        )
        response = await use_case.execute(request)

        assert response.session_id == "sess_mcp_123"
        # Проверяем что mcpServers были переданы
        sent_data = transport.send.call_args[0][0]
        assert "mcpServers" in sent_data.get("params", {})

    @pytest.mark.asyncio
    async def test_execute_with_client_capabilities(self) -> None:
        """UseCase передаёт clientCapabilities в session/new."""
        transport = AsyncMock()
        transport.is_initialized = Mock(return_value=True)
        transport.is_connected = Mock(return_value=True)
        transport.get_server_capabilities = Mock(return_value={})
        transport.send = AsyncMock()
        transport.receive = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": "session_req",
            "result": {"sessionId": "sess_caps_123"},
        })

        session_repo = AsyncMock()
        session_repo.save = AsyncMock()

        use_case = CreateSessionUseCase(transport=transport, session_repo=session_repo)

        client_caps = {"fs": {"readTextFile": True}}
        request = CreateSessionRequest(
            server_host="127.0.0.1",
            server_port=8765,
            cwd="/tmp",
            client_capabilities=client_caps,
        )
        response = await use_case.execute(request)

        assert response.session_id == "sess_caps_123"
        # Проверяем что clientCapabilities были переданы
        sent_data = transport.send.call_args[0][0]
        assert "clientCapabilities" in sent_data.get("params", {})

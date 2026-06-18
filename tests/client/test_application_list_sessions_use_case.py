"""Тесты для ListSessionsUseCase."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from codelab.client.application.use_cases import ListSessionsUseCase


class TestListSessionsUseCase:
    """Проверки сценария получения списка сессий с сервера."""

    @pytest.mark.asyncio
    async def test_execute_returns_sessions_from_server(self) -> None:
        """UseCase читает список из `session/list` и возвращает его в UI-формате."""

        transport = AsyncMock()
        transport.is_initialized = Mock(return_value=True)
        transport.is_connected = Mock(return_value=True)
        transport.get_server_capabilities = Mock(
            return_value={"sessionCapabilities": {"list": True}}
        )
        transport.host = "127.0.0.1"
        transport.port = 8765

        session_repo = AsyncMock()
        session_repo.load.return_value = None

        transport.request_with_callbacks.return_value = {
            "jsonrpc": "2.0",
            "id": "list_1",
            "result": {
                "sessions": [
                    {
                        "sessionId": "sess_1",
                        "cwd": "/tmp/project",
                        "title": "Session 1",
                        "updatedAt": "2026-04-10T10:00:00Z",
                    }
                ],
                "nextCursor": None,
            },
        }

        use_case = ListSessionsUseCase(transport=transport, session_repo=session_repo)
        response = await use_case.execute()

        assert response.sessions == [
            {
                "sessionId": "sess_1",
                "cwd": "/tmp/project",
                "title": "Session 1",
                "updatedAt": "2026-04-10T10:00:00Z",
            }
        ]
        transport.request_with_callbacks.assert_awaited_once()
        session_repo.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_raises_when_transport_is_not_initialized(self) -> None:
        """UseCase сообщает понятную ошибку, если initialize не выполнен."""

        transport = AsyncMock()
        transport.is_initialized = Mock(return_value=False)
        transport.is_connected = Mock(return_value=False)

        session_repo = AsyncMock()
        use_case = ListSessionsUseCase(transport=transport, session_repo=session_repo)

        with pytest.raises(RuntimeError, match="Transport not initialized"):
            await use_case.execute()

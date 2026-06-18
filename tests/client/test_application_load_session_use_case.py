"""Тесты для LoadSessionUseCase."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from codelab.client.application.dto import LoadSessionRequest
from codelab.client.application.use_cases import LoadSessionUseCase
from codelab.client.domain import Session


class TestLoadSessionUseCase:
    """Проверки сценария загрузки сессии через `session/load`."""

    @pytest.mark.asyncio
    async def test_execute_calls_session_load_and_collects_replay_updates(self) -> None:
        """UseCase отправляет `session/load` и собирает `session/update`."""

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

        async def request_with_callbacks_side_effect(
            *,
            method: str,
            params: dict[str, object],
            on_update,
            **_: object,
        ) -> dict[str, object]:
            """Имитирует серверные updates до финального response."""

            on_update(
                {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "sessionId": "sess_abc123",
                        "update": {
                            "sessionUpdate": "user_message_chunk",
                            "content": {"type": "text", "text": "hello"},
                        },
                    },
                }
            )
            on_update(
                {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "sessionId": "sess_abc123",
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"type": "text", "text": "world"},
                        },
                    },
                }
            )
            assert method == "session/load"
            assert params["sessionId"] == "sess_abc123"
            return {
                "jsonrpc": "2.0",
                "id": "req_1",
                "result": {
                    "configOptions": [],
                    "modes": {"availableModes": [], "currentModeId": "ask"},
                },
            }

        transport.request_with_callbacks.side_effect = request_with_callbacks_side_effect

        response = await use_case.execute(
            LoadSessionRequest(
                session_id="sess_abc123",
                server_host="127.0.0.1",
                server_port=8765,
                cwd="/tmp",
            )
        )

        assert response.session_id == "sess_abc123"
        assert response.server_capabilities == {"sessionCapabilities": {"load": True}}
        assert len(response.replay_updates) == 2
        assert response.replay_updates[0]["method"] == "session/update"

    @pytest.mark.asyncio
    async def test_execute_raises_when_transport_is_not_connected(self) -> None:
        """UseCase валидирует состояние транспорта перед `session/load`."""

        transport = AsyncMock()
        session_repo = AsyncMock()
        use_case = LoadSessionUseCase(transport=transport, session_repo=session_repo)

        session_repo.load.return_value = Session.create(
            server_host="127.0.0.1",
            server_port=8765,
            client_capabilities={},
            server_capabilities={},
            session_id="sess_abc123",
        )
        transport.is_initialized = Mock(return_value=True)
        transport.is_connected = Mock(return_value=False)

        with pytest.raises(RuntimeError, match="Transport not connected"):
            await use_case.execute(
                LoadSessionRequest(
                    session_id="sess_abc123",
                    server_host="127.0.0.1",
                    server_port=8765,
                )
            )

    @pytest.mark.asyncio
    async def test_execute_ignores_updates_for_other_sessions(self) -> None:
        """UseCase игнорирует `session/update` не из запрошенной сессии."""

        transport = AsyncMock()
        session_repo = AsyncMock()
        use_case = LoadSessionUseCase(transport=transport, session_repo=session_repo)

        session_repo.load.return_value = Session.create(
            server_host="127.0.0.1",
            server_port=8765,
            client_capabilities={},
            server_capabilities={"sessionCapabilities": {"load": True}},
            session_id="sess_target",
        )
        transport.is_initialized = Mock(return_value=True)
        transport.is_connected = Mock(return_value=True)

        async def request_with_callbacks_side_effect(
            *,
            method: str,
            params: dict[str, object],
            on_update,
            **_: object,
        ) -> dict[str, object]:
            """Имитирует mixed updates для разных sessionId."""

            on_update(
                {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "sessionId": "sess_other",
                        "update": {
                            "sessionUpdate": "user_message_chunk",
                            "content": {"type": "text", "text": "foreign"},
                        },
                    },
                }
            )
            on_update(
                {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "sessionId": "sess_target",
                        "update": {
                            "sessionUpdate": "user_message_chunk",
                            "content": {"type": "text", "text": "local"},
                        },
                    },
                }
            )

            assert method == "session/load"
            assert params["sessionId"] == "sess_target"
            return {
                "jsonrpc": "2.0",
                "id": "req_1",
                "result": {
                    "configOptions": [],
                    "modes": {"availableModes": [], "currentModeId": "ask"},
                },
            }

        transport.request_with_callbacks.side_effect = request_with_callbacks_side_effect

        response = await use_case.execute(
            LoadSessionRequest(
                session_id="sess_target",
                server_host="127.0.0.1",
                server_port=8765,
                cwd="/tmp",
            )
        )

        assert len(response.replay_updates) == 1
        assert response.replay_updates[0]["params"]["sessionId"] == "sess_target"

    @pytest.mark.asyncio
    async def test_execute_creates_shadow_session_when_repo_is_empty(self) -> None:
        """UseCase создает локальную shadow-сессию, если ее нет в repository."""

        transport = AsyncMock()
        session_repo = AsyncMock()
        use_case = LoadSessionUseCase(transport=transport, session_repo=session_repo)

        session_repo.load.return_value = None
        transport.is_initialized = Mock(return_value=True)
        transport.is_connected = Mock(return_value=True)
        transport.get_server_capabilities = Mock(
            return_value={"sessionCapabilities": {"load": True}}
        )
        transport.request_with_callbacks.return_value = {
            "jsonrpc": "2.0",
            "id": "req_1",
            "result": {
                "configOptions": [],
                "modes": {"availableModes": [], "currentModeId": "ask"},
            },
        }

        response = await use_case.execute(
            LoadSessionRequest(
                session_id="sess_missing",
                server_host="127.0.0.1",
                server_port=8765,
            )
        )

        assert response.session_id == "sess_missing"
        session_repo.save.assert_awaited_once()

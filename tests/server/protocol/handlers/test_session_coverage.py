"""Дополнительные тесты покрытия для обработчиков сессий.

Покрывает ранее непокрытые ветки session_new, session_load,
session_list и вспомогательной функции _serialize_available_commands.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import structlog

from codelab.server.protocol.handlers.session import (
    _serialize_available_commands,
    session_list,
    session_load,
    session_new,
)
from codelab.server.protocol.state import SessionState, ToolCallState


class TestSerializeAvailableCommands:
    """Тесты сериализации списка доступных команд."""

    def test_dict_command_preserved(self) -> None:
        """dict-команда добавляется без изменений."""
        result = _serialize_available_commands([{"name": "cmd", "description": "d"}])
        assert result == [{"name": "cmd", "description": "d"}]

    def test_pydantic_command_dumped(self) -> None:
        """Pydantic-модель сериализуется через model_dump."""
        cmd = MagicMock()
        cmd.model_dump.return_value = {"name": "cmd", "description": "d"}
        result = _serialize_available_commands([cmd])

        assert result == [{"name": "cmd", "description": "d"}]
        cmd.model_dump.assert_called_once_with(exclude_none=False)

    def test_other_command_preserved(self) -> None:
        """Объект без model_dump добавляется как есть."""
        cmd = MagicMock(spec=[])
        result = _serialize_available_commands([cmd])
        assert result == [cmd]


class TestSessionNewEdgeCases:
    """Тесты граничных случаев session/new."""

    def test_invalid_cwd_returns_error(self) -> None:
        """Относительный cwd возвращает ошибку Invalid params."""
        response = session_new(
            request_id="req_1",
            params={"cwd": "relative/path"},
            require_auth=False,
            authenticated=True,
            config_specs={},
            auth_methods=[],
            runtime_capabilities=None,
        )

        assert response.error is not None
        assert response.error.code == -32602
        assert "cwd" in response.error.message

    def test_mcp_servers_not_array_returns_error(self) -> None:
        """Невалидный mcpServers возвращает ошибку Invalid params."""
        response = session_new(
            request_id="req_1",
            params={"cwd": "/tmp", "mcpServers": "not-array"},
            require_auth=False,
            authenticated=True,
            config_specs={},
            auth_methods=[],
            runtime_capabilities=None,
        )

        assert response.error is not None
        assert response.error.code == -32602
        assert "mcpServers" in response.error.message


class TestSessionLoadEdgeCases:
    """Тесты граничных случаев session/load."""

    async def test_auth_required_not_authenticated(self) -> None:
        """При require_auth и неаутентифицированном клиенте возвращается auth_required."""
        outcome = await session_load(
            request_id="req_1",
            params={"sessionId": "sess_1", "cwd": "/tmp", "mcpServers": []},
            require_auth=True,
            authenticated=False,
            config_specs={},
            auth_methods=[{"id": "basic"}],
            storage=AsyncMock(),
        )

        assert outcome.response is not None
        assert outcome.response.error is not None
        assert outcome.response.error.code == -32010
        assert outcome.response.error.message == "auth_required"

    async def test_invalid_session_id(self) -> None:
        """Отсутствие строкового sessionId возвращает ошибку."""
        outcome = await session_load(
            request_id="req_1",
            params={"cwd": "/tmp", "mcpServers": []},
            require_auth=False,
            authenticated=True,
            config_specs={},
            auth_methods=[],
            storage=AsyncMock(),
        )

        assert outcome.response is not None
        assert outcome.response.error is not None
        assert outcome.response.error.code == -32602
        assert "sessionId" in outcome.response.error.message

    async def test_invalid_cwd(self) -> None:
        """Относительный cwd при загрузке возвращает ошибку."""
        outcome = await session_load(
            request_id="req_1",
            params={"sessionId": "sess_1", "cwd": "relative", "mcpServers": []},
            require_auth=False,
            authenticated=True,
            config_specs={},
            auth_methods=[],
            storage=AsyncMock(),
        )

        assert outcome.response is not None
        assert outcome.response.error is not None
        assert outcome.response.error.code == -32602
        assert "cwd" in outcome.response.error.message

    async def test_invalid_mcp_servers(self) -> None:
        """Невалидный mcpServers при загрузке возвращает ошибку."""
        outcome = await session_load(
            request_id="req_1",
            params={"sessionId": "sess_1", "cwd": "/tmp", "mcpServers": "bad"},
            require_auth=False,
            authenticated=True,
            config_specs={},
            auth_methods=[],
            storage=AsyncMock(),
        )

        assert outcome.response is not None
        assert outcome.response.error is not None
        assert outcome.response.error.code == -32602
        assert "mcpServers" in outcome.response.error.message

    async def test_session_not_found(self) -> None:
        """Если сессия не найдена, возвращается ошибка Session not found."""
        storage = AsyncMock()
        storage.load_session = AsyncMock(return_value=None)

        outcome = await session_load(
            request_id="req_1",
            params={"sessionId": "missing", "cwd": "/tmp", "mcpServers": []},
            require_auth=False,
            authenticated=True,
            config_specs={},
            auth_methods=[],
            storage=storage,
        )

        assert outcome.response is not None
        assert outcome.response.error is not None
        assert outcome.response.error.code == -32001
        assert "not found" in outcome.response.error.message.lower()

    async def test_session_not_found_is_logged(self) -> None:
        """Ненайденная сессия пишет warning: иначе -32001 остаётся невидимым в логах."""
        storage = AsyncMock()
        storage.load_session = AsyncMock(return_value=None)

        with structlog.testing.capture_logs() as logs:
            await session_load(
                request_id="req_1",
                params={"sessionId": "missing", "cwd": "/tmp", "mcpServers": []},
                require_auth=False,
                authenticated=True,
                config_specs={},
                auth_methods=[],
                storage=storage,
            )

        entry = next(log for log in logs if log["event"] == "session_load_not_found")
        assert entry["log_level"] == "warning"
        assert entry["session_id"] == "missing"

    async def test_successful_load_is_logged_with_replay_composition(self) -> None:
        """Успешная загрузка пишет состав реплея.

        Единственная точка наблюдаемости session/load — по этим счётчикам
        подтверждается поведенческая нейтральность при смене источника сессии
        (ADR-006, фаза D).
        """
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            latest_plan=[{"content": "Step", "priority": "high", "status": "pending"}],
        )
        session.tool_calls["call_1"] = ToolCallState(
            tool_call_id="call_1",
            title="Test",
            kind="other",
            status="completed",
        )
        session.events_history.append(
            {
                "type": "session_update",
                "update": {
                    "sessionUpdate": "user_message_chunk",
                    "content": {"type": "text", "text": "hi"},
                },
            }
        )

        storage = AsyncMock()
        storage.load_session = AsyncMock(return_value=session)

        with structlog.testing.capture_logs() as logs:
            outcome = await session_load(
                request_id="req_1",
                params={"sessionId": "sess_1", "cwd": "/tmp", "mcpServers": []},
                require_auth=False,
                authenticated=True,
                config_specs={},
                auth_methods=[],
                storage=storage,
            )

        entry = next(log for log in logs if log["event"] == "session_loaded")
        assert entry["log_level"] == "info"
        assert entry["session_id"] == "sess_1"
        assert entry["notifications_total"] == len(outcome.notifications)
        assert entry["history_notifications"] == 1
        assert entry["plan_replayed"] is True
        # В events_history нет события tool_call, поэтому включается fallback-реплей.
        assert entry["tool_call_fallback_used"] is True
        assert entry["events_history"] == 1
        assert entry["tool_calls"] == 1

    async def test_cleanup_cancellation_is_replayed_and_recorded(self) -> None:
        """Отмена незавершённого вызова на загрузке доходит до клиента и в историю.

        _cleanup_session_state помечает pending-вызовы cancelled при
        переключении сессии. Если это не отразить, клиент по реплею увидит
        pending, а состояние сессии будет cancelled — те же три расходящиеся
        стороны, что в 6b841b46 и b8054b3e.
        """
        session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        session.tool_calls["call_1"] = ToolCallState(
            tool_call_id="call_1",
            title="Run",
            kind="execute",
            status="pending",
        )
        session.events_history.append(
            {
                "type": "session_update",
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": "call_1",
                    "title": "Run",
                    "kind": "execute",
                    "status": "pending",
                },
            }
        )

        storage = AsyncMock()
        storage.load_session = AsyncMock(return_value=session)

        outcome = await session_load(
            request_id="req_1",
            params={"sessionId": "sess_1", "cwd": "/tmp", "mcpServers": []},
            require_auth=False,
            authenticated=True,
            config_specs={},
            auth_methods=[],
            storage=storage,
        )

        assert session.tool_calls["call_1"].status == "cancelled"

        # В историю запись легла — значит любое последующее сохранение сессии
        # оставит историю и состояние согласованными.
        recorded = [
            event["update"]
            for event in session.events_history
            if event.get("update", {}).get("sessionUpdate") == "tool_call_update"
        ]
        assert [u["status"] for u in recorded] == ["cancelled"]
        assert recorded[0]["toolCallId"] == "call_1"

        # И тот же факт ушёл клиенту в реплее — после события создания.
        statuses = [
            n.params["update"].get("status")
            for n in outcome.notifications
            if n.params is not None
            and n.params.get("update", {}).get("toolCallId") == "call_1"
        ]
        assert statuses == ["pending", "cancelled"]

    async def test_replays_tool_call_with_content(self) -> None:
        """При загрузке завершенного tool call с content отправляется tool_call_update."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
        )
        session.tool_calls["call_1"] = ToolCallState(
            tool_call_id="call_1",
            title="Test",
            kind="other",
            status="completed",
            content=[{"type": "text", "text": "result"}],
        )

        storage = AsyncMock()
        storage.load_session = AsyncMock(return_value=session)

        outcome = await session_load(
            request_id="req_1",
            params={"sessionId": "sess_1", "cwd": "/tmp", "mcpServers": []},
            require_auth=False,
            authenticated=True,
            config_specs={},
            auth_methods=[],
            storage=storage,
        )

        assert outcome.response is not None
        assert outcome.response.error is None

        updates = outcome.notifications
        update_methods = [n.method for n in updates if n.method is not None]
        assert "session/update" in update_methods

        tool_call_update = next(
            (
                n.params["update"]
                for n in updates
                if n.params is not None
                and n.params.get("update", {}).get("sessionUpdate") == "tool_call_update"
            ),
            None,
        )
        assert tool_call_update is not None
        assert tool_call_update["status"] == "completed"
        assert tool_call_update["content"] == [{"type": "text", "text": "result"}]


class TestSessionListEdgeCases:
    """Тесты граничных случаев session/list."""

    async def test_invalid_cwd(self) -> None:
        """Относительный cwd в фильтре возвращает ошибку."""
        response = await session_list(
            request_id="req_1",
            params={"cwd": "relative"},
            repository=AsyncMock(),
        )

        assert response.error is not None
        assert response.error.code == -32602
        assert "cwd" in response.error.message

    async def test_invalid_cursor_type(self) -> None:
        """Нестроковый cursor возвращает ошибку."""
        response = await session_list(
            request_id="req_1",
            params={"cursor": 123},
            repository=AsyncMock(),
        )

        assert response.error is not None
        assert response.error.code == -32602
        assert "cursor" in response.error.message

    async def test_pagination_continues_to_next_page(self) -> None:
        """При наличии next_cursor storage запрашивается повторно."""
        first = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            updated_at="2026-01-02T00:00:00Z",
        )
        second = SessionState(
            session_id="sess_2",
            cwd="/tmp",
            mcp_servers=[],
            updated_at="2026-01-01T00:00:00Z",
        )

        # Порт отдаёт ту же wire-проекцию, что backend (CQRS-lite, ADR-006),
        # поэтому пагинация проверяется на нём же
        repository = AsyncMock()
        repository.list_sessions = AsyncMock(
            side_effect=[
                ([first], "cursor_2"),
                ([second], None),
            ]
        )

        response = await session_list(
            request_id="req_1",
            params={},
            repository=repository,
            session_list_page_size=10,
        )

        assert response.error is None
        assert response.result is not None
        assert len(response.result["sessions"]) == 2
        assert repository.list_sessions.call_count == 2

"""Unit-тесты для PermissionManager.

Тестирует определение необходимости permission request, управление permission policy,
построение permission messages и обработку решений.
"""

from __future__ import annotations

import pytest

from codelab.server.protocol.handlers.permission_manager import PermissionManager
from codelab.server.protocol.state import SessionState


@pytest.fixture
def manager() -> PermissionManager:
    """Фикстура для создания PermissionManager."""
    return PermissionManager()


@pytest.fixture
def session() -> SessionState:
    """Фикстура для создания базовой сессии."""
    return SessionState(
        session_id="test_session",
        cwd="/tmp",
        mcp_servers=[],
    )


class TestPermissionManagerDecision:
    """Тесты определения необходимости permission request."""

    def test_should_request_for_default(
        self, manager: PermissionManager, session: SessionState
    ) -> None:
        """Проверяет, что по умолчанию нужен permission request."""
        # tool_kind не в policy
        assert manager.should_request_permission(session, "execute") is True

    def test_should_not_request_for_allow_always(
        self, manager: PermissionManager, session: SessionState
    ) -> None:
        """Проверяет, что permission request не нужен при allow_always."""
        session.permission_policy["execute"] = "allow_always"
        assert manager.should_request_permission(session, "execute") is False

    def test_should_not_request_for_reject_always(
        self, manager: PermissionManager, session: SessionState
    ) -> None:
        """Проверяет, что permission request не нужен при reject_always."""
        session.permission_policy["execute"] = "reject_always"
        assert manager.should_request_permission(session, "execute") is False

    def test_should_request_for_unknown_policy(
        self, manager: PermissionManager, session: SessionState
    ) -> None:
        """Проверяет, что permission request нужен для неизвестного policy."""
        session.permission_policy["execute"] = "unknown"
        assert manager.should_request_permission(session, "execute") is True


class TestPermissionManagerRemembered:
    """Тесты получения remembered permission."""

    def test_get_remembered_allow(self, manager: PermissionManager, session: SessionState) -> None:
        """Проверяет получение remembered allow решения."""
        session.permission_policy["execute"] = "allow_always"
        decision = manager.get_remembered_permission(session, "execute")
        assert decision == "allow"

    def test_get_remembered_reject(self, manager: PermissionManager, session: SessionState) -> None:
        """Проверяет получение remembered reject решения."""
        session.permission_policy["execute"] = "reject_always"
        decision = manager.get_remembered_permission(session, "execute")
        assert decision == "reject"

    def test_get_remembered_default_ask(
        self, manager: PermissionManager, session: SessionState
    ) -> None:
        """Проверяет получение default 'ask' решения."""
        decision = manager.get_remembered_permission(session, "execute")
        assert decision == "ask"

    def test_get_remembered_unknown_default_ask(
        self, manager: PermissionManager, session: SessionState
    ) -> None:
        """Проверяет, что неизвестный policy возвращает 'ask'."""
        session.permission_policy["execute"] = "unknown"
        decision = manager.get_remembered_permission(session, "execute")
        assert decision == "ask"


class TestPermissionManagerRequest:
    """Тесты построения permission request."""

    def test_build_permission_request_message(
        self, manager: PermissionManager, session: SessionState
    ) -> None:
        """Проверяет структуру permission request message."""
        msg = manager.build_permission_request(
            session=session,
            session_id="sess_1",
            tool_call_id="call_001",
            tool_title="Execute Command",
            tool_kind="execute",
        )

        assert msg.method == "session/request_permission"
        assert msg.params is not None
        assert msg.params["sessionId"] == "sess_1"
        assert isinstance(msg.params.get("toolCall"), dict)
        assert msg.params["toolCall"]["toolCallId"] == "call_001"
        assert msg.params["toolCall"]["title"] == "Execute Command"
        assert msg.params["toolCall"]["kind"] == "execute"
        assert "options" in msg.params

    def test_permission_options_structure(self, manager: PermissionManager) -> None:
        """Проверяет структуру permission options."""
        options = manager.build_permission_options()

        assert len(options) == 4
        assert options[0]["optionId"] == "allow_once"
        assert options[1]["optionId"] == "allow_always"
        assert options[2]["optionId"] == "reject_once"
        assert options[3]["optionId"] == "reject_always"

        # Проверяем, что каждая опция имеет обязательные поля
        for option in options:
            assert "optionId" in option
            assert "name" in option
            assert "kind" in option

    def test_build_permission_request_sets_active_turn_ids(
        self, manager: PermissionManager, session: SessionState
    ) -> None:
        """Проверяет, что build_permission_request обновляет active_turn."""
        from codelab.server.protocol.state import ActiveTurnState

        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
        )

        msg = manager.build_permission_request(
            session=session,
            session_id="sess_1",
            tool_call_id="call_001",
            tool_title="Test",
            tool_kind="execute",
        )

        # Проверяем, что permission_request_id установлен
        if msg.id is not None:
            assert session.active_turn.permission_request_id == msg.id
            assert session.active_turn.permission_tool_call_id == "call_001"


class TestPermissionManagerExtraction:
    """Тесты извлечения данных из response."""

    def test_extract_outcome_acp_format(self, manager: PermissionManager) -> None:
        """Проверяет извлечение outcome в ACP format."""
        result = {
            "outcome": {
                "outcome": "selected",
                "optionId": "allow_once",
            }
        }
        outcome = manager.extract_permission_outcome(result)
        assert outcome == "selected"

    def test_extract_outcome_legacy_format(self, manager: PermissionManager) -> None:
        """Проверяет извлечение outcome в legacy format."""
        result = {"outcome": "selected"}
        outcome = manager.extract_permission_outcome(result)
        assert outcome == "selected"

    def test_extract_outcome_invalid_format(self, manager: PermissionManager) -> None:
        """Проверяет, что невалидный format возвращает None."""
        assert manager.extract_permission_outcome(None) is None
        assert manager.extract_permission_outcome("invalid") is None
        assert manager.extract_permission_outcome({}) is None

    def test_extract_option_id_acp_format(self, manager: PermissionManager) -> None:
        """Проверяет извлечение optionId в ACP format."""
        result = {
            "outcome": {
                "outcome": "selected",
                "optionId": "allow_once",
            }
        }
        option_id = manager.extract_permission_option_id(result)
        assert option_id == "allow_once"

    def test_extract_option_id_legacy_format(self, manager: PermissionManager) -> None:
        """Проверяет извлечение optionId в legacy format."""
        result = {"optionId": "allow_once"}
        option_id = manager.extract_permission_option_id(result)
        assert option_id == "allow_once"

    def test_extract_option_id_invalid_format(self, manager: PermissionManager) -> None:
        """Проверяет, что невалидный format возвращает None."""
        assert manager.extract_permission_option_id(None) is None
        assert manager.extract_permission_option_id({}) is None


class TestPermissionManagerOptionKind:
    """Тесты резолюции kind опции по optionId."""

    def test_resolve_option_kind_allow_once(self, manager: PermissionManager) -> None:
        """Проверяет резолюцию kind для allow_once."""
        options = manager.build_permission_options()
        kind = manager.resolve_permission_option_kind("allow_once", options)
        assert kind == "allow_once"

    def test_resolve_option_kind_allow_always(self, manager: PermissionManager) -> None:
        """Проверяет резолюцию kind для allow_always."""
        options = manager.build_permission_options()
        kind = manager.resolve_permission_option_kind("allow_always", options)
        assert kind == "allow_always"

    def test_resolve_option_kind_reject_always(self, manager: PermissionManager) -> None:
        """Проверяет резолюцию kind для reject_always."""
        options = manager.build_permission_options()
        kind = manager.resolve_permission_option_kind("reject_always", options)
        assert kind == "reject_always"

    def test_resolve_option_kind_invalid(self, manager: PermissionManager) -> None:
        """Проверяет резолюцию для несуществующего optionId."""
        options = manager.build_permission_options()
        kind = manager.resolve_permission_option_kind("invalid", options)
        assert kind is None

    def test_resolve_option_kind_none(self, manager: PermissionManager) -> None:
        """Проверяет резолюцию для None optionId."""
        options = manager.build_permission_options()
        kind = manager.resolve_permission_option_kind(None, options)
        assert kind is None


class TestPermissionManagerAcceptance:
    """Тесты обработки решения по разрешению."""

    def test_acceptance_allow_once_no_policy_save(
        self, manager: PermissionManager, session: SessionState
    ) -> None:
        """Проверяет, что allow_once не сохраняет policy."""
        tool_call_id = "call_001"
        session.tool_calls[tool_call_id] = __import__(
            "codelab.server.protocol.state", fromlist=["ToolCallState"]
        ).ToolCallState(
            tool_call_id=tool_call_id,
            title="Test",
            kind="execute",
            status="pending",
        )

        manager.build_permission_acceptance_updates(
            session=session,
            session_id="sess_1",
            tool_call_id=tool_call_id,
            option_id="allow_once",
        )

        # Policy не должна быть сохранена
        assert session.permission_policy.get("execute") is None

    def test_acceptance_allow_always_saves_policy(
        self, manager: PermissionManager, session: SessionState
    ) -> None:
        """Проверяет, что allow_always сохраняет policy."""
        from codelab.server.protocol.state import ToolCallState

        tool_call_id = "call_001"
        session.tool_calls[tool_call_id] = ToolCallState(
            tool_call_id=tool_call_id,
            title="Test",
            kind="execute",
            status="pending",
        )

        manager.build_permission_acceptance_updates(
            session=session,
            session_id="sess_1",
            tool_call_id=tool_call_id,
            option_id="allow_always",
        )

        # Policy должна быть сохранена
        assert session.permission_policy.get("execute") == "allow_always"

    def test_acceptance_reject_always_saves_policy(
        self, manager: PermissionManager, session: SessionState
    ) -> None:
        """Проверяет, что reject_always сохраняет policy."""
        from codelab.server.protocol.state import ToolCallState

        tool_call_id = "call_001"
        session.tool_calls[tool_call_id] = ToolCallState(
            tool_call_id=tool_call_id,
            title="Test",
            kind="read",
            status="pending",
        )

        manager.build_permission_acceptance_updates(
            session=session,
            session_id="sess_1",
            tool_call_id=tool_call_id,
            option_id="reject_always",
        )

        # Policy должна быть сохранена
        assert session.permission_policy.get("read") == "reject_always"

    def test_acceptance_nonexistent_tool_call(
        self, manager: PermissionManager, session: SessionState
    ) -> None:
        """Проверяет обработку несуществующего tool call."""
        updates = manager.build_permission_acceptance_updates(
            session=session,
            session_id="sess_1",
            tool_call_id="nonexistent",
            option_id="allow_always",
        )

        # Не должно быть ошибок, policy просто не сохранится
        assert len(updates) == 0


class TestPermissionManagerSessionFinding:
    """Тесты поиска сессий по permission request ID."""

    def test_find_session_by_permission_request_id(self, manager: PermissionManager) -> None:
        """Проверяет поиск сессии по permission request ID."""
        from codelab.server.protocol.state import ActiveTurnState

        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
        )
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
            permission_request_id="perm_123",
        )

        sessions = {"sess_1": session}
        found = manager.find_session_by_permission_request_id("perm_123", sessions)

        assert found is session

    def test_find_session_missing(self, manager: PermissionManager) -> None:
        """Проверяет, что поиск возвращает None для несуществующего ID."""
        sessions: dict[str, SessionState] = {}
        found = manager.find_session_by_permission_request_id("nonexistent", sessions)
        assert found is None

    def test_find_session_no_active_turn(self, manager: PermissionManager) -> None:
        """Проверяет поиск в сессии без active_turn."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
        )
        session.active_turn = None

        sessions = {"sess_1": session}
        found = manager.find_session_by_permission_request_id("perm_123", sessions)

        assert found is None

    def test_find_session_no_permission_request_id(self, manager: PermissionManager) -> None:
        """Проверяет поиск в active_turn без permission_request_id."""
        from codelab.server.protocol.state import ActiveTurnState

        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
        )
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1",
            session_id="sess_1",
            permission_request_id=None,
        )

        sessions = {"sess_1": session}
        found = manager.find_session_by_permission_request_id("perm_123", sessions)

        assert found is None

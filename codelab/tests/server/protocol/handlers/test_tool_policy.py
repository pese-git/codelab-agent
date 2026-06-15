"""Unit-тесты для ToolPolicyDecider.

Тестирует единую логику принятия решений о выполнении инструментов
с учётом mode, session policy и global policy.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from codelab.server.protocol.handlers.tool_policy import (
    decide_tool_policy,
    decide_tool_policy_async,
)
from codelab.server.protocol.state import SessionState


@pytest.fixture
def session() -> SessionState:
    """Фикстура для создания базовой сессии."""
    return SessionState(
        session_id="test_session",
        cwd="/tmp",
        mcp_servers=[],
    )


class TestDecideToolPolicyPlanMode:
    """Тесты decision chain в plan mode."""

    def test_plan_mode_blocks_execute(self, session: SessionState) -> None:
        session.config_values["mode"] = "plan"
        assert decide_tool_policy(session, "execute") == "reject"

    def test_plan_mode_blocks_edit(self, session: SessionState) -> None:
        session.config_values["mode"] = "plan"
        assert decide_tool_policy(session, "edit") == "reject"

    def test_plan_mode_blocks_delete(self, session: SessionState) -> None:
        session.config_values["mode"] = "plan"
        assert decide_tool_policy(session, "delete") == "reject"

    def test_plan_mode_blocks_bash(self, session: SessionState) -> None:
        session.config_values["mode"] = "plan"
        assert decide_tool_policy(session, "bash") == "reject"

    def test_plan_mode_allows_read(self, session: SessionState) -> None:
        session.config_values["mode"] = "plan"
        assert decide_tool_policy(session, "read") == "allow"

    def test_plan_mode_allows_search(self, session: SessionState) -> None:
        session.config_values["mode"] = "plan"
        assert decide_tool_policy(session, "search") == "allow"


class TestDecideToolPolicyBypassMode:
    """Тесты decision chain в bypass mode."""

    def test_bypass_allows_execute(self, session: SessionState) -> None:
        session.config_values["mode"] = "bypass"
        assert decide_tool_policy(session, "execute") == "allow"

    def test_bypass_allows_edit(self, session: SessionState) -> None:
        session.config_values["mode"] = "bypass"
        assert decide_tool_policy(session, "edit") == "allow"

    def test_bypass_allows_read(self, session: SessionState) -> None:
        session.config_values["mode"] = "bypass"
        assert decide_tool_policy(session, "read") == "allow"


class TestDecideToolPolicyStandardMode:
    """Тесты decision chain в standard mode."""

    def test_standard_asks_by_default(self, session: SessionState) -> None:
        assert decide_tool_policy(session, "execute") == "ask"

    def test_standard_allow_always(self, session: SessionState) -> None:
        session.permission_policy["execute"] = "allow_always"
        assert decide_tool_policy(session, "execute") == "allow"

    def test_standard_reject_always(self, session: SessionState) -> None:
        session.permission_policy["execute"] = "reject_always"
        assert decide_tool_policy(session, "execute") == "reject"

    def test_standard_unknown_policy_asks(self, session: SessionState) -> None:
        session.permission_policy["execute"] = "unknown"
        assert decide_tool_policy(session, "execute") == "ask"

    def test_standard_default_mode_is_standard(self, session: SessionState) -> None:
        """По умолчанию mode=standard, должен спрашивать."""
        assert "mode" not in session.config_values
        assert decide_tool_policy(session, "execute") == "ask"


@pytest.mark.asyncio
class TestDecideToolPolicyAsync:
    """Тесты async версии с global policy."""

    async def test_async_without_global_policy(self, session: SessionState) -> None:
        result = await decide_tool_policy_async(session, "execute")
        assert result == "ask"

    async def test_async_plan_mode_blocks(self, session: SessionState) -> None:
        session.config_values["mode"] = "plan"
        result = await decide_tool_policy_async(session, "execute")
        assert result == "reject"

    async def test_async_bypass_mode_allows(self, session: SessionState) -> None:
        session.config_values["mode"] = "bypass"
        result = await decide_tool_policy_async(session, "execute")
        assert result == "allow"

    async def test_async_session_policy_allow(self, session: SessionState) -> None:
        session.permission_policy["execute"] = "allow_always"
        result = await decide_tool_policy_async(session, "execute")
        assert result == "allow"

    async def test_async_global_policy_allow(self, session: SessionState) -> None:
        global_policy_manager = AsyncMock()
        global_policy_manager.get_global_policy.return_value = "allow_always"
        result = await decide_tool_policy_async(
            session, "execute", global_policy_manager
        )
        assert result == "allow"

    async def test_async_global_policy_reject(self, session: SessionState) -> None:
        global_policy_manager = AsyncMock()
        global_policy_manager.get_global_policy.return_value = "reject_always"
        result = await decide_tool_policy_async(
            session, "execute", global_policy_manager
        )
        assert result == "reject"

    async def test_async_global_policy_none_asks(self, session: SessionState) -> None:
        global_policy_manager = AsyncMock()
        global_policy_manager.get_global_policy.return_value = None
        result = await decide_tool_policy_async(
            session, "execute", global_policy_manager
        )
        assert result == "ask"

    async def test_async_session_policy_takes_precedence_over_global(
        self, session: SessionState
    ) -> None:
        """Session policy проверяется до global policy."""
        session.permission_policy["execute"] = "reject_always"
        global_policy_manager = AsyncMock()
        global_policy_manager.get_global_policy.return_value = "allow_always"
        result = await decide_tool_policy_async(
            session, "execute", global_policy_manager
        )
        assert result == "reject"

    async def test_async_global_policy_not_called_for_plan_mode(
        self, session: SessionState
    ) -> None:
        """В plan mode global policy не проверяется."""
        session.config_values["mode"] = "plan"
        global_policy_manager = AsyncMock()
        result = await decide_tool_policy_async(
            session, "execute", global_policy_manager
        )
        assert result == "reject"
        global_policy_manager.get_global_policy.assert_not_called()

    async def test_async_global_policy_not_called_for_bypass_mode(
        self, session: SessionState
    ) -> None:
        """В bypass mode global policy не проверяется."""
        session.config_values["mode"] = "bypass"
        global_policy_manager = AsyncMock()
        result = await decide_tool_policy_async(
            session, "execute", global_policy_manager
        )
        assert result == "allow"
        global_policy_manager.get_global_policy.assert_not_called()

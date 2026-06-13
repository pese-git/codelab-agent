"""Integration-тесты tool execution по mode через полный pipeline.

Покрывает:
- Полный цикл session/set_mode → tool execution decision
- Mode transition и его влияние на tool policy
- Интеграция DirectivesStage + PermissionManager + tool_policy
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from codelab.server.protocol.handlers.config import session_set_mode
from codelab.server.protocol.handlers.permission_manager import PermissionManager
from codelab.server.protocol.handlers.pipeline.context import PromptContext
from codelab.server.protocol.handlers.pipeline.stages.directives import (
    DirectivesStage,
)
from codelab.server.protocol.handlers.tool_policy import decide_tool_policy
from codelab.server.protocol.state import (
    ActiveTurnState,
    ClientRuntimeCapabilities,
    SessionState,
)
from codelab.server.tools.registry import SimpleToolRegistry


@pytest.fixture
def tool_registry() -> SimpleToolRegistry:
    return SimpleToolRegistry()


@pytest.fixture
def permission_manager() -> PermissionManager:
    return PermissionManager()


@pytest.fixture
def stage(
    tool_registry: SimpleToolRegistry,
    permission_manager: PermissionManager,
) -> DirectivesStage:
    return DirectivesStage(tool_registry, permission_manager)


def _make_storage(session: SessionState | None = None):
    """Создать mock storage с опциональной сессией."""
    storage = AsyncMock()
    if session is not None:
        storage.load_session = AsyncMock(return_value=session)
        storage.save_session = AsyncMock()
    else:
        storage.load_session = AsyncMock(return_value=None)
    return storage


def _make_config_specs():
    """Создать config_specs с mode опцией."""
    return {
        "mode": {
            "id": "mode",
            "name": "Mode",
            "category": "mode",
            "type": "select",
            "default": "standard",
            "options": [
                {"value": "plan", "name": "Plan"},
                {"value": "standard", "name": "Standard"},
                {"value": "bypass", "name": "Bypass"},
            ],
        },
    }


def _make_session(mode: str = "standard") -> SessionState:
    return SessionState(
        session_id="sess_1",
        cwd="/tmp",
        mcp_servers=[],
        config_values={"mode": mode},
        runtime_capabilities=ClientRuntimeCapabilities(
            terminal=True, fs_read=True, fs_write=True
        ),
    )


def _make_context(
    session: SessionState,
    params: dict | None = None,
) -> PromptContext:
    return PromptContext(
        session_id="sess_1",
        session=session,
        request_id="req_1",
        params=params or {},
        raw_text="",
    )


def _has_permission_request(result) -> bool:
    """Проверить наличие permission request в результате."""
    return any(
        n.method == "session/request_permission"
        for n in result.notifications
    )


class TestToolExecutionIntegration:
    """Integration тесты tool execution по mode."""

    @pytest.mark.asyncio
    async def test_plan_mode_blocks_all_write_operations(
        self, stage: DirectivesStage
    ) -> None:
        """В plan mode все write операции должны быть заблокированы."""
        session = _make_session(mode="plan")
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1", session_id="sess_1"
        )

        blocked_kinds = ["edit", "delete", "execute"]

        for kind in blocked_kinds:
            context = _make_context(
                session,
                params={
                    "_meta": {
                        "promptDirectives": {
                            "requestTool": True,
                            "toolKind": kind,
                        }
                    }
                },
            )

            result = await stage.process(context)
            msg = f"Kind '{kind}' should be cancelled in plan mode"
            assert result.stop_reason == "cancelled", msg

    @pytest.mark.asyncio
    async def test_plan_mode_allows_all_read_operations(
        self, stage: DirectivesStage
    ) -> None:
        """В plan mode все read операции должны быть разрешены."""
        session = _make_session(mode="plan")
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1", session_id="sess_1"
        )

        allowed_kinds = ["read", "search", "think", "fetch", "move"]

        for kind in allowed_kinds:
            context = _make_context(
                session,
                params={
                    "_meta": {
                        "promptDirectives": {
                            "requestTool": True,
                            "toolKind": kind,
                        }
                    }
                },
            )

            result = await stage.process(context)
            msg = f"Kind '{kind}' should be allowed in plan mode"
            assert result.stop_reason != "cancelled", msg
            assert not _has_permission_request(result)

    @pytest.mark.asyncio
    async def test_bypass_mode_allows_all_operations(
        self, stage: DirectivesStage
    ) -> None:
        """В bypass mode все операции должны выполняться автоматически."""
        session = _make_session(mode="bypass")
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1", session_id="sess_1"
        )

        all_kinds = [
            "edit", "delete", "execute", "bash", "terminal",
            "read", "search",
        ]

        for kind in all_kinds:
            context = _make_context(
                session,
                params={
                    "_meta": {
                        "promptDirectives": {
                            "requestTool": True,
                            "toolKind": kind,
                        }
                    }
                },
            )

            result = await stage.process(context)
            msg = f"Kind '{kind}' should not be cancelled in bypass mode"
            assert result.stop_reason != "cancelled", msg
            assert not _has_permission_request(result)

    @pytest.mark.asyncio
    async def test_standard_mode_requests_permission_for_write(
        self, stage: DirectivesStage
    ) -> None:
        """В standard mode write операции должны запрашивать permission."""
        session = _make_session(mode="standard")
        session.active_turn = ActiveTurnState(
            prompt_request_id="req_1", session_id="sess_1"
        )

        write_kinds = ["edit", "delete", "execute", "bash", "terminal"]

        for kind in write_kinds:
            context = _make_context(
                session,
                params={
                    "_meta": {
                        "promptDirectives": {
                            "requestTool": True,
                            "toolKind": kind,
                        }
                    }
                },
            )

            result = await stage.process(context)
            assert _has_permission_request(result)
            assert result.pending_permission is True


class TestModeTransitionIntegration:
    """Integration тесты перехода между режимами."""

    @pytest.mark.asyncio
    async def test_mode_transition_from_plan_to_bypass(self) -> None:
        """Переход из plan в bypass должен изменить поведение tool policy."""
        session = _make_session(mode="plan")

        # В plan mode execute заблокирован
        assert decide_tool_policy(session, "execute") == "reject"
        assert decide_tool_policy(session, "edit") == "reject"
        assert decide_tool_policy(session, "read") == "allow"

        # Сменяем режим на bypass
        session.config_values["mode"] = "bypass"

        # В bypass mode всё разрешено
        assert decide_tool_policy(session, "execute") == "allow"
        assert decide_tool_policy(session, "edit") == "allow"
        assert decide_tool_policy(session, "read") == "allow"

    @pytest.mark.asyncio
    async def test_mode_transition_from_bypass_to_standard(self) -> None:
        """Переход из bypass в standard должен включить permission."""
        session = _make_session(mode="bypass")

        # В bypass mode всё разрешено
        assert decide_tool_policy(session, "execute") == "allow"
        assert decide_tool_policy(session, "edit") == "allow"

        # Сменяем режим на standard
        session.config_values["mode"] = "standard"

        # В standard mode требуется permission
        assert decide_tool_policy(session, "execute") == "ask"
        assert decide_tool_policy(session, "edit") == "ask"

    @pytest.mark.asyncio
    async def test_mode_transition_from_standard_to_plan(self) -> None:
        """Переход из standard в plan должен заблокировать write."""
        session = _make_session(mode="standard")

        # В standard mode требуется permission
        assert decide_tool_policy(session, "execute") == "ask"
        assert decide_tool_policy(session, "edit") == "ask"

        # Сменяем режим на plan
        session.config_values["mode"] = "plan"

        # В plan mode write заблокированы
        assert decide_tool_policy(session, "execute") == "reject"
        assert decide_tool_policy(session, "edit") == "reject"
        assert decide_tool_policy(session, "read") == "allow"

    @pytest.mark.asyncio
    async def test_session_set_mode_updates_tool_policy(self) -> None:
        """session/set_mode должен обновлять tool policy."""
        session = _make_session(mode="standard")
        storage = _make_storage(session)

        # Изначально standard mode → ask
        assert decide_tool_policy(session, "execute") == "ask"

        # Выполняем session/set_mode → bypass
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "sess_1", "modeId": "bypass"},
            storage,
            _make_config_specs(),
        )

        assert outcome.response is not None
        assert outcome.response.error is None
        assert session.config_values.get("mode") == "bypass"

        # Теперь bypass mode → allow
        assert decide_tool_policy(session, "execute") == "allow"

    @pytest.mark.asyncio
    async def test_session_set_mode_with_old_mode_normalization(self) -> None:
        """session/set_mode с старым mode должен нормализовать."""
        session = _make_session(mode="standard")
        storage = _make_storage(session)

        # Выполняем session/set_mode с старым mode "code"
        outcome = await session_set_mode(
            "req_1",
            {"sessionId": "sess_1", "modeId": "code"},
            storage,
            _make_config_specs(),
        )

        assert outcome.response is not None
        assert outcome.response.error is None
        assert session.config_values.get("mode") == "bypass"

        # Tool policy должна соответствовать bypass
        assert decide_tool_policy(session, "execute") == "allow"
        assert decide_tool_policy(session, "edit") == "allow"


class TestToolPolicyDecisionIntegration:
    """Integration тесты decide_tool_policy."""

    def test_plan_mode_with_allow_always_policy(self) -> None:
        """В plan mode allow_always policy не должен override блокировку."""
        session = _make_session(mode="plan")
        session.permission_policy["execute"] = "allow_always"

        assert decide_tool_policy(session, "execute") == "reject"

    def test_plan_mode_with_reject_always_policy(self) -> None:
        """В plan mode reject_always policy согласуется с блокировкой."""
        session = _make_session(mode="plan")
        session.permission_policy["execute"] = "reject_always"

        assert decide_tool_policy(session, "execute") == "reject"

    def test_bypass_mode_with_reject_always_policy(self) -> None:
        """В bypass mode bypass override reject_always policy."""
        session = _make_session(mode="bypass")
        session.permission_policy["execute"] = "reject_always"

        assert decide_tool_policy(session, "execute") == "allow"

    def test_standard_mode_with_allow_always_policy(self) -> None:
        """В standard mode allow_always policy должен auto-execute."""
        session = _make_session(mode="standard")
        session.permission_policy["execute"] = "allow_always"

        assert decide_tool_policy(session, "execute") == "allow"

    def test_standard_mode_with_reject_always_policy(self) -> None:
        """В standard mode reject_always policy должен auto-reject."""
        session = _make_session(mode="standard")
        session.permission_policy["execute"] = "reject_always"

        assert decide_tool_policy(session, "execute") == "reject"

    def test_standard_mode_without_policy(self) -> None:
        """В standard mode без policy должен быть ask."""
        session = _make_session(mode="standard")

        assert decide_tool_policy(session, "execute") == "ask"
        assert decide_tool_policy(session, "edit") == "ask"
        assert decide_tool_policy(session, "read") == "ask"

    def test_default_mode_is_standard(self) -> None:
        """Сессия без mode должна использовать standard."""
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
        )

        assert decide_tool_policy(session, "execute") == "ask"

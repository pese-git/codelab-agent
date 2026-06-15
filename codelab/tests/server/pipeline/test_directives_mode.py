"""Тесты DirectivesStage — tool execution по mode.

Покрывает:
- mode=plan: блокировка write/execute инструментов
- mode=standard: permission request
- mode=bypass: auto-execute
"""

from __future__ import annotations

import pytest

from codelab.server.protocol.handlers.permission_manager import PermissionManager
from codelab.server.protocol.handlers.pipeline.context import PromptContext
from codelab.server.protocol.handlers.pipeline.stages.directives import DirectivesStage
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


class TestDirectivesStagePlanMode:
    """Тесты tool execution в plan mode."""

    @pytest.mark.asyncio
    async def test_plan_mode_rejects_execute(
        self, stage: DirectivesStage
    ) -> None:
        """В plan mode execute инструмент должен быть отклонён."""
        session = _make_session(mode="plan")
        session.active_turn = ActiveTurnState(prompt_request_id="req_1", session_id="sess_1")
        context = _make_context(
            session,
            params={
                "_meta": {
                    "promptDirectives": {
                        "requestTool": True,
                        "toolKind": "execute",
                    }
                }
            },
        )

        result = await stage.process(context)

        # В plan mode execute должен быть rejected
        assert result.stop_reason == "cancelled"
        # Не должно быть permission request
        permission_requests = [
            n for n in result.notifications
            if n.method == "session/request_permission"
        ]
        assert len(permission_requests) == 0

    @pytest.mark.asyncio
    async def test_plan_mode_rejects_edit(
        self, stage: DirectivesStage
    ) -> None:
        """В plan mode edit инструмент должен быть отклонён."""
        session = _make_session(mode="plan")
        session.active_turn = ActiveTurnState(prompt_request_id="req_1", session_id="sess_1")
        context = _make_context(
            session,
            params={
                "_meta": {
                    "promptDirectives": {
                        "requestTool": True,
                        "toolKind": "edit",
                    }
                }
            },
        )

        result = await stage.process(context)
        assert result.stop_reason == "cancelled"

    @pytest.mark.asyncio
    async def test_plan_mode_allows_read(
        self, stage: DirectivesStage
    ) -> None:
        """В plan mode read инструмент должен быть разрешён."""
        session = _make_session(mode="plan")
        session.active_turn = ActiveTurnState(prompt_request_id="req_1", session_id="sess_1")
        context = _make_context(
            session,
            params={
                "_meta": {
                    "promptDirectives": {
                        "requestTool": True,
                        "toolKind": "read",
                    }
                }
            },
        )

        result = await stage.process(context)
        # Read в plan mode — allow, не должно быть cancelled
        assert result.stop_reason != "cancelled"
        # Не должно быть permission request
        permission_requests = [
            n for n in result.notifications
            if n.method == "session/request_permission"
        ]
        assert len(permission_requests) == 0


class TestDirectivesStageBypassMode:
    """Тесты tool execution в bypass mode."""

    @pytest.mark.asyncio
    async def test_bypass_mode_auto_executes_execute(
        self, stage: DirectivesStage
    ) -> None:
        """В bypass mode execute инструмент должен выполниться автоматически."""
        session = _make_session(mode="bypass")
        session.active_turn = ActiveTurnState(prompt_request_id="req_1", session_id="sess_1")
        context = _make_context(
            session,
            params={
                "_meta": {
                    "promptDirectives": {
                        "requestTool": True,
                        "toolKind": "execute",
                    }
                }
            },
        )

        result = await stage.process(context)

        # Bypass mode — auto-execute, не должно быть permission request
        permission_requests = [
            n for n in result.notifications
            if n.method == "session/request_permission"
        ]
        assert len(permission_requests) == 0
        # Не должно быть cancelled
        assert result.stop_reason != "cancelled"

    @pytest.mark.asyncio
    async def test_bypass_mode_auto_executes_edit(
        self, stage: DirectivesStage
    ) -> None:
        """В bypass mode edit инструмент должен выполниться автоматически."""
        session = _make_session(mode="bypass")
        session.active_turn = ActiveTurnState(prompt_request_id="req_1", session_id="sess_1")
        context = _make_context(
            session,
            params={
                "_meta": {
                    "promptDirectives": {
                        "requestTool": True,
                        "toolKind": "edit",
                    }
                }
            },
        )

        result = await stage.process(context)
        permission_requests = [
            n for n in result.notifications
            if n.method == "session/request_permission"
        ]
        assert len(permission_requests) == 0


class TestDirectivesStageStandardMode:
    """Тесты tool execution в standard mode."""

    @pytest.mark.asyncio
    async def test_standard_mode_requests_permission(
        self, stage: DirectivesStage
    ) -> None:
        """В standard mode без policy должен запрашиваться permission."""
        session = _make_session(mode="standard")
        session.active_turn = ActiveTurnState(prompt_request_id="req_1", session_id="sess_1")
        context = _make_context(
            session,
            params={
                "_meta": {
                    "promptDirectives": {
                        "requestTool": True,
                        "toolKind": "execute",
                    }
                }
            },
        )

        result = await stage.process(context)

        # Standard mode без policy — permission request
        permission_requests = [
            n for n in result.notifications
            if n.method == "session/request_permission"
        ]
        assert len(permission_requests) == 1
        assert result.pending_permission is True
        assert result.should_stop is True

    @pytest.mark.asyncio
    async def test_standard_mode_allow_always_auto_executes(
        self, stage: DirectivesStage
    ) -> None:
        """В standard mode с allow_always policy — auto-execute."""
        session = _make_session(mode="standard")
        session.permission_policy["execute"] = "allow_always"
        session.active_turn = ActiveTurnState(prompt_request_id="req_1", session_id="sess_1")
        context = _make_context(
            session,
            params={
                "_meta": {
                    "promptDirectives": {
                        "requestTool": True,
                        "toolKind": "execute",
                    }
                }
            },
        )

        result = await stage.process(context)

        # allow_always — auto-execute, без permission request
        permission_requests = [
            n for n in result.notifications
            if n.method == "session/request_permission"
        ]
        assert len(permission_requests) == 0

    @pytest.mark.asyncio
    async def test_standard_mode_reject_always_cancels(
        self, stage: DirectivesStage
    ) -> None:
        """В standard mode с reject_always policy — cancel."""
        session = _make_session(mode="standard")
        session.permission_policy["execute"] = "reject_always"
        session.active_turn = ActiveTurnState(prompt_request_id="req_1", session_id="sess_1")
        context = _make_context(
            session,
            params={
                "_meta": {
                    "promptDirectives": {
                        "requestTool": True,
                        "toolKind": "execute",
                    }
                }
            },
        )

        result = await stage.process(context)
        assert result.stop_reason == "cancelled"

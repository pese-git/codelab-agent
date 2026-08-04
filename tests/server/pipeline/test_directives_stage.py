"""Юнит-тесты для DirectivesStage — обработка forced_stop_reason.

Покрывают:
- Установка context.stop_reason из forced_stop_reason
- Все ACP stop reasons: max_tokens, max_turn_requests, refusal
- Pipeline continuation после forced_stop_reason (не останавливает)
- Комбинации forced_stop_reason с другими директивами
"""

from __future__ import annotations

import pytest

from codelab.server.domain.session import Session as DomainSession
from codelab.server.domain.session import TurnState
from codelab.server.mapping.plan_mapper import PlanMapper
from codelab.server.protocol.handlers.permission_manager import PermissionManager
from codelab.server.protocol.handlers.pipeline.context import PromptContext
from codelab.server.protocol.handlers.pipeline.stages.directives import DirectivesStage
from codelab.server.protocol.state import PromptDirectives
from codelab.server.storage.document import ClientRuntimeCapabilities
from codelab.server.tools.registry import SimpleToolRegistry
from tests.server._domain_sessions import make_commands, make_domain_session


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


@pytest.fixture
def session() -> DomainSession:
    return make_domain_session(
        session_id="sess_1",
        cwd="/tmp",
        mcp_servers=[],
    )


def _make_context(
    session: DomainSession,
    raw_text: str,
    params: dict | None = None,
) -> PromptContext:
    return PromptContext(
        session_id="sess_1",
        session=session,
        commands=make_commands(session),
        request_id="req_1",
        params=params or {},
        raw_text=raw_text,
    )


class TestDirectivesStageForcedStopReason:
    """Тесты установки stop_reason из forced_stop_reason."""

    @pytest.mark.asyncio
    async def test_stop_reason_max_tokens_from_slash(
        self, stage: DirectivesStage, session: DomainSession
    ) -> None:
        """Slash-команда /stop-max-tokens устанавливает context.stop_reason."""
        session.active_turn = TurnState(prompt_request_id="req_1", session_id="sess_1")
        context = _make_context(session, "/stop-max-tokens")

        result = await stage.process(context)

        assert result.stop_reason == "max_tokens"
        assert result.should_stop is False  # forced_stop_reason НЕ останавливает pipeline

    @pytest.mark.asyncio
    async def test_stop_reason_max_turn_requests_from_slash(
        self, stage: DirectivesStage, session: DomainSession
    ) -> None:
        """Slash-команда /stop-max-turn-requests устанавливает context.stop_reason."""
        session.active_turn = TurnState(prompt_request_id="req_1", session_id="sess_1")
        context = _make_context(session, "/stop-max-turn-requests")

        result = await stage.process(context)

        assert result.stop_reason == "max_turn_requests"
        assert result.should_stop is False

    @pytest.mark.asyncio
    async def test_stop_reason_refusal_from_slash(
        self, stage: DirectivesStage, session: DomainSession
    ) -> None:
        """Slash-команда /refuse устанавливает context.stop_reason."""
        session.active_turn = TurnState(prompt_request_id="req_1", session_id="sess_1")
        context = _make_context(session, "/refuse")

        result = await stage.process(context)

        assert result.stop_reason == "refusal"
        assert result.should_stop is False

    @pytest.mark.asyncio
    async def test_stop_reason_max_tokens_from_meta(
        self, stage: DirectivesStage, session: DomainSession
    ) -> None:
        """_meta.promptDirectives.forcedStopReason: max_tokens."""
        session.active_turn = TurnState(prompt_request_id="req_1", session_id="sess_1")
        context = _make_context(
            session,
            "plain text",
            params={
                "_meta": {
                    "promptDirectives": {
                        "forcedStopReason": "max_tokens",
                    }
                }
            },
        )

        result = await stage.process(context)

        assert result.stop_reason == "max_tokens"
        assert result.should_stop is False

    @pytest.mark.asyncio
    async def test_stop_reason_max_turn_requests_from_meta(
        self, stage: DirectivesStage, session: DomainSession
    ) -> None:
        """_meta.promptDirectives.forcedStopReason: max_turn_requests."""
        session.active_turn = TurnState(prompt_request_id="req_1", session_id="sess_1")
        context = _make_context(
            session,
            "plain text",
            params={
                "_meta": {
                    "promptDirectives": {
                        "forcedStopReason": "max_turn_requests",
                    }
                }
            },
        )

        result = await stage.process(context)

        assert result.stop_reason == "max_turn_requests"
        assert result.should_stop is False

    @pytest.mark.asyncio
    async def test_stop_reason_refusal_from_meta(
        self, stage: DirectivesStage, session: DomainSession
    ) -> None:
        """_meta.promptDirectives.forcedStopReason: refusal."""
        session.active_turn = TurnState(prompt_request_id="req_1", session_id="sess_1")
        context = _make_context(
            session,
            "plain text",
            params={
                "_meta": {
                    "promptDirectives": {
                        "forcedStopReason": "refusal",
                    }
                }
            },
        )

        result = await stage.process(context)

        assert result.stop_reason == "refusal"
        assert result.should_stop is False

    @pytest.mark.asyncio
    async def test_no_forced_stop_reason_keeps_default(
        self, stage: DirectivesStage, session: DomainSession
    ) -> None:
        """Без forced_stop_reason context.stop_reason остаётся 'end_turn'."""
        session.active_turn = TurnState(prompt_request_id="req_1", session_id="sess_1")
        context = _make_context(session, "hello world")

        result = await stage.process(context)

        assert result.stop_reason == "end_turn"

    @pytest.mark.asyncio
    async def test_forced_stop_reason_does_not_stop_pipeline(
        self, stage: DirectivesStage, session: DomainSession
    ) -> None:
        """forced_stop_reason изменяет stop_reason, но НЕ устанавливает should_stop."""
        session.active_turn = TurnState(prompt_request_id="req_1", session_id="sess_1")
        context = _make_context(session, "/refuse")

        result = await stage.process(context)

        assert result.stop_reason == "refusal"
        assert result.should_stop is False
        assert result.pending_permission is False

    @pytest.mark.asyncio
    async def test_forced_stop_reason_with_additional_text(
        self, stage: DirectivesStage, session: DomainSession
    ) -> None:
        """forced_stop_reason извлекается даже с дополнительным текстом."""
        session.active_turn = TurnState(prompt_request_id="req_1", session_id="sess_1")
        context = _make_context(session, "/stop-max-tokens because of limit")

        result = await stage.process(context)

        assert result.stop_reason == "max_tokens"

    @pytest.mark.asyncio
    async def test_forced_stop_reason_stored_in_meta(
        self, stage: DirectivesStage, session: DomainSession
    ) -> None:
        """Directives сохраняются в context.meta['directives']."""
        session.active_turn = TurnState(prompt_request_id="req_1", session_id="sess_1")
        context = _make_context(session, "/stop-max-turn-requests")

        result = await stage.process(context)

        assert "directives" in result.meta
        assert isinstance(result.meta["directives"], PromptDirectives)
        assert result.meta["directives"].forced_stop_reason == "max_turn_requests"


class TestDirectivesStageForcedStopReasonWithOtherDirectives:
    """Тесты комбинаций forced_stop_reason с другими директивами."""

    @pytest.mark.asyncio
    async def test_forced_stop_reason_with_request_tool(
        self, stage: DirectivesStage, session: DomainSession
    ) -> None:
        """forced_stop_reason может сосуществовать с requestTool."""
        # Capabilities — поле неизменяемого `SessionConfig`, поэтому сессия для
        # tool-runtime собирается со своими capabilities, а не патчится после.
        session = make_domain_session(
            session_id="sess_1",
            cwd="/tmp",
            mcp_servers=[],
            runtime_capabilities=ClientRuntimeCapabilities(
                terminal=True, fs_read=False, fs_write=False
            ),
        )
        session.active_turn = TurnState(prompt_request_id="req_1", session_id="sess_1")
        context = _make_context(
            session,
            "text",
            params={
                "_meta": {
                    "promptDirectives": {
                        "forcedStopReason": "max_tokens",
                        "requestTool": True,
                    }
                }
            },
        )

        result = await stage.process(context)

        assert result.stop_reason == "max_tokens"
        # requestTool=True в режиме ask → permission request → should_stop=True
        assert result.should_stop is True
        assert result.pending_permission is True

    @pytest.mark.asyncio
    async def test_forced_stop_reason_with_publish_plan(
        self, stage: DirectivesStage, session: DomainSession
    ) -> None:
        """forced_stop_reason с publishPlan — plan notification добавляется."""
        session.active_turn = TurnState(prompt_request_id="req_1", session_id="sess_1")
        context = _make_context(
            session,
            "/plan entry1, entry2",
            params={
                "_meta": {
                    "promptDirectives": {
                        "forcedStopReason": "refusal",
                    }
                }
            },
        )

        result = await stage.process(context)

        assert result.stop_reason == "refusal"
        assert result.should_stop is False
        # Plan notification должен быть добавлен
        plan_notifications = [
            n
            for n in result.notifications
            if n.params and n.params.get("update", {}).get("sessionUpdate") == "plan"
        ]
        assert len(plan_notifications) == 1

    @pytest.mark.asyncio
    async def test_stored_plan_matches_wire_notification(
        self, stage: DirectivesStage, session: DomainSession
    ) -> None:
        """P2-26: latest_plan байт-идентичен entries в live-notification.

        Гарантирует, что replay на session/load отдаст ту же ACP-форму, что ушла
        клиенту вживую (никаких {title, description} в хранении).
        """
        session.active_turn = TurnState(prompt_request_id="req_1", session_id="sess_1")
        context = _make_context(session, "/plan entry1, entry2")

        result = await stage.process(context)

        plan_notifications = [
            n
            for n in result.notifications
            if n.params and n.params.get("update", {}).get("sessionUpdate") == "plan"
        ]
        assert len(plan_notifications) == 1
        wire_entries = plan_notifications[0].params["update"]["entries"]
        # Сверяем ACP-форму: план хранится доменным `AgentPlan`, а на диск и в wire
        # уезжает через `PlanMapper` — совпасть обязаны именно эти формы.
        assert PlanMapper.to_acp(session.plan.get_steps()) == wire_entries

    @pytest.mark.asyncio
    async def test_meta_overrides_slash_forced_stop_reason(
        self, stage: DirectivesStage, session: DomainSession
    ) -> None:
        """_meta forcedStopReason имеет приоритет над slash-командой."""
        session.active_turn = TurnState(prompt_request_id="req_1", session_id="sess_1")
        context = _make_context(
            session,
            "/stop-max-tokens",
            params={
                "_meta": {
                    "promptDirectives": {
                        "forcedStopReason": "refusal",
                    }
                }
            },
        )

        result = await stage.process(context)

        # _meta имеет приоритет
        assert result.stop_reason == "refusal"


class TestDirectivesStageShouldStopBehavior:
    """Тесты that forced_stop_reason does NOT trigger should_stop."""

    @pytest.mark.asyncio
    async def test_all_forced_stop_reasons_dont_stop_pipeline(
        self, stage: DirectivesStage, session: DomainSession
    ) -> None:
        """Все forced_stop_reason значения НЕ останавливают pipeline."""
        forced_reasons = ["max_tokens", "max_turn_requests", "refusal"]

        for reason in forced_reasons:
            session.active_turn = TurnState(prompt_request_id="req_1", session_id="sess_1")
            context = _make_context(
                session,
                "text",
                params={
                    "_meta": {
                        "promptDirectives": {
                            "forcedStopReason": reason,
                        }
                    }
                },
            )

            result = await stage.process(context)

            assert result.stop_reason == reason, f"Failed for reason: {reason}"
            assert result.should_stop is False, f"should_stop should be False for: {reason}"

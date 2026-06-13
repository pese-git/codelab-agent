"""Единая точка принятия решений о выполнении инструментов.

Decision chain:
1. mode=plan → reject для write/execute, allow для read
2. mode=bypass → allow все инструменты
3. mode=standard → session policy → global policy → ask

Этот сервис устраняет дублирование логики mode-check, которая ранее
существовала в трёх местах:
- PermissionManager.decide()
- directives._decide_tool_policy()
- agent_loop._decide_tool_execution()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import structlog

from ..mode import MODE_BYPASS, MODE_PLAN, is_tool_blocked_in_plan_mode

if TYPE_CHECKING:
    from codelab.server.protocol.handlers.global_policy_manager import GlobalPolicyManager
    from codelab.server.protocol.state import SessionState

PermissionDecision = Literal["allow", "reject", "ask"]

logger = structlog.get_logger()


def decide_tool_policy(session: SessionState, tool_kind: str) -> PermissionDecision:
    """Определить политику выполнения инструмента (синхронная версия).

    Цепочка решений:
    1. mode=plan → reject для write/execute, allow для read
    2. mode=bypass → allow все инструменты
    3. mode=standard → session policy → ask

    Без global policy — используется в DirectivesStage.

    Args:
        session: Состояние сессии.
        tool_kind: Категория инструмента.

    Returns:
        "allow" — выполнить автоматически.
        "reject" — отклонить.
        "ask" — запросить разрешение у пользователя.
    """
    mode = session.config_values.get("mode", "standard")

    if mode == MODE_PLAN:
        if is_tool_blocked_in_plan_mode(tool_kind):
            logger.debug(
                "tool_policy_decision",
                mode=mode,
                tool_kind=tool_kind,
                decision="reject",
                reason="plan_mode_blocks",
            )
            return "reject"
        logger.debug(
            "tool_policy_decision",
            mode=mode,
            tool_kind=tool_kind,
            decision="allow",
            reason="plan_mode_allows_read",
        )
        return "allow"

    if mode == MODE_BYPASS:
        logger.debug(
            "tool_policy_decision",
            mode=mode,
            tool_kind=tool_kind,
            decision="allow",
            reason="bypass_auto_execute",
        )
        return "allow"

    session_policy = session.permission_policy.get(tool_kind)
    if session_policy == "allow_always":
        logger.debug(
            "tool_policy_decision",
            mode=mode,
            tool_kind=tool_kind,
            decision="allow",
            reason="session_policy_allow_always",
        )
        return "allow"
    if session_policy == "reject_always":
        logger.debug(
            "tool_policy_decision",
            mode=mode,
            tool_kind=tool_kind,
            decision="reject",
            reason="session_policy_reject_always",
        )
        return "reject"

    return _decide_core(session, tool_kind, global_policy=None)


async def decide_tool_policy_async(
    session: SessionState,
    tool_kind: str,
    global_policy_manager: GlobalPolicyManager | None = None,
) -> PermissionDecision:
    """Определить политику выполнения (асинхронная версия).

    Цепочка решений:
    1. mode=plan → reject для write/execute, allow для read
    2. mode=bypass → allow все инструменты
    3. mode=standard → session policy → global policy → ask

    С global policy — используется в AgentLoop.

    Args:
        session: Состояние сессии.
        tool_kind: Категория инструмента.
        global_policy_manager: Опциональный менеджер глобальных политик.

    Returns:
        "allow" — выполнить автоматически.
        "reject" — отклонить.
        "ask" — запросить разрешение у пользователя.
    """
    # Fast path: plan/bypass не требуют global policy
    mode = session.config_values.get("mode", "standard")
    if mode == MODE_PLAN:
        if is_tool_blocked_in_plan_mode(tool_kind):
            logger.debug(
                "tool_policy_decision",
                mode=mode,
                tool_kind=tool_kind,
                decision="reject",
                reason="plan_mode_blocks",
            )
            return "reject"
        logger.debug(
            "tool_policy_decision",
            mode=mode,
            tool_kind=tool_kind,
            decision="allow",
            reason="plan_mode_allows_read",
        )
        return "allow"

    if mode == MODE_BYPASS:
        logger.debug(
            "tool_policy_decision",
            mode=mode,
            tool_kind=tool_kind,
            decision="allow",
            reason="bypass_auto_execute",
        )
        return "allow"

    # Standard mode: session policy
    session_policy = session.permission_policy.get(tool_kind)
    if session_policy == "allow_always":
        logger.debug(
            "tool_policy_decision",
            mode=mode,
            tool_kind=tool_kind,
            decision="allow",
            reason="session_policy_allow_always",
        )
        return "allow"
    if session_policy == "reject_always":
        logger.debug(
            "tool_policy_decision",
            mode=mode,
            tool_kind=tool_kind,
            decision="reject",
            reason="session_policy_reject_always",
        )
        return "reject"

    # Global policy — вызываем только если дошли сюда
    global_policy = None
    if global_policy_manager is not None:
        global_policy = await global_policy_manager.get_global_policy(tool_kind)

    return _decide_core(session, tool_kind, global_policy=global_policy)


def _decide_core(
    session: SessionState,
    tool_kind: str,
    global_policy: str | None,
) -> PermissionDecision:
    """Завершение цепочки решений после session policy (global policy → ask)."""
    mode = session.config_values.get("mode", "standard")

    if global_policy == "allow_always":
        logger.debug(
            "tool_policy_decision",
            mode=mode,
            tool_kind=tool_kind,
            decision="allow",
            reason="global_policy_allow_always",
        )
        return "allow"
    if global_policy == "reject_always":
        logger.debug(
            "tool_policy_decision",
            mode=mode,
            tool_kind=tool_kind,
            decision="reject",
            reason="global_policy_reject_always",
        )
        return "reject"

    logger.debug(
        "tool_policy_decision",
        mode=mode,
        tool_kind=tool_kind,
        decision="ask",
        reason="default_ask",
    )
    return "ask"

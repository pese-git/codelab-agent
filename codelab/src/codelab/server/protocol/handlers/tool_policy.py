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

from ..mode import MODE_BYPASS, MODE_PLAN, is_tool_blocked_in_plan_mode

if TYPE_CHECKING:
    from codelab.server.protocol.handlers.global_policy_manager import GlobalPolicyManager
    from codelab.server.protocol.state import SessionState

PermissionDecision = Literal["allow", "reject", "ask"]


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

    # 1. Plan mode: блокируем write/execute
    if mode == MODE_PLAN:
        if is_tool_blocked_in_plan_mode(tool_kind):
            return "reject"
        return "allow"

    # 2. Bypass mode: auto-execute все инструменты
    if mode == MODE_BYPASS:
        return "allow"

    # 3. Standard mode: session policy
    session_policy = session.permission_policy.get(tool_kind)
    if session_policy == "allow_always":
        return "allow"
    if session_policy == "reject_always":
        return "reject"

    return "ask"


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
    mode = session.config_values.get("mode", "standard")

    # 1. Plan mode: блокируем write/execute
    if mode == MODE_PLAN:
        if is_tool_blocked_in_plan_mode(tool_kind):
            return "reject"
        return "allow"

    # 2. Bypass mode: auto-execute все инструменты
    if mode == MODE_BYPASS:
        return "allow"

    # 3. Standard mode: session policy
    session_policy = session.permission_policy.get(tool_kind)
    if session_policy == "allow_always":
        return "allow"
    if session_policy == "reject_always":
        return "reject"

    # 4. Global policy
    if global_policy_manager is not None:
        global_policy = await global_policy_manager.get_global_policy(tool_kind)
        if global_policy == "allow_always":
            return "allow"
        if global_policy == "reject_always":
            return "reject"

    return "ask"

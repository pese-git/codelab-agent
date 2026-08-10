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

from ...domain.mode import DEFAULT_MODE, MODE_BYPASS, MODE_PLAN, is_tool_blocked_in_plan_mode

if TYPE_CHECKING:
    from codelab.server.domain.session import Session
    from codelab.server.protocol.handlers.global_policy_manager import GlobalPolicyManager

PermissionDecision = Literal["allow", "reject", "ask"]

logger = structlog.get_logger()


def decide_tool_policy(session: Session, tool_kind: str) -> PermissionDecision:
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
    mode = session.get_config_value("mode", "standard")

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

    session_policy = session.get_permission_policy(tool_kind)
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



def describe_rejection(session: Session, tool_kind: str) -> str:
    """Причина отказа для модели — тем же знанием, каким принято решение.

    Текст уходит модели в теле tool result (и клиенту в `tool_call_update`),
    поэтому обязан называть причину и её длительность. Прежнее сообщение
    (`Tool execution rejected by policy for <kind>`) не говорило ни того, ни
    другого: в plan-режиме модель трактовала отказ как разовый сбой, повторяла
    вызов и работала с несуществующими терминалами, выжигая turn до лимита
    запросов (tech-debt P2-36, найдено разбором живых прогонов).

    Args:
        session: Состояние сессии (источник режима и политик).
        tool_kind: Категория инструмента.

    Returns:
        Причина отказа с указанием, что повтор даст тот же результат.
    """
    mode = session.get_config_value("mode", DEFAULT_MODE)

    if mode == MODE_PLAN and is_tool_blocked_in_plan_mode(tool_kind):
        return (
            f"Сессия в режиме '{MODE_PLAN}' (read-only): инструменты вида '{tool_kind}' "
            "недоступны, пока пользователь не сменит режим. Повторный вызов даст тот же "
            "отказ — используй инструменты чтения или заверши ответ."
        )

    if session.get_permission_policy(tool_kind) == "reject_always":
        return (
            f"Пользователь запретил инструменты вида '{tool_kind}' на всю сессию. "
            "Повторный вызов даст тот же отказ — измени подход или заверши ответ."
        )

    return (
        f"Вызов инструмента вида '{tool_kind}' отклонён политикой. Повторный вызов, "
        "скорее всего, даст тот же отказ — измени подход или заверши ответ."
    )


async def decide_tool_policy_async(
    session: Session,
    tool_kind: str,
    global_policy_manager: GlobalPolicyManager | None = None,
    *,
    requires_permission: bool = True,
) -> PermissionDecision:
    """Определить политику выполнения (асинхронная версия).

    Цепочка решений:
    0. инструмент не объявлял требования разрешения → allow
    1. mode=plan → reject для write/execute, allow для read
    2. mode=bypass → allow все инструменты
    3. mode=standard → session policy → global policy → ask

    С global policy — используется в AgentLoop.

    Шаг 0 цепочки переехал сюда из вызывающего (ADR-009, шаг 1): решение о том,
    нужно ли вообще спрашивать, — часть политики, а не подготовка к её вызову.
    Пока проверка жила у `ToolCallProcessor`, у политики было два владельца, и
    вызывающий без этой проверки её просто не делал — это и есть P1-56.

    Порядок сохранён дословно: `requires_permission=False` даёт `allow`
    **раньше** проверки режима, как и было в вызывающем. Иначе инструмент без
    требования разрешения начал бы отклоняться в plan-режиме — изменение
    поведения, которого шаг 1 не допускает.

    Args:
        session: Состояние сессии.
        tool_kind: Категория инструмента.
        global_policy_manager: Опциональный менеджер глобальных политик.
        requires_permission: Объявляет ли инструмент требование разрешения.
            MCP-инструменты передают `True` всегда — у них требование по
            умолчанию (`tool_adapter.py`).

    Returns:
        "allow" — выполнить автоматически.
        "reject" — отклонить.
        "ask" — запросить разрешение у пользователя.
    """
    if not requires_permission:
        logger.debug(
            "tool_policy_decision",
            tool_kind=tool_kind,
            decision="allow",
            reason="tool_declares_no_permission",
        )
        return "allow"

    # Fast path: plan/bypass не требуют global policy
    mode = session.get_config_value("mode", "standard")
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
    session_policy = session.get_permission_policy(tool_kind)
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
    session: Session,
    tool_kind: str,
    global_policy: str | None,
) -> PermissionDecision:
    """Завершение цепочки решений после session policy (global policy → ask)."""
    mode = session.get_config_value("mode", "standard")

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

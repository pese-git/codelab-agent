"""Применение решения по permission-request к активному prompt-turn."""

from __future__ import annotations

from typing import Any

import structlog

from ....domain.session import Session as DomainSession
from ....domain.value_objects import ToolCallStatus
from ....messages import ACPMessage, JsonRpcId
from ...state import PendingToolExecution, ProtocolOutcome
from ...turn_runtime import TurnEndCause, finish_turn
from ..permissions import build_permission_options
from ..session import session_info_notification
from ..tool_call_handler import ToolCallHandler
from .tool_call_state import update_tool_call_status
from .tool_call_updates import tool_call_status_notification

logger = structlog.get_logger()


def resolve_permission_response_impl(
    *,
    session: DomainSession,
    permission_request_id: JsonRpcId,
    result: Any,
) -> ProtocolOutcome | None:
    """Применяет решение по permission-request к активному prompt-turn.

    Работает доменным агрегатом внутри транзакции репозитория (фаза D ADR-006):
    до этого путь мутировал копию, которую никто не сохранял, поэтому запомненная
    policy-решением политика, снятые permission-идентификаторы и статус вызова не
    доживали до диска (tech-debt P1-49, причина P2-46).

    Пример использования:
        outcome = resolve_permission_response_impl(
            session=session,
            permission_request_id="perm_1",
            result={"outcome": {"outcome": "selected", "optionId": "allow_once"}},
        )
    """

    from ..permissions import (
        extract_permission_option_id,
        extract_permission_outcome,
        resolve_permission_option_kind,
    )

    if session.active_turn is None:
        return None
    # Вызов берётся у ожидания **этого** запроса, а не «текущего» ожидания turn'а:
    # незакрытых разрешений может быть несколько, и ответы приходят в любом порядке.
    wait = session.active_turn.permission_wait_for(permission_request_id)
    if wait is None or wait.tool_call_id is None:
        return None
    tool_call_id = wait.tool_call_id

    session_id = str(session.id)
    notifications: list[ACPMessage] = []
    outcome_value = extract_permission_outcome(result)
    selected_option = extract_permission_option_id(result)
    selected_option_id = selected_option if isinstance(selected_option, str) else None
    selected_option_kind = resolve_permission_option_kind(
        selected_option_id, build_permission_options()
    )

    # Снятие ожидания ЕСТЬ возврат в `running` (ADR-008, шаг 2): оно часть значения
    # фазы, поэтому «снял, но забыл вернуть фазу» больше не выразимо. До этого фаза
    # оставалась `awaiting_permission` до конца turn'а при обоих идентификаторах
    # `null` — наблюдалось живьём (прогон 2026-08-06) и мешало различить «процесс умер на
    # настоящей паузе» от «идентификатор не сняли» (P2-46).
    #
    # Закрывается ровно **это** ожидание: если turn ждёт ещё чьего-то решения, он
    # обязан продолжать ждать, а не считать себя разбуженным чужим ответом (P1-61).
    session.active_turn.close_permission(permission_request_id)

    tool_call = session.tool_calls.get(tool_call_id)
    tool_kind = tool_call.kind if tool_call is not None else None

    if tool_kind is not None and selected_option_kind in {"allow_always", "reject_always"}:
        # Сохраняем policy-решение для следующих tool-call этого же kind.
        session.set_permission_policy(tool_kind, selected_option_kind)

    should_allow = bool(
        outcome_value == "selected" and selected_option_kind in {"allow_once", "allow_always"}
    )
    status = ToolCallStatus.IN_PROGRESS if should_allow else ToolCallStatus.CANCELLED
    # Через дверь, а не напрямую: с шага 4g ADR-008 статус — проекция журнала, и
    # решение по разрешению, записанное только в реестр, терялось бы на
    # следующей команде — ровно там, где turn возобновляют.
    update_tool_call_status(session, tool_call_id, status.value)
    notifications.append(
        tool_call_status_notification(
            session_id=session_id, tool_call_id=tool_call_id, status=status.value
        )
    )

    session.mark_updated()
    notifications.append(
        session_info_notification(
            session_id=session_id,
            title=None,
            updated_at=session.updated_at,
        )
    )

    if not should_allow:
        # Отказ обрывает turn: отложенный хвост батча (P2-40) не выполнится, и без
        # ответа его вызовы остались бы без `role: tool`.
        ToolCallHandler().answer_unexecuted_tool_calls(
            session,
            session.take_deferred_batch_ids(),
            reason="в разрешении отказано",
        )

        cancelled = finish_turn(
            session,
            cause=TurnEndCause.PERMISSION_DENIED,
            stop_reason="cancelled",
        )
        return ProtocolOutcome(
            notifications=notifications,
            followup_responses=[cancelled] if cancelled is not None else [],
        )

    # Turn не завершаем: вызов исполнит фоновая задача и она же закроет turn.
    logger.debug(
        "permission allowed, scheduling tool execution",
        session_id=session_id,
        tool_call_id=tool_call_id,
    )

    return ProtocolOutcome(
        notifications=notifications,
        followup_responses=[],
        pending_tool_execution=PendingToolExecution(
            session_id=session_id,
            tool_call_id=tool_call_id,
        ),
    )

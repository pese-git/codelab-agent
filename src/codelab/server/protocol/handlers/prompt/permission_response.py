"""Применение решения по permission-request к активному prompt-turn."""

from __future__ import annotations

from typing import Any

import structlog

from ....domain.session import Session as DomainSession
from ....domain.value_objects import ToolCallStatus
from ....messages import ACPMessage, JsonRpcId
from ...state import PendingToolExecution, ProtocolOutcome
from ..permissions import build_permission_options
from ..session import session_info_notification
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
    tool_call_id = session.active_turn.permission_tool_call_id
    if tool_call_id is None:
        return None

    session_id = str(session.id)
    notifications: list[ACPMessage] = []
    outcome_value = extract_permission_outcome(result)
    selected_option = extract_permission_option_id(result)
    selected_option_id = selected_option if isinstance(selected_option, str) else None
    selected_option_kind = resolve_permission_option_kind(
        selected_option_id, build_permission_options()
    )

    session.active_turn.permission_request_id = None
    session.active_turn.permission_tool_call_id = None

    tool_call = session.tool_calls.get(tool_call_id)
    tool_kind = tool_call.kind if tool_call is not None else None

    if tool_kind is not None and selected_option_kind in {"allow_always", "reject_always"}:
        # Сохраняем policy-решение для следующих tool-call этого же kind.
        session.set_permission_policy(tool_kind, selected_option_kind)

    should_allow = bool(
        outcome_value == "selected" and selected_option_kind in {"allow_once", "allow_always"}
    )
    status = ToolCallStatus.IN_PROGRESS if should_allow else ToolCallStatus.CANCELLED
    session.tool_calls.update_status(tool_call_id, status)
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
        session.answer_deferred_batch(reason="в разрешении отказано")

        prompt_request_id = session.active_turn.prompt_request_id
        session.clear_active_turn()
        cancelled = (
            ACPMessage.response(prompt_request_id, {"stopReason": "cancelled"})
            if prompt_request_id is not None
            else None
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

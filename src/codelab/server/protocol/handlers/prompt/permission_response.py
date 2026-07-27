"""Применение решения по permission-request к активному prompt-turn."""

from __future__ import annotations

from typing import Any

import structlog

from ....messages import ACPMessage, JsonRpcId
from ...state import PendingToolExecution, ProtocolOutcome, SessionState
from ..permissions import build_permission_options
from ..session import session_info_notification
from .tool_calls import build_policy_tool_execution_updates, finalize_active_turn

logger = structlog.get_logger()


def resolve_permission_response_impl(
    *,
    session: SessionState,
    permission_request_id: JsonRpcId,
    result: Any,
) -> ProtocolOutcome | None:
    """Реализация применения решения по permission-request к активному prompt-turn.

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

    session_id = session.session_id
    notifications: list[ACPMessage] = []
    outcome_value = extract_permission_outcome(result)
    selected_option = extract_permission_option_id(result)
    selected_option_id = selected_option if isinstance(selected_option, str) else None
    selected_option_kind = resolve_permission_option_kind(
        selected_option_id, build_permission_options()
    )

    session.active_turn.permission_request_id = None
    session.active_turn.permission_tool_call_id = None

    tool_call_state = session.tool_calls.get(tool_call_id)
    tool_kind = tool_call_state.kind if tool_call_state is not None else None

    if tool_kind is not None and selected_option_kind in {"allow_always", "reject_always"}:
        # Сохраняем policy-решение для следующих tool-call этого же kind.
        session.set_permission_policy(tool_kind, selected_option_kind)

    should_allow = bool(
        outcome_value == "selected" and selected_option_kind in {"allow_once", "allow_always"}
    )
    if not should_allow:
        notifications.extend(
            build_policy_tool_execution_updates(
                session=session,
                session_id=session_id,
                tool_call_id=tool_call_id,
                allowed=False,
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
        cancelled = finalize_active_turn(session=session, stop_reason="cancelled")
        return ProtocolOutcome(
            notifications=notifications,
            followup_responses=[cancelled] if cancelled is not None else [],
        )

    # ✅ КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Когда permission allowed, отправить notifications
    # и завершить turn с end_turn. Tool execution будет выполнен внутри session_prompt().
    notifications.extend(
        build_policy_tool_execution_updates(
            session=session,
            session_id=session_id,
            tool_call_id=tool_call_id,
            allowed=True,
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

    # ✅ КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Не завершаем turn, а сигнализируем о pending tool execution
    # http_server.py выполнит tool асинхронно и затем завершит turn
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

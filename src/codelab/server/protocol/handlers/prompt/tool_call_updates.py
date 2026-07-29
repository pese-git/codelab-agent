"""ACP-рендер lifecycle-обновлений tool call (постоянная wire-граница).

Строит `session/update: tool_call_update` для двух путей исполнения —
executor-lifecycle и решение policy. Вынесено из `tool_calls.py`, который
совмещал рендер с мутацией состояния сессии (расщепление двуликих фасадов,
фаза C ADR-006): рендер остаётся на wire навсегда, мутация уезжает в домен.

Полностью развязать их не получится и не нужно: обе функции по построению
атомарны — «сменить статус и сообщить об этом клиенту», поэтому они зовут
`update_tool_call_status` (мутация состояния). Разделение делает эту связь явной:
видно, какая половина каждой функции переедет в домен в фазе D.
"""

from __future__ import annotations

from ....messages import ACPMessage
from ...state import SessionState
from .tool_calls import update_tool_call_status


def build_executor_tool_execution_updates(
    *,
    session: SessionState,
    session_id: str,
    tool_call_id: str,
    leave_running: bool,
) -> list[ACPMessage]:
    """Генерирует базовый executor-lifecycle для существующего tool-call.

    Пример использования:
        updates = build_executor_tool_execution_updates(
            session=state,
            session_id="sess_1",
            tool_call_id="call_001",
            leave_running=False,
        )
    """

    in_progress = ACPMessage.notification(
        "session/update",
        {
            "sessionId": session_id,
            "update": {
                "sessionUpdate": "tool_call_update",
                "toolCallId": tool_call_id,
                "status": "in_progress",
            },
        },
    )
    update_tool_call_status(session, tool_call_id, "in_progress")

    if leave_running:
        return [in_progress]

    completed_content = [
        {
            "type": "content",
            "content": {
                "type": "text",
                "text": "Tool completed successfully.",
            },
        }
    ]
    update_tool_call_status(
        session,
        tool_call_id,
        "completed",
        content=completed_content,
    )
    completed = ACPMessage.notification(
        "session/update",
        {
            "sessionId": session_id,
            "update": {
                "sessionUpdate": "tool_call_update",
                "toolCallId": tool_call_id,
                "status": "completed",
                "content": completed_content,
            },
        },
    )
    return [in_progress, completed]


def build_policy_tool_execution_updates(
    *,
    session: SessionState,
    session_id: str,
    tool_call_id: str,
    allowed: bool,
) -> list[ACPMessage]:
    """Строит lifecycle updates для tool execution после policy-решения.

    При allowed=True отправляет только "in_progress" статус.
    Реальное выполнение и "completed" статус обрабатываются асинхронно
    через pending_tool_execution в ProtocolOutcome.

    Пример использования:
        updates = build_policy_tool_execution_updates(
            session=state,
            session_id="sess_1",
            tool_call_id="call_1",
            allowed=True,
        )
    """

    if not allowed:
        update_tool_call_status(session, tool_call_id, "cancelled")
        return [
            ACPMessage.notification(
                "session/update",
                {
                    "sessionId": session_id,
                    "update": {
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": tool_call_id,
                        "status": "cancelled",
                    },
                },
            )
        ]

    # При allowed=True только отмечаем "in_progress".
    # Реальное выполнение будет запущено асинхронно через pending_tool_execution.
    update_tool_call_status(session, tool_call_id, "in_progress")
    return [
        ACPMessage.notification(
            "session/update",
            {
                "sessionId": session_id,
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": tool_call_id,
                    "status": "in_progress",
                },
            },
        )
    ]

"""ACP-рендер lifecycle-обновлений tool call (постоянная wire-граница).

Строит `session/update: tool_call_update` для двух путей исполнения —
executor-lifecycle и решение policy. Вынесено из `tool_calls.py`, который
совмещал рендер с мутацией состояния сессии (расщепление двуликих фасадов,
фаза C ADR-006): рендер остаётся на wire навсегда, мутация уезжает в домен.

Полностью развязать их не получится и не нужно: обе функции по построению
атомарны — «сменить статус и сообщить об этом клиенту», поэтому они зовут
`update_tool_call_status` из `tool_call_state`. Разделение делает эту связь явной:
видно, какая половина каждой функции переедет в домен в фазе D.
"""

from __future__ import annotations

from typing import Any

from ....domain.session import Session
from ....messages import ACPMessage
from .tool_call_state import update_tool_call_status


def tool_call_status_notification(
    *,
    session_id: str,
    tool_call_id: str,
    status: str,
    content: list[dict[str, Any]] | None = None,
    locations: list[dict[str, Any]] | None = None,
    raw_output: dict[str, Any] | None = None,
) -> ACPMessage:
    """ACP-нотификация о смене статуса tool call — чистый wire, без состояния.

    Шов, по которому фаза D разрезает функции ниже: рендер остаётся здесь
    навсегда, а смену статуса делает владелец состояния (для переехавших
    транзакций — доменный `ToolCallRegistry.update_status`).

    Единственное место, где собирается форма `tool_call_update`: остальные
    строители (`ToolCallHandler.build_tool_update_notification`, обработчики
    ответов client-RPC) делегируют сюда, иначе форма расходилась бы по копиям.
    """
    update: dict[str, Any] = {
        "sessionUpdate": "tool_call_update",
        "toolCallId": tool_call_id,
        "status": status,
    }
    if content is not None:
        update["content"] = content
    if locations is not None:
        update["locations"] = locations
    if raw_output is not None:
        update["rawOutput"] = raw_output
    return ACPMessage.notification(
        "session/update",
        {"sessionId": session_id, "update": update},
    )


def build_executor_tool_execution_updates(
    *,
    session: Session,
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

    in_progress = tool_call_status_notification(
        session_id=session_id, tool_call_id=tool_call_id, status="in_progress"
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
    completed = tool_call_status_notification(
        session_id=session_id,
        tool_call_id=tool_call_id,
        status="completed",
        content=completed_content,
    )
    return [in_progress, completed]


def build_policy_tool_execution_updates(
    *,
    session: Session,
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
            tool_call_status_notification(
                session_id=session_id, tool_call_id=tool_call_id, status="cancelled"
            )
        ]

    # При allowed=True только отмечаем "in_progress".
    # Реальное выполнение будет запущено асинхронно через pending_tool_execution.
    update_tool_call_status(session, tool_call_id, "in_progress")
    return [
        tool_call_status_notification(
            session_id=session_id, tool_call_id=tool_call_id, status="in_progress"
        )
    ]

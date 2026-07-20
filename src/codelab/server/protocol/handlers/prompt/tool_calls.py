"""Жизненный цикл tool-call и prompt-turn: создание/обновление/отмена, финализация
turn, lifecycle-updates и plan entries."""

from __future__ import annotations

from typing import Any

from ....messages import ACPMessage
from ...state import PromptDirectives, SessionState, ToolCallState
from .normalization import normalize_stop_reason


def create_tool_call(session: SessionState, *, title: str, kind: str) -> str:
    """Создает запись нового tool call в состоянии сессии.

    Пример использования:
        tool_call_id = create_tool_call(state, title="Demo", kind="other")
    """

    # Локально монотонный ID делает тесты предсказуемыми и читабельными.
    session.tool_call_counter += 1
    tool_call_id = f"call_{session.tool_call_counter:03d}"
    session.tool_calls[tool_call_id] = ToolCallState(
        tool_call_id=tool_call_id,
        title=title,
        kind=kind,
        status="pending",
    )
    return tool_call_id


def update_tool_call_status(
    session: SessionState,
    tool_call_id: str,
    status: str,
    *,
    content: list[dict[str, Any]] | None = None,
) -> None:
    """Обновляет статус tool call с проверкой допустимых переходов.

    Пример использования:
        update_tool_call_status(state, "call_001", "in_progress")
    """

    state = session.tool_calls.get(tool_call_id)
    if state is None:
        return

    # Явная матрица переходов защищает от нелегальных смен статуса.
    allowed_transitions: dict[str, set[str]] = {
        "pending": {"in_progress", "cancelled", "failed"},
        "in_progress": {"completed", "cancelled", "failed"},
        "completed": set(),
        "cancelled": set(),
        "failed": set(),
    }
    next_states = allowed_transitions.get(state.status, set())
    if status not in next_states and status != state.status:
        return

    state.status = status
    if content is not None:
        state.content = content


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


def build_plan_entries(
    *,
    directives: PromptDirectives,
    text_preview: str,
) -> list[dict[str, str]]:
    """Строит plan entries для `session/update: plan`.

    Пример использования:
        entries = build_plan_entries(
            directives=directives,
            text_preview="ship release",
        )
    """

    if directives.plan_entries:
        return directives.plan_entries

    normalized_preview = text_preview.strip() or "выполнение запроса"
    short_preview = normalized_preview[:80]
    return [
        {
            "content": f"Уточнить задачу: {short_preview}",
            "priority": "high",
            "status": "completed",
        },
        {
            "content": f"Выполнить основной шаг для: {short_preview}",
            "priority": "high",
            "status": "in_progress",
        },
        {
            "content": "Проверить результат и завершить ответ",
            "priority": "medium",
            "status": "pending",
        },
    ]


def cancel_active_tool_calls(session: SessionState, session_id: str) -> list[ACPMessage]:
    """Отменяет все незавершенные tool calls и формирует update-события.

    Пример использования:
        updates = cancel_active_tool_calls(state, "sess_1")
    """

    # Финальные статусы не трогаем, отменяем только активные вызовы.
    notifications: list[ACPMessage] = []
    for tool_call in session.tool_calls.values():
        if tool_call.status not in {"pending", "in_progress"}:
            continue
        update_tool_call_status(session, tool_call.tool_call_id, "cancelled")
        notifications.append(
            ACPMessage.notification(
                "session/update",
                {
                    "sessionId": session_id,
                    "update": {
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": tool_call.tool_call_id,
                        "status": "cancelled",
                    },
                },
            )
        )
    return notifications


def finalize_active_turn(session: SessionState, *, stop_reason: str) -> ACPMessage | None:
    """Финализирует текущий active turn и очищает его состояние.

    Пример использования:
        response = finalize_active_turn(state, stop_reason="cancelled")
    """

    active_turn = session.active_turn
    if active_turn is None or active_turn.prompt_request_id is None:
        return None

    session.active_turn = None
    return ACPMessage.response(
        active_turn.prompt_request_id,
        {"stopReason": normalize_stop_reason(stop_reason)},
    )


def complete_active_turn(
    session: SessionState,
    *,
    stop_reason: str = "end_turn",
) -> ACPMessage | None:
    """Завершает активный prompt-turn и возвращает финальный response.

    Используется транспортом WS для отложенного ответа на `session/prompt`.

    Пример использования:
        response = complete_active_turn(session, stop_reason="end_turn")
    """
    return finalize_active_turn(
        session=session,
        stop_reason=normalize_stop_reason(stop_reason),
    )


def should_auto_complete_active_turn(
    session: SessionState,
) -> bool:
    """Возвращает `True`, если active turn можно безопасно автозавершить.

    Если turn ожидает permission-response, автозавершение запрещено.

    Пример использования:
        if should_auto_complete_active_turn(session):
            ...
    """
    if session.active_turn is None:
        return False
    return session.active_turn.phase == "waiting_tool_completion"

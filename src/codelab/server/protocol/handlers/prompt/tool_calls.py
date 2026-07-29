"""Мутации состояния: запись tool call и жизненный цикл prompt-turn.

ACP-рендер lifecycle-обновлений переехал в `tool_call_updates`, построение
содержимого плана — к `PlanBuilder` (расщепление двуликих фасадов, фаза C
ADR-006): здесь осталось изменение состояния сессии."""

from __future__ import annotations

from typing import Any

from ....messages import ACPMessage
from ...state import SessionState, ToolCallState
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

"""Жизненный цикл active turn: финализация и автозавершение.

Выделено из `tool_calls.py` (фаза C ADR-006). Отдельно от tool call'ов, потому
что в фазе D у turn-состояния своя точка сцепления — `TurnLifecycleManager`, и
переключается оно раньше tool call'ов (транзакция `session/cancel`).
"""

from __future__ import annotations

import structlog

from ....messages import ACPMessage
from ...state import SessionState
from .normalization import normalize_stop_reason

logger = structlog.get_logger()


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

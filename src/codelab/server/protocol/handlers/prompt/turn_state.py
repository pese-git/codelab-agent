"""Жизненный цикл active turn: финализация и автозавершение.

Выделено из `tool_calls.py` (фаза C ADR-006). Отдельно от tool call'ов, потому
что в фазе D у turn-состояния своя точка сцепления — `TurnLifecycleManager`, и
переключается оно раньше tool call'ов (транзакция `session/cancel`).
"""

from __future__ import annotations

import structlog

from ....domain.session import Session as DomainSession
from ....domain.value_objects import AwaitingPermission
from ....messages import ACPMessage
from .normalization import normalize_stop_reason

logger = structlog.get_logger()


def finalize_active_turn(session: DomainSession, *, stop_reason: str) -> ACPMessage | None:
    """Финализирует текущий active turn и очищает его состояние.

    Работает с доменным агрегатом, а не с документом (ADR-008, шаг 2): фаза turn'а —
    типизированный `TurnPhase`, и интерпретировать её должен домен, а не читатель
    сериализованной формы.

    ⚠️ **Очистка turn'а здесь на диск не попадает — так было и до перехода.**
    Вызывающий (`BackgroundExecutor`) загружает сессию только для чтения и не
    сохраняет её, а бэкенд отдаёт новый объект на каждую загрузку. Сделать очистку
    настоящей записью — отдельное решение: это изменение поведения на пути завершения
    turn'а, и оно требует своего живого прогона.

    Пример использования:
        response = finalize_active_turn(session, stop_reason="cancelled")
    """

    active_turn = session.active_turn
    if active_turn is None or active_turn.prompt_request_id is None:
        return None

    session.clear_active_turn()
    return ACPMessage.response(
        active_turn.prompt_request_id,
        {"stopReason": normalize_stop_reason(stop_reason)},
    )


def complete_active_turn(
    session: DomainSession,
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
    session: DomainSession,
) -> bool:
    """Возвращает `True`, если active turn можно безопасно автозавершить.

    Если turn ожидает permission-response, автозавершение запрещено.

    Пример использования:
        if should_auto_complete_active_turn(session):
            ...
    """
    if session.active_turn is None:
        return False
    # Признак читается из значения фазы, а не из её имени: до ADR-008 шага 2 те же две
    # ветки одного состояния различались строкой `waiting_tool_completion`.
    phase = session.active_turn.phase
    return isinstance(phase, AwaitingPermission) and phase.keep_tool_pending

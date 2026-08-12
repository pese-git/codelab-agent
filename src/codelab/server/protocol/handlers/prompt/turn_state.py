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
from ...turn_runtime import TurnEndCause, finish_turn
from .normalization import normalize_stop_reason

logger = structlog.get_logger()


def finalize_active_turn(session: DomainSession, *, stop_reason: str) -> ACPMessage | None:
    """Финализирует текущий active turn и очищает его состояние.

    Работает с доменным агрегатом, а не с документом (ADR-008, шаг 2): фаза turn'а —
    типизированный `TurnPhase`, и интерпретировать её должен домен, а не читатель
    сериализованной формы.

    Очистка доезжает до диска: вызывающий (`BackgroundExecutor`) снимает turn командой
    над свежей копией, а не мутацией read-only загрузки (P2-54, 2026-08-11). Прежде
    решение о снятии жило только в памяти, и на диске оставался `active_turn` с
    `phase: running` у давно закрытого turn'а.

    **Turn без идентификатора исходного запроса снимается тоже (P2-54, 2026-08-12).**
    Прежде такой turn не снимался вовсе: guard выходил раньше снятия, и на диске
    оставалась фаза паузы — ровно симптом, ради которого заведён P2-54. Отвечать в этом
    случае по-прежнему некому, и `finish_turn` это уже учитывает: он снимает turn и
    возвращает `None`, не строя ответа. Случай латентный — с Zed промпт всегда приходит
    запросом с id, — но состояние на диске обязано быть правдивым независимо от того,
    наблюдается ли ложь сегодня.

    Пример использования:
        response = finalize_active_turn(session, stop_reason="cancelled")
    """
    return finish_turn(
        session,
        cause=TurnEndCause.COMPLETED,
        stop_reason=normalize_stop_reason(stop_reason),
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
    if not isinstance(phase, AwaitingPermission):
        return False
    # `all`, а не «последнее ожидание»: незакрытых разрешений может быть несколько
    # (P1-61), и достаточно одного, которое turn обязан дождаться, чтобы автозавершение
    # было запрещено. Обратное дало бы завершение turn'а поверх живого ожидания.
    return all(wait.keep_tool_pending for wait in phase.waits)

"""Создание и финализация prompt-turn — wire-поверхность вокруг доменного `TurnState`.

**Класс сведён к живому (P2-54, 2026-08-12).** Из восьми методов вызывающих в
продакшене имели два; остальные шесть — `mark_cancel_requested`, `is_cancel_requested`,
`set_turn_phase`, `get_turn_phase`, `resolve_stop_reason`, `should_handle_cancel` — не
звал никто, только тесты. Это не случайный мусор, а след трёх переездов: фаза turn'а
уехала в домен (`TurnState.transition_to`, ADR-008 шаг 2), снятие turn'а получило
владельца (`turn_runtime.finish_turn`, шаг 5.2), а нормализация stop reason жила в
`prompt.normalization` и использовалась живым путём оттуда. Каждый переезд оставлял
здесь копию, и копии переставали вызываться, но не удалялись — тот же класс, что
`finalize_active_turn` и `clear_active_turn`, удалённые шагом 5.2.

Ответственность после сведения: создать `TurnState` и нормализовать stop reason на
финализации. Проверка переходов фазы, снятие turn'а и его персистентность здесь не
живут — у каждого из них свой владелец.
"""

from __future__ import annotations

import structlog

from codelab.server.domain.session import Session, TurnState
from codelab.server.domain.value_objects import Running

from ...messages import JsonRpcId
from .prompt.normalization import normalize_stop_reason

logger = structlog.get_logger()


class TurnLifecycleManager:
    """Создаёт состояние turn'а и нормализует stop reason на финализации."""

    def create_active_turn(
        self,
        session_id: str,
        prompt_request_id: JsonRpcId | None,
    ) -> TurnState:
        """Создает новое состояние active turn.

        Args:
            session_id: ID сессии
            prompt_request_id: ID входящего prompt request

        Returns:
            Инициализированный TurnState (доменное состояние turn'а)
        """
        turn = TurnState(
            prompt_request_id=prompt_request_id,
            session_id=session_id,
            phase=Running(),
        )
        logger.debug(
            "active turn created",
            session_id=session_id,
            request_id=prompt_request_id,
        )
        return turn

    def finalize_turn(
        self,
        session: Session,
        stop_reason: str,
    ) -> str | None:
        """Финализирует active turn и возвращает нормализованный stop reason.

        Нормализация идёт через `prompt.normalization.normalize_stop_reason` — тот же
        нормализатор, которым пользуется живой путь ответа. Прежде здесь лежала вторая
        копия с тем же множеством значений; предупреждение о подмене перенесено в общий
        нормализатор, а не потеряно вместе с копией.

        Args:
            session: Состояние сессии
            stop_reason: Причина завершения turn

        Returns:
            Нормализованный stop reason или None если нет active turn
        """
        if session.active_turn is None:
            logger.warning(
                "cannot finalize turn: no active turn",
                session_id=str(session.id),
            )
            return None

        normalized_reason = normalize_stop_reason(stop_reason)

        logger.debug(
            "turn finalized",
            session_id=str(session.id),
            stop_reason=normalized_reason,
        )

        return normalized_reason

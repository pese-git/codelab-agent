"""Менеджер управления фазами и жизненным циклом prompt-turn.

Содержит логику управления состоянием turn'а, фазами и stop reasons.
"""

from __future__ import annotations

import structlog

from codelab.server.domain.session import Session, TurnState
from codelab.server.domain.value_objects import Running, TurnPhase

from ...messages import ACPMessage, JsonRpcId
from ..state import PromptDirectives

# Используем structlog для структурированного логирования
logger = structlog.get_logger()


class TurnLifecycleManager:
    """Управляет фазами и жизненным циклом prompt-turn.

    Ответственность:
    - Управление фазами turn (running → completed)
    - Обработка cancel requests (set cancel_requested flag)
    - Finalization с корректным stop reason
    - Эмиссия финальных notifications
    """

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

    def mark_cancel_requested(self, session: Session) -> None:
        """Устанавливает флаг cancel_requested в active turn.

        Args:
            session: Состояние сессии
        """
        if session.active_turn is None:
            logger.warning(
                "cannot mark cancel: no active turn",
                session_id=str(session.id),
            )
            return

        session.mark_turn_cancel_requested()
        logger.debug(
            "cancel requested marked",
            session_id=str(session.id),
        )

    def is_cancel_requested(self, session: Session) -> bool:
        """Проверяет, был ли запрошен cancel для активного turn.

        Args:
            session: Состояние сессии

        Returns:
            True если cancel был запрошен
        """
        if session.active_turn is None:
            return False
        return session.active_turn.cancel_requested

    def set_turn_phase(
        self,
        session: Session,
        phase: TurnPhase,
    ) -> None:
        """Переходит turn в новую фазу.

        Проверка перехода принадлежит агрегату (`TurnState.transition_to`, ADR-008
        шаг 2): раньше матрица жила здесь строками и **не применялась ни разу** —
        у этого метода не было вызывающих в продакшене, а фазу писали прямыми
        присваиваниями. Здесь остаётся wire-поверхность: проверка наличия turn'а.

        Args:
            session: Состояние сессии
            phase: Новая фаза
        """
        if session.active_turn is None:
            logger.warning(
                "cannot set turn phase: no active turn",
                session_id=str(session.id),
            )
            return

        current_phase = session.active_turn.phase
        if not session.active_turn.transition_to(phase):
            return

        logger.debug(
            "turn phase changed",
            session_id=str(session.id),
            from_phase=current_phase.wire_name,
            to_phase=phase.wire_name,
        )

    def get_turn_phase(self, session: Session) -> str:
        """Возвращает имя текущей фазы turn.

        Args:
            session: Состояние сессии

        Returns:
            Имя фазы или 'unknown' если turn'а нет
        """
        if session.active_turn is None:
            return "unknown"
        return session.active_turn.phase.wire_name

    def resolve_stop_reason(
        self,
        directives: PromptDirectives,
        supported_reasons: set[str] | None = None,
    ) -> str:
        """Определяет stop reason для текущего turn.

        Приоритет:
        1. directives.forced_stop_reason (если установлен)
        2. Производная от directives (cancel, tool_pending)
        3. Default: 'end_turn'

        Args:
            directives: Исходящие директивы
            supported_reasons: Поддерживаемые значения (default: ACP spec)

        Returns:
            Нормализованный stop reason
        """
        if supported_reasons is None:
            supported_reasons = _get_supported_stop_reasons()

        # Если явно установлен stop reason, используем его
        if directives.forced_stop_reason:
            return _normalize_stop_reason(
                directives.forced_stop_reason,
                supported_reasons,
            )

        # Определяем на основе директив
        # ACP не определяет отдельный stop reason для pending-tool сценария,
        # поэтому используем стандартное завершение turn.
        if directives.keep_tool_pending:
            return "end_turn"

        # Default
        return "end_turn"

    def finalize_turn(
        self,
        session: Session,
        stop_reason: str,
    ) -> str | None:
        """Финализирует active turn и возвращает нормализованный stop reason.

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

        # Нормализуем stop reason
        supported = _get_supported_stop_reasons()
        normalized_reason = _normalize_stop_reason(stop_reason, supported)

        logger.debug(
            "turn finalized",
            session_id=str(session.id),
            stop_reason=normalized_reason,
        )

        return normalized_reason

    def finalize_active_turn(self, session: Session, *, stop_reason: str) -> ACPMessage | None:
        """Финализирует текущий active turn и очищает его состояние.

        Args:
            session: Состояние сессии
            stop_reason: Причина завершения (e.g., "end_turn", "cancelled")

        Returns:
            ACPMessage response для исходного `session/prompt` или None если нет active_turn
        """
        active_turn = session.active_turn
        if active_turn is None or active_turn.prompt_request_id is None:
            return None

        session.clear_active_turn()
        return ACPMessage.response(
            active_turn.prompt_request_id,
            {"stopReason": stop_reason},
        )

    def clear_active_turn(self, session: Session) -> None:
        """Очищает active turn (устанавливает в None).

        Args:
            session: Состояние сессии
        """
        if session.active_turn is None:
            return

        session_id = str(session.id)
        session.clear_active_turn()
        logger.debug(
            "active turn cleared",
            session_id=session_id,
        )

    def should_handle_cancel(self, session: Session) -> bool:
        """Проверяет, нужно ли обрабатывать cancel.

        Returns:
            True если есть active_turn и cancel_requested=True
        """
        if session.active_turn is None:
            return False
        return session.active_turn.cancel_requested




def _get_supported_stop_reasons() -> set[str]:
    """Спецификация поддерживаемых stop reasons из ACP.

    Returns:
        Множество поддерживаемых stop reasons
    """
    return {
        "end_turn",
        "max_tokens",
        "max_turn_requests",
        "refusal",
        "cancelled",
    }


def _normalize_stop_reason(
    candidate: str,
    supported: set[str],
) -> str:
    """Нормализует stop reason к поддерживаемому значению.

    Если candidate не поддерживается, возвращает 'end_turn'.

    Args:
        candidate: Предложенный stop reason
        supported: Множество поддерживаемых значений

    Returns:
        Нормализованный stop reason
    """
    if candidate in supported:
        return candidate

    logger.warning(
        "stop reason not supported, using default",
        requested=candidate,
        supported=supported,
    )
    return "end_turn"



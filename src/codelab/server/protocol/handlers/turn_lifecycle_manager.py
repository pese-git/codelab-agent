"""Менеджер управления фазами и жизненным циклом prompt-turn.

Содержит логику управления ActiveTurnState, фазами и stop reasons.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from ...messages import ACPMessage, JsonRpcId
from ..state import ActiveTurnState, PromptDirectives, SessionState

if TYPE_CHECKING:
    pass

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
    ) -> ActiveTurnState:
        """Создает новое состояние active turn.

        Args:
            session_id: ID сессии
            prompt_request_id: ID входящего prompt request

        Returns:
            Инициализированный ActiveTurnState
        """
        turn = ActiveTurnState(
            prompt_request_id=prompt_request_id,
            session_id=session_id,
            phase="running",
        )
        logger.debug(
            "active turn created",
            session_id=session_id,
            request_id=prompt_request_id,
        )
        return turn

    def mark_cancel_requested(self, session: SessionState) -> None:
        """Устанавливает флаг cancel_requested в active turn.

        Args:
            session: Состояние сессии
        """
        if session.active_turn is None:
            logger.warning(
                "cannot mark cancel: no active turn",
                session_id=session.session_id,
            )
            return

        session.active_turn.cancel_requested = True
        logger.debug(
            "cancel requested marked",
            session_id=session.session_id,
        )

    def is_cancel_requested(self, session: SessionState) -> bool:
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
        session: SessionState,
        phase: str,
    ) -> None:
        """Переходит turn в новую фазу.

        Args:
            session: Состояние сессии
            phase: Новая фаза (running, awaiting_permission,
                awaiting_client_rpc, completing)
        """
        if session.active_turn is None:
            logger.warning(
                "cannot set turn phase: no active turn",
                session_id=session.session_id,
            )
            return

        allowed_phases = _get_allowed_phases()
        if phase not in allowed_phases:
            logger.warning(
                "invalid turn phase",
                phase=phase,
                allowed=allowed_phases,
            )
            return

        current_phase = session.active_turn.phase
        if not _validate_phase_transition(current_phase, phase):
            logger.warning(
                "invalid phase transition",
                from_phase=current_phase,
                to_phase=phase,
            )
            return

        session.active_turn.phase = phase
        logger.debug(
            "turn phase changed",
            session_id=session.session_id,
            from_phase=current_phase,
            to_phase=phase,
        )

    def get_turn_phase(self, session: SessionState) -> str:
        """Возвращает текущую фазу turn.

        Args:
            session: Состояние сессии

        Returns:
            Текущая фаза или 'unknown' если턴а нет
        """
        if session.active_turn is None:
            return "unknown"
        return session.active_turn.phase

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
        session: SessionState,
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
                session_id=session.session_id,
            )
            return None

        # Нормализуем stop reason
        supported = _get_supported_stop_reasons()
        normalized_reason = _normalize_stop_reason(stop_reason, supported)

        logger.debug(
            "turn finalized",
            session_id=session.session_id,
            stop_reason=normalized_reason,
        )

        return normalized_reason

    def finalize_active_turn(self, session: SessionState, *, stop_reason: str) -> ACPMessage | None:
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

        session.active_turn = None
        return ACPMessage.response(
            active_turn.prompt_request_id,
            {"stopReason": stop_reason},
        )

    def clear_active_turn(self, session: SessionState) -> None:
        """Очищает active turn (устанавливает в None).

        Args:
            session: Состояние сессии
        """
        if session.active_turn is None:
            return

        session_id = session.session_id
        session.active_turn = None
        logger.debug(
            "active turn cleared",
            session_id=session_id,
        )

    def should_handle_cancel(self, session: SessionState) -> bool:
        """Проверяет, нужно ли обрабатывать cancel.

        Returns:
            True если есть active_turn и cancel_requested=True
        """
        if session.active_turn is None:
            return False
        return session.active_turn.cancel_requested


def _get_allowed_phases() -> set[str]:
    """Матрица допустимых фаз жизненного цикла.

    Returns:
        Множество разрешенных фаз
    """
    return {
        "running",
        "awaiting_permission",
        "awaiting_client_rpc",
        "completing",
    }


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


def _validate_phase_transition(
    from_phase: str,
    to_phase: str,
) -> bool:
    """Проверяет валидность перехода между фазами.

    Допустимые переходы:
    - running -> любая
    - awaiting_permission -> running, completing
    - awaiting_client_rpc -> running, completing
    - completing -> (финальная)

    Args:
        from_phase: Текущая фаза
        to_phase: Целевая фаза

    Returns:
        True если переход валиден
    """
    # От running можно перейти в любую фазу
    if from_phase == "running":
        return True

    # От awaiting_permission можно вернуться в running или завершить
    if from_phase == "awaiting_permission":
        return to_phase in {"running", "completing"}

    # От awaiting_client_rpc можно вернуться в running или завершить
    if from_phase == "awaiting_client_rpc":
        return to_phase in {"running", "completing"}

    # completing - финальная фаза
    if from_phase == "completing":
        return to_phase == "completing"

    return False

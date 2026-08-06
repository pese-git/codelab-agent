"""SessionCancelCommandHandler - обработчик метода session/cancel.

Отменяет текущий prompt turn в сессии.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from ...messages import ACPMessage
from ...storage import SessionRepository
from ..handlers.prompt_orchestrator import PromptOrchestrator
from ..state import ProtocolOutcome

logger = structlog.get_logger()


class SessionCancelCommandHandler:
    """Обработчик метода session/cancel.

    Отвечает за:
    - Отмену активного prompt turn
    - Прерывание LLM-запроса
    - Отправку followup responses для deferred turns

    Транзакция работает доменным агрегатом через `SessionRepository.transaction`
    (фаза D ADR-006, инвариант владения ADR-007).

    Attributes:
        method_name: Имя обрабатываемого метода.
    """

    method_name = "session/cancel"

    def __init__(
        self,
        repository: SessionRepository,
        orchestrator_provider: Callable[[], Awaitable[PromptOrchestrator]],
        llm_adapter: Any | None = None,
    ) -> None:
        """Инициализирует обработчик.

        Args:
            repository: Доменный порт хранилища сессий.
            orchestrator_provider: Функция для получения PromptOrchestrator.
            llm_adapter: Адаптер LLM для cancellation.
        """
        self._repository = repository
        self._orchestrator_provider = orchestrator_provider
        self._llm_adapter = llm_adapter

    async def handle(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает метод session/cancel.

        Args:
            message: Входящее JSON-RPC сообщение.

        Returns:
            ProtocolOutcome с результатом отмены.
        """
        params = message.params or {}

        orchestrator = await self._orchestrator_provider()
        session_id = params.get("sessionId")
        logger.info("session_cancel_received", session_id=session_id, request_id=message.id)

        # Валидация до области транзакции: область записывает при успешном выходе,
        # а запись штампует `updated_at` — отклонённый запрос не должен менять
        # «последнюю активность» (правило ADR-007).
        if not isinstance(session_id, str):
            logger.warning("session_cancel_missing_session_id", params=params)
            return ProtocolOutcome(response=None, notifications=[])

        notifications: list[ACPMessage] = []
        followup: list[ACPMessage] = []
        cancel_response: ACPMessage | None = None

        async with self._repository.transaction(session_id) as session:
            if session is None:
                logger.warning("session_cancel_session_not_found", session_id=session_id)
                return ProtocolOutcome(
                    response=ACPMessage.response(message.id, None),
                    notifications=[],
                )

            # Снимается ДО обработки: отмена снимает active turn, и после неё фазу уже
            # не прочитать.
            turn_on_cancel = session.active_turn
            phase_on_cancel = turn_on_cancel.phase.wire_name if turn_on_cancel else "no_turn"
            permission_id_on_cancel = (
                turn_on_cancel.permission_request_id if turn_on_cancel else None
            )

            outcome = orchestrator.handle_cancel(
                request_id=message.id,
                params=params,
                session=session,
            )
            notifications = list(outcome.notifications)

            # Прерываем активный LLM-запрос
            if self._llm_adapter is not None:
                await self._llm_adapter.cancel_prompt(session_id)
                logger.info("agent_llm_task_cancelled", session_id=session_id)

            # Отложенный turn: раньше его снятие было ВТОРОЙ записью подряд по той
            # же сессии; в области транзакции хватает одного коммита на выходе.
            followup = list(outcome.followup_responses)
            pending = session.runtime.pending_prompt_response
            if pending is not None:
                followup.append(
                    ACPMessage.response(
                        pending["request_id"],
                        {"stopReason": pending["stop_reason"]},
                    )
                )
                session.runtime.pending_prompt_response = None

            # Для notification (id=None) не отправляем response
            cancel_response = outcome.response or (
                ACPMessage.response(message.id, None) if message.id is not None else None
            )

            # Логируем ПОСЛЕ сбора followup: иначе по логу не видно, ответили ли
            # клиенту на отложенный `session/prompt` — счётчик показывал состояние
            # до того, как этот ответ добавлен.
            logger.info(
                "session_cancel_handled",
                session_id=session_id,
                notifications_count=len(notifications),
                followup_count=len(followup),
                deferred_prompt_answered=pending is not None,
                active_turn_cleared=session.active_turn is None,
                # Фаза turn'а на входе отмены. Без неё по логу не отличить «отмена
                # пришла, когда разрешения никто не ждал» от «пауза не доехала до
                # диска, поэтому tombstone не записан»: прогон 2026-08-06 дал
                # `cancelled_permission_requests: []` при отмене ровно в момент
                # ожидания, и различить причины было нечем.
                phase_on_cancel=phase_on_cancel,
                permission_tombstone_written=permission_id_on_cancel is not None,
            )

        return ProtocolOutcome(
            response=cancel_response,
            notifications=notifications,
            followup_responses=followup,
        )

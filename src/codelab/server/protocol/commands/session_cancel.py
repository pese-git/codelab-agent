"""SessionCancelCommandHandler - обработчик метода session/cancel.

Отменяет текущий prompt turn в сессии.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from ...messages import ACPMessage
from ...storage import SessionStorage
from ..handlers.prompt_orchestrator import PromptOrchestrator
from ..state import ProtocolOutcome

logger = structlog.get_logger()


class SessionCancelCommandHandler:
    """Обработчик метода session/cancel.

    Отвечает за:
    - Отмену активного prompt turn
    - Прерывание LLM-запроса
    - Отправку followup responses для deferred turns

    Attributes:
        method_name: Имя обрабатываемого метода.
    """

    method_name = "session/cancel"

    def __init__(
        self,
        storage: SessionStorage,
        orchestrator_provider: Callable[[], Awaitable[PromptOrchestrator]],
        llm_adapter: Any | None = None,
    ) -> None:
        """Инициализирует обработчик.

        Args:
            storage: Хранилище сессий.
            orchestrator_provider: Функция для получения PromptOrchestrator.
            llm_adapter: Адаптер LLM для cancellation.
        """
        self._storage = storage
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

        if not isinstance(session_id, str):
            logger.warning("session_cancel_missing_session_id", params=params)
            return ProtocolOutcome(response=None, notifications=[])

        session = await self._storage.load_session(session_id)
        if session is None:
            return ProtocolOutcome(
                response=ACPMessage.response(message.id, None),
                notifications=[],
            )

        outcome = orchestrator.handle_cancel(
            request_id=message.id,
            params=params,
            session=session,
        )
        logger.info(
            "session_cancel_handled",
            session_id=session_id,
            notifications_count=len(outcome.notifications),
            followup_count=len(outcome.followup_responses),
        )

        # Прерываем активный LLM-запрос
        if self._llm_adapter is not None:
            await self._llm_adapter.cancel_prompt(session_id)
            logger.info("agent_llm_task_cancelled", session_id=session_id)

        await self._storage.save_session(session)

        # Обрабатываем deferred turn
        followup: list[ACPMessage] = list(outcome.followup_responses)
        pending = session.pending_prompt_response
        if pending is not None:
            followup.append(
                ACPMessage.response(
                    pending["request_id"],
                    {"stopReason": pending["stop_reason"]},
                )
            )
            session.pending_prompt_response = None
            await self._storage.save_session(session)

        # Для notification (id=None) не отправляем response
        cancel_response = outcome.response or (
            ACPMessage.response(message.id, None) if message.id is not None else None
        )

        return ProtocolOutcome(
            response=cancel_response,
            notifications=outcome.notifications,
            followup_responses=followup,
        )

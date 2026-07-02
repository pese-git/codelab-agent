"""PermissionResponseCommandHandler - обработчик ответа на permission request.

Обрабатывает response клиента на session/request_permission.
"""

from __future__ import annotations

from typing import Any

import structlog

from ...messages import ACPMessage, JsonRpcId
from ...storage import SessionStorage
from ..handlers import permissions
from ..handlers.permission_manager import PermissionManager
from ..state import ProtocolOutcome

logger = structlog.get_logger()


class PermissionResponseCommandHandler:
    """Обработчик метода session/request_permission_response.

    Отвечает за:
    - Обработку ответа клиента на permission request
    - Обновление policy для allow_always/reject_always
    - Обновление статуса tool call

    Attributes:
        method_name: Имя обрабатываемого метода.
    """

    method_name = "session/request_permission_response"

    def __init__(
        self,
        storage: SessionStorage,
    ) -> None:
        """Инициализирует обработчик.

        Args:
            storage: Хранилище сессий.
        """
        self._storage = storage

    async def handle(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает ответ на permission request.

        Args:
            message: Входящее JSON-RPC сообщение.

        Returns:
            ProtocolOutcome с результатом обработки.
        """
        if message.id is None:
            return ProtocolOutcome(
                response=ACPMessage.error_response(
                    None, code=-32600, message="Invalid Request: id is required"
                )
            )

        params = message.params or {}
        return await self._handle_permission_response(message.id, params)

    async def _handle_permission_response(
        self,
        request_id: JsonRpcId,
        params: dict[str, Any],
    ) -> ProtocolOutcome:
        """Обрабатывает response на session/request_permission от клиента."""
        session_id = params.get("sessionId", "")

        # Найти сессию по permission request ID
        session = await permissions.find_session_by_permission_request_id(
            request_id, self._storage
        )

        if session is None:
            # Проверить, был ли request отменен (late response handling)
            cancelled_session = await permissions.find_session_with_cancelled_permission(
                request_id, self._storage
            )
            if cancelled_session is not None:
                logger.debug(
                    "ignoring_late_response_on_cancelled_permission_request",
                    request_id=request_id,
                    session_id=cancelled_session.session_id,
                )
                cancelled_session.cancelled_permission_requests.discard(request_id)
                await self._storage.save_session(cancelled_session)
                return ProtocolOutcome(response=ACPMessage.response(request_id, {}))

            logger.warning(
                "permission_response_for_unknown_request",
                request_id=request_id,
            )
            return ProtocolOutcome(
                response=ACPMessage.error_response(
                    request_id,
                    code=-32603,
                    message="Unknown permission request",
                )
            )

        permission_manager = PermissionManager()

        result = params.get("result", {})

        # Извлечь решение из response
        outcome = permission_manager.extract_permission_outcome(result)
        option_id = permission_manager.extract_permission_option_id(result)

        if outcome != "selected" or option_id is None:
            logger.warning(
                "invalid_permission_response_format",
                request_id=request_id,
                session_id=session_id,
                outcome=outcome,
            )
            return ProtocolOutcome(
                response=ACPMessage.error_response(
                    request_id,
                    code=-32603,
                    message="Invalid permission response",
                )
            )

        # Получить tool_call_id из active_turn
        if session.active_turn is None or session.active_turn.permission_tool_call_id is None:
            logger.warning(
                "no_permission_tool_call_in_active_turn",
                request_id=request_id,
                session_id=session_id,
            )
            return ProtocolOutcome(
                response=ACPMessage.error_response(
                    request_id,
                    code=-32603,
                    message="No pending tool call",
                )
            )

        tool_call_id = session.active_turn.permission_tool_call_id

        # Сохранить policy если нужно
        acceptance_updates = permission_manager.build_permission_acceptance_updates(
            session,
            session_id,
            tool_call_id,
            option_id,
        )

        logger.debug(
            "permission_response_handled",
            request_id=request_id,
            session_id=session_id,
            option_id=option_id,
            tool_call_id=tool_call_id,
        )

        return ProtocolOutcome(
            response=ACPMessage.response(request_id, {}),
            notifications=acceptance_updates,
        )

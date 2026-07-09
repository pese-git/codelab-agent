"""ResponseRouter — маршрутизация ответов от клиента.

Инкапсулирует логику обработки входящих responses от клиента:
- Permission responses (session/request_permission_response)
- Client RPC responses (agent->client fs/* requests)
- Cancelled responses (late responses на отменённые запросы)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from ..messages import ACPMessage, JsonRpcId
from .handlers import permissions, prompt
from .state import ProtocolOutcome

if TYPE_CHECKING:
    from ..client_rpc.service import ClientRPCService
    from ..storage import SessionStorage
    from .pending_registry import PendingRequestRegistry

logger = structlog.get_logger()


class ResponseRouter:
    """Маршрутизирует ответы от клиента к соответствующим обработчикам.

    Отвечает за:
    - Обработку permission responses
    - Обработку client RPC responses
    - Обработку cancelled responses (late responses)

    Attributes:
        storage: Хранилище сессий.
        pending_registry: Реестр pending permission requests.
        client_rpc_service: Сервис для agent->client RPC.
    """

    def __init__(
        self,
        storage: SessionStorage,
        pending_registry: PendingRequestRegistry,
        client_rpc_service: ClientRPCService | None = None,
    ) -> None:
        """Инициализирует ResponseRouter.

        Args:
            storage: Хранилище сессий.
            pending_registry: Реестр pending permission requests.
            client_rpc_service: Сервис для agent->client RPC (опционально).
        """
        self._storage = storage
        self._pending_registry = pending_registry
        self._client_rpc_service = client_rpc_service

    async def handle_client_response(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает входящий response от клиента для server-originated requests.

        Сейчас используется для `session/request_permission`, отправленного ранее
        в рамках active prompt-turn.

        Args:
            message: Входящее JSON-RPC сообщение (response).

        Returns:
            ProtocolOutcome с результатом обработки.
        """
        if message.id is None:
            logger.debug("handle_client_response: ignoring message with no id")
            return ProtocolOutcome()

        logger.debug(
            "handle_client_response: routing response",
            request_id=message.id,
            has_result=message.result is not None,
        )

        # Пробуем разрешить как pending client RPC response
        resolved_client_rpc = await self._resolve_pending_client_rpc_response(
            request_id=message.id,
            result=message.result,
            error=message.error.model_dump(exclude_none=True)
            if message.error is not None
            else None,
        )
        if resolved_client_rpc is not None:
            logger.debug(
                "handle_client_response: resolved as pending client RPC",
                request_id=message.id,
            )
            return resolved_client_rpc

        # Пробуем пробросить в ClientRPCService
        if self._client_rpc_service is not None and self._client_rpc_service.has_pending_request(
            message.id
        ):
            logger.debug(
                "forwarding_client_response_to_client_rpc_service",
                request_id=message.id,
                has_error=message.error is not None,
            )
            self._client_rpc_service.handle_response(message.to_dict())
            return ProtocolOutcome()

        # Пробуем обработать как cancelled client RPC response
        if await permissions.consume_cancelled_client_rpc_response(message.id, self._storage):
            logger.debug(
                "handle_client_response: consumed cancelled client RPC response",
                request_id=message.id,
            )
            return ProtocolOutcome()

        # Пробуем обработать как cancelled permission response
        if await permissions.consume_cancelled_permission_response(message.id, self._storage):
            logger.debug(
                "handle_client_response: consumed cancelled permission response",
                request_id=message.id,
            )
            return ProtocolOutcome()

        # Пробуем разрешить как permission response
        logger.debug(
            "handle_client_response: attempting to resolve permission response",
            request_id=message.id,
        )
        resolved = await self._resolve_permission_response(message.id, message.result)
        if resolved is None:
            logger.debug(
                "handle_client_response: _resolve_permission_response returned None",
                request_id=message.id,
            )
            return ProtocolOutcome()

        logger.debug(
            "handle_client_response: permission response resolved successfully",
            request_id=message.id,
        )
        return resolved

    async def _resolve_pending_client_rpc_response(
        self,
        *,
        request_id: JsonRpcId,
        result: Any,
        error: dict[str, Any] | None,
    ) -> ProtocolOutcome | None:
        """Обрабатывает response на ожидаемый agent->client fs/* request.

        Args:
            request_id: ID запроса.
            result: Результат из response.
            error: Ошибка из response (опционально).

        Returns:
            ProtocolOutcome если обработано, иначе None.
        """
        session = await prompt.find_session_by_pending_client_request_id(request_id, self._storage)
        if session is None:
            return None

        return prompt.resolve_pending_client_rpc_response_impl(
            session=session,
            request_id=request_id,
            result=result,
            error=error,
        )

    async def _resolve_permission_response(
        self,
        permission_request_id: JsonRpcId,
        result: Any,
    ) -> ProtocolOutcome | None:
        """Применяет решение по permission-request к активному prompt-turn.

        Args:
            permission_request_id: ID permission request.
            result: Результат из response.

        Returns:
            ProtocolOutcome если обработано, иначе None.
        """
        logger.debug(
            "_resolve_permission_response: searching for session",
            permission_request_id=permission_request_id,
        )
        session = await permissions.find_session_by_permission_request_id(
            permission_request_id, self._storage
        )
        if session is None:
            logger.debug(
                "_resolve_permission_response: session not found for permission_request_id",
                permission_request_id=permission_request_id,
            )
            return None

        logger.debug(
            "_resolve_permission_response: session found, resolving",
            permission_request_id=permission_request_id,
            session_id=session.session_id,
            active_turn_exists=session.active_turn is not None,
            active_turn_perm_request_id=(
                session.active_turn.permission_request_id if session.active_turn else None
            ),
            active_turn_perm_tool_call_id=(
                session.active_turn.permission_tool_call_id if session.active_turn else None
            ),
        )
        return prompt.resolve_permission_response_impl(
            session=session,
            permission_request_id=permission_request_id,
            result=result,
        )

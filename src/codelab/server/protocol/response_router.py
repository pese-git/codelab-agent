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
    from ..storage import SessionRepository, SessionStorage
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
        repository: SessionRepository,
        pending_registry: PendingRequestRegistry,
        client_rpc_service: ClientRPCService | None = None,
    ) -> None:
        """Инициализирует ResponseRouter.

        Args:
            storage: Хранилище сессий (wire; пути, ещё не переехавшие на домен).
            repository: Доменный порт хранилища (write-фаза D4-d1, ADR-006).
            pending_registry: Реестр pending permission requests.
            client_rpc_service: Сервис для agent->client RPC (опционально).
        """
        self._storage = storage
        self._repository = repository
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

        # Сначала — процессный реестр ожидающих RPC: это словарь, тогда как поиск по
        # состоянию сессий ниже делает полный скан хранилища (90 мс на 30 сессиях).
        # Наборы идентификаторов не пересекаются: запросы `ClientRPCService` живут в
        # его futures, а `pending_external_request` заводит директивный путь, который
        # через сервис не проходит. Живой путь fs/terminal идёт именно через сервис,
        # поэтому раньше каждый его ответ платил за скан впустую.
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

        # Пробуем разрешить как pending client RPC response (директивный путь)
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

        # Пробуем обработать как cancelled client RPC response
        if await permissions.consume_cancelled_client_rpc_response(message.id, self._repository):
            logger.debug(
                "handle_client_response: consumed cancelled client RPC response",
                request_id=message.id,
            )
            return ProtocolOutcome()

        # Пробуем обработать как cancelled permission response
        if await permissions.consume_cancelled_permission_response(message.id, self._repository):
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
        session_id = await prompt.find_session_id_by_pending_client_request_id(
            request_id, self._repository
        )
        if session_id is None:
            return None

        # Область транзакции: до неё ответ применялся к копии, которую никто не
        # сохранял, — тот же класс, что P1-49 на permission-пути. Здесь это било
        # реже (путь директивный, `pending_client_request` в проде почти не
        # заводится), но терялось то же: статус вызова, снятый pending и финал turn'а.
        async with self._repository.transaction(session_id) as session:
            if session is None:
                logger.warning(
                    "client_rpc_response_session_gone",
                    request_id=request_id,
                    session_id=session_id,
                )
                return None

            outcome = prompt.resolve_pending_client_rpc_response_impl(
                session=session,
                request_id=request_id,
                result=result,
                error=error,
            )
            logger.info(
                "client_rpc_response_applied",
                session_id=session_id,
                request_id=request_id,
                applied=outcome is not None,
                chains_next_request=bool(
                    session.active_turn is not None
                    and session.active_turn.pending_external_request is not None
                ),
            )
            return outcome

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
        # Сначала — процессный реестр исходящих запросов: он знает сессию по
        # идентификатору за O(1). Скан ниже сравнивает единственный
        # `permission_request_id` из документа, поэтому для любого запроса, кроме
        # последнего, сессию не находил — так терялся второй одновременный
        # запрос (P1-61). Скан остаётся фолбэком: сессии, записанные до этой
        # версии, реестру неизвестны.
        session_id = self._pending_registry.session_for(permission_request_id)
        if session_id is None:
            logger.debug(
                "_resolve_permission_response: not in outgoing registry, scanning",
                permission_request_id=permission_request_id,
            )
            session_id = await permissions.find_session_id_by_permission_request_id(
                permission_request_id, self._repository
            )
        if session_id is None:
            logger.debug(
                "_resolve_permission_response: session not found for permission_request_id",
                permission_request_id=permission_request_id,
            )
            return None

        # Область транзакции: до неё решение применялось к копии, которую никто не
        # сохранял — запомненная политика, снятые permission-идентификаторы и статус
        # вызова не доживали до диска (P1-49, причина P2-46). Фоновое исполнение
        # вызова запускается уже после выхода из области (`core.handle`), поэтому
        # оно читает зафиксированное состояние, а не полуправку.
        async with self._repository.transaction(session_id) as session:
            if session is None:
                logger.warning(
                    "permission_response_session_gone",
                    permission_request_id=permission_request_id,
                    session_id=session_id,
                )
                return None

            logger.debug(
                "_resolve_permission_response: session found, resolving",
                permission_request_id=permission_request_id,
                session_id=session_id,
                active_turn_exists=session.active_turn is not None,
                active_turn_perm_request_id=(
                    session.active_turn.permission_request_id if session.active_turn else None
                ),
                active_turn_perm_tool_call_id=(
                    session.active_turn.permission_tool_call_id if session.active_turn else None
                ),
            )
            outcome = prompt.resolve_permission_response_impl(
                session=session,
                permission_request_id=permission_request_id,
                result=result,
            )
            # Запрос закрыт — реестр обязан его забыть, иначе он рос бы на всю
            # жизнь соединения, а `session/load` считал бы отвеченное разрешение
            # живым и не чистил бы turn.
            self._pending_registry.forget(permission_request_id)
            logger.info(
                "permission_response_applied",
                session_id=session_id,
                permission_request_id=permission_request_id,
                applied=outcome is not None,
                schedules_tool=outcome is not None and outcome.pending_tool_execution is not None,
                remembered_policy=len(session.permissions.policy),
                outstanding_requests=self._pending_registry.outstanding_outgoing,
            )
            return outcome

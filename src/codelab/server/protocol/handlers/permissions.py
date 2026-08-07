"""Обработчики методов управления разрешениями.

Содержит логику обработки session/request_permission и related.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from codelab.server.storage.document import SessionDocument

from ...domain.session import Session
from ...messages import JsonRpcId
from ...storage import SessionRepository, SessionStorage

if TYPE_CHECKING:
    from .global_policy_manager import GlobalPolicyManager


async def find_session_by_permission_request_id(
    permission_request_id: JsonRpcId,
    storage: SessionStorage,
) -> SessionDocument | None:
    """Ищет сессию с активным turn, ожидающим ответ по permission-request.

    Пример использования:
        session = await find_session_by_permission_request_id("perm_1", storage)
    """
    import structlog

    logger = structlog.get_logger()

    cursor = None
    sessions_checked = 0
    while True:
        page, cursor = await storage.list_sessions(cursor=cursor, limit=100)
        for session in page:
            sessions_checked += 1
            active_turn = session.active_turn
            if active_turn is None:
                continue
            logger.debug(
                "find_session_by_permission_request_id: checking session",
                session_id=session.session_id,
                active_turn_perm_request_id=active_turn.permission_request_id,
                looking_for=permission_request_id,
            )
            # Членство, а не сравнение с последним: незакрытых ожиданий может быть
            # несколько, и ответ приходит на любое из них (P1-61).
            if active_turn.awaits_permission_request(permission_request_id):
                logger.debug(
                    "find_session_by_permission_request_id: found matching session",
                    session_id=session.session_id,
                )
                return session
        if cursor is None:
            logger.debug(
                "find_session_by_permission_request_id: no match found",
                permission_request_id=permission_request_id,
                total_sessions_checked=sessions_checked,
            )
            return None


def extract_permission_outcome(result: Any) -> str | None:
    """Извлекает outcome из `session/request_permission` response.

    Поддерживает текущий ACP shape (`{"outcome": {"outcome": ...}}`) и
    legacy-вариант (`{"outcome": ...}`) для обратной совместимости.

    Пример использования:
        outcome = extract_permission_outcome(
            {"outcome": {"outcome": "selected", "optionId": "allow_once"}},
        )
    """

    if not isinstance(result, dict):
        return None

    nested_outcome = result.get("outcome")
    if isinstance(nested_outcome, dict):
        raw_value = nested_outcome.get("outcome")
        if isinstance(raw_value, str):
            return raw_value

    # Legacy fallback для старых клиентов.
    if isinstance(nested_outcome, str):
        return nested_outcome
    return None


def extract_permission_option_id(result: Any) -> str | None:
    """Извлекает `optionId` из `session/request_permission` response.

    Поддерживает ACP shape (`{"outcome": {"optionId": ...}}`) и legacy
    (`{"optionId": ...}`) формат для обратной совместимости.

    Пример использования:
        option_id = extract_permission_option_id(
            {"outcome": {"outcome": "selected", "optionId": "allow_once"}},
        )
    """

    if not isinstance(result, dict):
        return None

    nested_outcome = result.get("outcome")
    if isinstance(nested_outcome, dict):
        raw_option_id = nested_outcome.get("optionId")
        if isinstance(raw_option_id, str):
            return raw_option_id

    raw_option_id = result.get("optionId")
    if isinstance(raw_option_id, str):
        return raw_option_id
    return None


def resolve_permission_option_kind(
    option_id: str | None,
    permission_options: list[dict[str, Any]],
) -> str | None:
    """Возвращает kind permission-опции по ее `optionId`.

    Пример использования:
        kind = resolve_permission_option_kind("allow_once", options)
    """

    if option_id is None:
        return None
    for option in permission_options:
        if not isinstance(option, dict):
            continue
        if option.get("optionId") != option_id:
            continue
        kind_value = option.get("kind")
        if isinstance(kind_value, str):
            return kind_value
        return None
    return None


async def resolve_remembered_permission_decision(
    *,
    session: SessionDocument,
    tool_kind: str,
    global_manager: GlobalPolicyManager | None = None,
) -> str:
    """Возвращает применяемое policy-решение для tool kind с fallback chain.

    Fallback chain:
    1. Session policy (session.permission_policy)
    2. Global policy (global_manager.get_global_policy) если global_manager передан
    3. Ask user (default)

    Возвращаемые значения:
    - `allow`: выполнить tool-call без запроса permission.
    - `reject`: отклонить tool-call без запроса permission.
    - `ask`: запросить решение у клиента через `session/request_permission`.

    Args:
        session: Текущая сессия
        tool_kind: Тип инструмента (execute, read, write, etc.)
        global_manager: Optional GlobalPolicyManager для fallback на global policies

    Пример использования:
        decision = await resolve_remembered_permission_decision(
            session=state,
            tool_kind="execute",
            global_manager=manager,
        )
    """

    # 1. Check session policy
    session_decision = session.get_permission_policy(tool_kind)
    if session_decision is not None:
        if session_decision == "allow_always":
            return "allow"
        if session_decision == "reject_always":
            return "reject"

    # 2. Check global policy (if manager provided)
    if global_manager is not None:
        global_decision = await global_manager.get_global_policy(tool_kind)
        if global_decision is not None:
            if global_decision == "allow_always":
                return "allow"
            if global_decision == "reject_always":
                return "reject"

    # 3. Default: ask user
    return "ask"


def build_permission_options() -> list[dict[str, Any]]:
    """Возвращает варианты решения для `session/request_permission`.

    Пример использования:
        options = build_permission_options()
    """

    return [
        {
            "optionId": "allow_once",
            "name": "Allow once",
            "kind": "allow_once",
        },
        {
            "optionId": "allow_always",
            "name": "Always allow this tool",
            "kind": "allow_always",
        },
        {
            "optionId": "reject_once",
            "name": "Reject once",
            "kind": "reject_once",
        },
        {
            "optionId": "reject_always",
            "name": "Always reject this tool",
            "kind": "reject_always",
        },
    ]


async def consume_cancelled_permission_response(
    request_id: JsonRpcId,
    repository: SessionRepository,
) -> bool:
    """Поглощает late-response на ранее отмененный permission-request.

    Возвращает `True`, если идентификатор найден в canceled-tombstones и
    удален; иначе `False`.

    Пример использования:
        if await consume_cancelled_permission_response("perm_1", repository):
            ...
    """
    async for session in repository.iter_sessions():
        if not session.is_permission_cancelled(request_id):
            continue
        session.uncancel_permission_request(request_id)
        await repository.save_session(session)
        return True
    return False


async def find_session_id_by_permission_request_id(
    request_id: JsonRpcId,
    repository: SessionRepository,
) -> str | None:
    """Ищет id сессии, чей активный turn ждёт этот permission-request.

    Возвращает именно **id**, а не агрегат: мутировать найденную на обходе копию
    нельзя — решение применяется в области транзакции, которая берёт свою
    (write-model, `SessionRepository.iter_sessions`).

    Пример использования:
        session_id = await find_session_id_by_permission_request_id("perm_1", repository)
    """
    async for session in repository.iter_sessions():
        active_turn = session.active_turn
        if active_turn is None:
            continue
        if active_turn.permission_wait_for(request_id) is not None:
            return str(session.id)
    return None


async def find_session_with_cancelled_permission(
    request_id: JsonRpcId,
    repository: SessionRepository,
) -> Session | None:
    """Ищет сессию с отменённым permission request в tombstones.

    Возвращает доменный агрегат: вызывающий снимает tombstone и сохраняет
    (write-model, см. `SessionRepository.iter_sessions`).

    Пример использования:
        session = await find_session_with_cancelled_permission("perm_1", repository)
    """
    async for session in repository.iter_sessions():
        if session.is_permission_cancelled(request_id):
            return session
    return None


async def consume_cancelled_client_rpc_response(
    request_id: JsonRpcId,
    repository: SessionRepository,
) -> bool:
    """Поглощает late-response на ранее отмененный agent->client RPC.

    Возвращает `True`, если идентификатор найден в canceled-tombstones и
    удален; иначе `False`.

    Пример использования:
        if await consume_cancelled_client_rpc_response("rpc_1", repository):
            ...
    """
    async for session in repository.iter_sessions():
        if not session.is_client_rpc_cancelled(request_id):
            continue
        session.uncancel_client_rpc_request(request_id)
        await repository.save_session(session)
        return True
    return False

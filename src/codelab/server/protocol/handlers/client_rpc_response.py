"""Обработка ответов на agent->client RPC (fs/*, terminal/*).

Диспетчеризация response по виду ожидаемого client-request
(`PendingExternalRequest.kind`) реализована таблицей обработчиков — по одному на
каждый вид fs/terminal-операции. Это разбивает исходную функцию с цикломатической
сложностью 51 на набор самостоятельных обработчиков и тонкий диспетчер
(см. doc/internals/tech-debt.md, P0-2).

Работает доменным агрегатом внутри транзакции репозитория (транзакция 7 фазы D,
ADR-006): мутации — доменные сеймы, wire остаётся в построении ACP-сообщений.
Форму `tool_call_update` собирает единственный рендер
(`prompt.tool_call_updates.tool_call_status_notification`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from ...domain.session import PendingExternalRequest
from ...domain.session import Session as DomainSession
from ...domain.value_objects import ToolCallStatus
from ...messages import ACPMessage, JsonRpcId
from ...storage import SessionRepository
from ..state import ProtocolOutcome
from ..turn_runtime import TurnEndCause, finish_turn
from .prompt.tool_call_updates import tool_call_status_notification
from .session import session_info_notification

logger = structlog.get_logger()


def _status_notifications(
    *,
    session: DomainSession,
    changed: bool,
    session_id: str,
    tool_call_id: str,
    status: ToolCallStatus,
    content: list[dict[str, Any]] | None = None,
    raw_output: dict[str, Any] | None = None,
) -> list[ACPMessage]:
    """Нотификация о смене статуса — только если состояние её подтверждает.

    Раньше нотификация строилась независимо от исхода перехода, и отклонённый
    матрицей переход давал клиенту `completed` при `pending` на диске (P2-55).
    Клиент верит нотификации, а состояние остаётся своим — расхождение тем хуже,
    что вызов остаётся нетерминальным и его потом «отменяет» скан незавершённых.

    `update_status` возвращает `False` по двум разным причинам, и смешивать их
    нельзя — иначе лог соврёт при разборе:

    * **переход отклонён матрицей** (вызов есть) — нотификация не отправляется:
      молчание вместо лжи. Отказ уже записан `tool_call_status_transition_rejected`.
    * **вызова нет в состоянии** — поведение сохранено: клиент о вызове знает
      (создание ему уже уходило), и путь отказа обязан его уведомить. Это
      расхождение другого рода, поэтому оно логируется отдельным событием и не
      меняется здесь.
    """
    if changed:
        known = True
    else:
        known = session.tool_calls.get(tool_call_id) is not None
        if known:
            logger.warning(
                "tool_call_status_notification_suppressed",
                session_id=session_id,
                tool_call_id=tool_call_id,
                requested_status=status.value,
                reason="переход отклонён матрицей — нотификация солгала бы клиенту",
            )
            return []
        logger.warning(
            "tool_call_status_notification_for_unknown_call",
            session_id=session_id,
            tool_call_id=tool_call_id,
            requested_status=status.value,
        )
    return [
        tool_call_status_notification(
            session_id=session_id,
            tool_call_id=tool_call_id,
            status=status.value,
            content=content,
            raw_output=raw_output,
        )
    ]


def _finalize_turn(session: DomainSession, *, stop_reason: str = "end_turn") -> ACPMessage | None:
    """Снять active turn и построить ответ на исходный `session/prompt`.

    Доменный аналог `prompt.turn_state.finalize_active_turn`: очистка turn'а —
    операция агрегата, а сборка JSON-RPC ответа остаётся wire.

    Turn **без** идентификатора исходного запроса снимается тоже (P2-54, 2026-08-12):
    прежде guard выходил раньше снятия, и на диске оставался `active_turn` с фазой
    `waiting_client_rpc` у turn'а, чей клиентский запрос уже разрешён. Ответа при этом
    не строится — `finish_turn` вернёт `None`, потому что отвечать некому.
    """
    return finish_turn(
        session,
        cause=TurnEndCause.CLIENT_RPC_FINISHED,
        stop_reason=stop_reason,
    )


async def find_session_id_by_pending_client_request_id(
    request_id: JsonRpcId,
    repository: SessionRepository,
) -> str | None:
    """Ищет id сессии, чей активный turn ждёт этот agent->client запрос.

    Возвращает **id**, а не агрегат: мутировать копию с обхода нельзя — ответ
    применяется к копии, которую берёт транзакция (см. `iter_sessions`).

    Пример использования:
        session_id = await find_session_id_by_pending_client_request_id("req_1", repository)
    """
    async for session in repository.iter_sessions():
        active_turn = session.active_turn
        if active_turn is None or active_turn.pending_external_request is None:
            continue
        if active_turn.pending_external_request.request_id == request_id:
            return str(session.id)
    return None


@dataclass(frozen=True)
class _ContinueToCompletion:
    """Сигнал обработчика: добавить notifications и финализировать turn.

    Возвращается ветками, которые завершают tool call (fs_read, fs_write,
    terminal_release) и должны пройти через общий «хвост» финализации.
    """

    notifications: list[ACPMessage]


# Результат per-kind обработчика:
#   * ProtocolOutcome        — вернуть как есть (продолжение terminal-цепочки/ошибка);
#   * _ContinueToCompletion  — добавить notifications и финализировать turn;
#   * None                   — невалидный/незавершаемый ответ, обработка прекращается.
_HandlerResult = ProtocolOutcome | _ContinueToCompletion | None


def _handle_fs_read(
    *,
    session: DomainSession,
    session_id: str,
    pending: PendingExternalRequest,
    result: Any,
) -> _HandlerResult:
    if not isinstance(result, dict) or not isinstance(result.get("content"), str):
        return finalize_failed_client_rpc_request(
            session=session,
            session_id=session_id,
            tool_call_id=pending.tool_call_id,
            failure_text="Invalid fs/read_text_file response.",
        )
    content_text = result["content"]
    content = [
        {
            "type": "content",
            "content": {
                "type": "text",
                "text": content_text,
            },
        }
    ]
    changed = session.tool_calls.update_status(
        pending.tool_call_id, ToolCallStatus.COMPLETED, content=content
    )
    return _ContinueToCompletion(
        _status_notifications(
            session=session,
            changed=changed,
            session_id=session_id,
            tool_call_id=pending.tool_call_id,
            status=ToolCallStatus.COMPLETED,
            content=content,
        )
    )


def _handle_fs_write(
    *,
    session: DomainSession,
    session_id: str,
    pending: PendingExternalRequest,
    result: Any,
) -> _HandlerResult:
    if not isinstance(result, dict):
        return finalize_failed_client_rpc_request(
            session=session,
            session_id=session_id,
            tool_call_id=pending.tool_call_id,
            failure_text="Invalid fs/write_text_file response.",
        )
    old_text: str | None = None
    new_text = pending.expected_new_text or ""
    if isinstance(result.get("oldText"), str):
        old_text = result["oldText"]
    if isinstance(result.get("newText"), str):
        new_text = result["newText"]

    diff_content = [
        {
            "type": "diff",
            "path": pending.path,
            "oldText": old_text,
            "newText": new_text,
        }
    ]
    changed = session.tool_calls.update_status(
        pending.tool_call_id, ToolCallStatus.COMPLETED, content=diff_content
    )
    return _ContinueToCompletion(
        _status_notifications(
            session=session,
            changed=changed,
            session_id=session_id,
            tool_call_id=pending.tool_call_id,
            status=ToolCallStatus.COMPLETED,
            content=diff_content,
        )
    )


def _handle_terminal_create(
    *,
    session: DomainSession,
    session_id: str,
    pending: PendingExternalRequest,
    result: Any,
) -> _HandlerResult:
    if session.active_turn is None:
        return None

    terminal_id = None
    if isinstance(result, dict) and isinstance(result.get("terminalId"), str):
        terminal_id = result["terminalId"]
    if terminal_id is None:
        changed = session.tool_calls.update_status(pending.tool_call_id, ToolCallStatus.FAILED)
        notifications: list[ACPMessage] = _status_notifications(
            session=session,
            changed=changed,
            session_id=session_id,
            tool_call_id=pending.tool_call_id,
            status=ToolCallStatus.FAILED,
        )
        done = _finalize_turn(session)
        return ProtocolOutcome(
            notifications=notifications,
            followup_responses=[done] if done is not None else [],
        )

    changed = session.tool_calls.update_status(pending.tool_call_id, ToolCallStatus.IN_PROGRESS)
    notifications = _status_notifications(
        session=session,
        changed=changed,
        session_id=session_id,
        tool_call_id=pending.tool_call_id,
        status=ToolCallStatus.IN_PROGRESS,
        content=[{"type": "terminal", "terminalId": terminal_id}],
    )

    output_request = ACPMessage.request(
        "terminal/output",
        {
            "sessionId": session_id,
            "terminalId": terminal_id,
        },
    )
    if output_request.id is None:
        return None
    session.active_turn.pending_external_request = PendingExternalRequest(
        request_id=output_request.id,
        kind="terminal_output",
        tool_call_id=pending.tool_call_id,
        path=pending.path,
        terminal_id=terminal_id,
    )
    notifications.append(output_request)
    return ProtocolOutcome(notifications=notifications)


def _issue_terminal_followup(
    session: DomainSession,
    session_id: str,
    *,
    method: str,
    next_kind: str,
    pending: PendingExternalRequest,
    terminal_id: str,
    terminal_output: str | None,
    terminal_truncated: bool | None,
    terminal_exit_code: int | None = None,
    terminal_signal: str | None = None,
) -> ProtocolOutcome | None:
    """Отправляет следующий запрос terminal-цепочки и переводит pending в next_kind.

    Общий шаг переходов output->release, output->wait_for_exit, wait_for_exit->release.
    Возвращает None, если запрос не удалось сформировать.
    """
    assert session.active_turn is not None
    request = ACPMessage.request(
        method,
        {
            "sessionId": session_id,
            "terminalId": terminal_id,
        },
    )
    if request.id is None:
        return None
    session.active_turn.pending_external_request = PendingExternalRequest(
        request_id=request.id,
        kind=next_kind,
        tool_call_id=pending.tool_call_id,
        path=pending.path,
        terminal_id=terminal_id,
        terminal_output=terminal_output,
        terminal_exit_code=terminal_exit_code,
        terminal_signal=terminal_signal,
        terminal_truncated=terminal_truncated,
    )
    return ProtocolOutcome(notifications=[request])


@dataclass(frozen=True)
class _TerminalExitStatus:
    """Распарсенный exitStatus из terminal/output."""

    exit_code: int | None
    signal: str | None


def _parse_terminal_exit_status(raw: dict[str, Any]) -> _TerminalExitStatus | None:
    """Валидирует и парсит exitStatus. Возвращает None, если структура невалидна."""
    exit_code = raw.get("exitCode")
    signal = raw.get("signal")
    if exit_code is not None and not isinstance(exit_code, int):
        return None
    if signal is not None and not isinstance(signal, str):
        return None
    return _TerminalExitStatus(
        exit_code=exit_code if isinstance(exit_code, int) else None,
        signal=signal if isinstance(signal, str) else None,
    )


def _handle_terminal_output(
    *,
    session: DomainSession,
    session_id: str,
    pending: PendingExternalRequest,
    result: Any,
) -> _HandlerResult:
    if session.active_turn is None:
        return None

    terminal_id = pending.terminal_id
    if terminal_id is None:
        return None
    if not isinstance(result, dict) or not isinstance(result.get("output"), str):
        return finalize_failed_client_rpc_request(
            session=session,
            session_id=session_id,
            tool_call_id=pending.tool_call_id,
            failure_text="Invalid terminal/output response.",
        )
    output_text = result["output"]
    output_truncated = result["truncated"] if isinstance(result.get("truncated"), bool) else False

    raw_exit_status = result.get("exitStatus")
    output_exit_code: int | None = None
    output_signal: str | None = None
    has_exit_status = raw_exit_status is not None
    if has_exit_status:
        exit_status = (
            _parse_terminal_exit_status(raw_exit_status)
            if isinstance(raw_exit_status, dict)
            else None
        )
        if exit_status is None:
            return finalize_failed_client_rpc_request(
                session=session,
                session_id=session_id,
                tool_call_id=pending.tool_call_id,
                failure_text="Invalid terminal/output response.",
            )
        output_exit_code = exit_status.exit_code
        output_signal = exit_status.signal

    # Если terminal/output уже содержит exitStatus, можно сразу release без wait_for_exit.
    if has_exit_status:
        return _issue_terminal_followup(
            session,
            session_id,
            method="terminal/release",
            next_kind="terminal_release",
            pending=pending,
            terminal_id=terminal_id,
            terminal_output=output_text,
            terminal_truncated=output_truncated,
            terminal_exit_code=output_exit_code,
            terminal_signal=output_signal,
        )

    return _issue_terminal_followup(
        session,
        session_id,
        method="terminal/wait_for_exit",
        next_kind="terminal_wait_for_exit",
        pending=pending,
        terminal_id=terminal_id,
        terminal_output=output_text,
        terminal_truncated=output_truncated,
    )


def _handle_terminal_wait_for_exit(
    *,
    session: DomainSession,
    session_id: str,
    pending: PendingExternalRequest,
    result: Any,
) -> _HandlerResult:
    if session.active_turn is None:
        return None

    terminal_id = pending.terminal_id
    if terminal_id is None:
        return None
    if not isinstance(result, dict):
        return finalize_failed_client_rpc_request(
            session=session,
            session_id=session_id,
            tool_call_id=pending.tool_call_id,
            failure_text="Invalid terminal/wait_for_exit response.",
        )
    exit_code = result["exitCode"] if isinstance(result.get("exitCode"), int) else None
    signal = result["signal"] if isinstance(result.get("signal"), str) else None

    return _issue_terminal_followup(
        session,
        session_id,
        method="terminal/release",
        next_kind="terminal_release",
        pending=pending,
        terminal_id=terminal_id,
        terminal_output=pending.terminal_output,
        terminal_truncated=pending.terminal_truncated,
        terminal_exit_code=exit_code,
        terminal_signal=signal,
    )


def _handle_terminal_release(
    *,
    session: DomainSession,
    session_id: str,
    pending: PendingExternalRequest,
    result: Any,
) -> _HandlerResult:
    terminal_id = pending.terminal_id
    if terminal_id is None:
        return None
    if not isinstance(result, dict):
        return finalize_failed_client_rpc_request(
            session=session,
            session_id=session_id,
            tool_call_id=pending.tool_call_id,
            failure_text="Invalid terminal/release response.",
        )
    completion_text = f"Terminal command finished with exit code {pending.terminal_exit_code}."
    if pending.terminal_exit_code is None:
        completion_text = "Terminal command finished."
    if pending.terminal_signal is not None:
        completion_text = f"{completion_text} Signal: {pending.terminal_signal}."
    if pending.terminal_truncated:
        completion_text = f"{completion_text} Output was truncated."
    if pending.terminal_output:
        completion_text = f"{completion_text} Output: {pending.terminal_output}"

    completed_content = [
        {
            "type": "terminal",
            "terminalId": terminal_id,
        },
        {
            "type": "content",
            "content": {
                "type": "text",
                "text": completion_text,
            },
        },
    ]
    changed = session.tool_calls.update_status(
        pending.tool_call_id,
        ToolCallStatus.COMPLETED,
        content=completed_content,
    )
    return _ContinueToCompletion(
        _status_notifications(
            session=session,
            changed=changed,
            session_id=session_id,
            tool_call_id=pending.tool_call_id,
            status=ToolCallStatus.COMPLETED,
            content=completed_content,
            raw_output={
                "exitCode": pending.terminal_exit_code,
                "signal": pending.terminal_signal,
                "truncated": pending.terminal_truncated,
            },
        )
    )


# Таблица диспетчеризации: вид ожидаемого client-request -> обработчик его response.
_CLIENT_RPC_RESPONSE_HANDLERS = {
    "fs_read": _handle_fs_read,
    "fs_write": _handle_fs_write,
    "terminal_create": _handle_terminal_create,
    "terminal_output": _handle_terminal_output,
    "terminal_wait_for_exit": _handle_terminal_wait_for_exit,
    "terminal_release": _handle_terminal_release,
}


def _complete_resolved_client_rpc(
    session: DomainSession,
    session_id: str,
    notifications: list[ACPMessage],
) -> ProtocolOutcome:
    """Общий «хвост» для завершающих ветвей: очищает pending и финализирует turn."""
    assert session.active_turn is not None
    session.active_turn.pending_external_request = None
    session.mark_updated()
    notifications.append(
        session_info_notification(
            session_id=session_id,
            title=None,
            updated_at=session.updated_at,
        )
    )
    completed = _finalize_turn(session)
    return ProtocolOutcome(
        notifications=notifications,
        followup_responses=[completed] if completed is not None else [],
    )


def resolve_pending_client_rpc_response_impl(
    *,
    session: DomainSession,
    request_id: JsonRpcId,
    result: Any,
    error: dict[str, Any] | None,
) -> ProtocolOutcome | None:
    """Реализация обработки response на ожидаемый agent->client fs/* request.

    Диспетчеризует по виду ожидаемого запроса (``pending.kind``) на
    соответствующий обработчик; завершающие ветви проходят через общий хвост
    финализации turn.

    Пример использования:
        outcome = resolve_pending_client_rpc_response_impl(
            session=session,
            request_id="req_1",
            result={"content": "ok"},
            error=None,
        )
    """
    if session.active_turn is None:
        return None
    pending = session.active_turn.pending_external_request
    if pending is None:
        return None

    session_id = str(session.id)

    if error is not None:
        raw_message = error.get("message")
        error_message = raw_message if isinstance(raw_message, str) else ""
        failure_suffix = f": {error_message}" if error_message else ""
        return finalize_failed_client_rpc_request(
            session=session,
            session_id=session_id,
            tool_call_id=pending.tool_call_id,
            failure_text=f"Client RPC request failed{failure_suffix}",
        )

    handler = _CLIENT_RPC_RESPONSE_HANDLERS.get(pending.kind)
    if handler is None:
        return None

    handled = handler(session=session, session_id=session_id, pending=pending, result=result)
    if isinstance(handled, _ContinueToCompletion):
        return _complete_resolved_client_rpc(session, session_id, handled.notifications)
    return handled


def finalize_failed_client_rpc_request(
    *,
    session: DomainSession,
    session_id: str,
    tool_call_id: str,
    failure_text: str,
) -> ProtocolOutcome:
    """Финализирует prompt-turn после неуспешного или невалидного client RPC.

    Пример использования:
        return finalize_failed_client_rpc_request(
            session=state,
            session_id="sess_1",
            tool_call_id="call_1",
            failure_text="Invalid terminal/output response.",
        )
    """
    changed = session.tool_calls.update_status(tool_call_id, ToolCallStatus.FAILED)
    failure_notifications = _status_notifications(
        session=session,
        changed=changed,
        session_id=session_id,
        tool_call_id=tool_call_id,
        status=ToolCallStatus.FAILED,
        content=[{"type": "content", "content": {"type": "text", "text": failure_text}}],
    )
    session.mark_updated()
    session_info = session_info_notification(
        session_id=session_id,
        title=None,
        updated_at=session.updated_at,
    )
    failed = _finalize_turn(session)
    return ProtocolOutcome(
        notifications=[*failure_notifications, session_info],
        followup_responses=[failed] if failed is not None else [],
    )

"""Подготовка исходящих fs/* и terminal/* client-RPC + проверки runtime-возможностей."""

from __future__ import annotations

from pathlib import Path

from ....domain.session import PendingExternalRequest, Session
from ....messages import ACPMessage
from ...state import PreparedFsClientRequest, PromptDirectives
from .tool_call_state import create_tool_call


def normalize_session_path(cwd: str, candidate: str) -> str | None:
    """Преобразует путь из slash-команды в абсолютный путь в рамках cwd.

    Пример использования:
        path = normalize_session_path("/tmp", "README.md")
    """

    if not isinstance(candidate, str) or not candidate.strip():
        return None
    candidate_path = Path(candidate)
    if candidate_path.is_absolute():
        return str(candidate_path)
    return str(Path(cwd) / candidate_path)


def can_use_fs_client_rpc(session: Session, kind: str) -> bool:
    """Проверяет доступность fs/* client RPC для указанной операции.

    Пример использования:
        enabled = can_use_fs_client_rpc(session, "fs_read")
    """

    caps = session.config.runtime_capabilities
    if caps is None:
        return False
    if kind == "fs_read":
        return caps.fs_read
    if kind == "fs_write":
        return caps.fs_write
    return False


def can_use_terminal_client_rpc(session: Session) -> bool:
    """Проверяет доступность terminal/* client RPC в текущем runtime.

    Пример использования:
        enabled = can_use_terminal_client_rpc(session)
    """

    caps = session.config.runtime_capabilities
    if caps is None:
        return False
    return caps.terminal


def build_fs_client_request(
    *,
    session: Session,
    session_id: str,
    directives: PromptDirectives,
) -> PreparedFsClientRequest | None:
    """Готовит исходящий fs/* request и связанный tool_call lifecycle.

    Пример использования:
        prepared = build_fs_client_request(
            session=state,
            session_id="sess_1",
            directives=directives,
        )
    """

    if directives.fs_read_path is not None:
        target_path = normalize_session_path(session.config.cwd, directives.fs_read_path)
        if target_path is None:
            return None
        tool_call_id = create_tool_call(
            session=session,
            title="Read text file",
            kind="read",
            # Вызов начинает работу здесь же: нотификация уходит клиенту вместе с
            # самим `fs/read_text_file`, и всё время ожидания ответа он выполняется,
            # а не ждёт запуска. `pending` вместо этого оставлял состояние в «не
            # начат», из-за чего завершение упиралось в запрет `pending → completed`
            # и на диске статус расходился с тем, что уже ушло клиенту (P2-55).
            status="in_progress",
        )
        created = ACPMessage.notification(
            "session/update",
            {
                "sessionId": session_id,
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": tool_call_id,
                    "title": "Read text file",
                    "kind": "read",
                    "status": "in_progress",
                    "locations": [{"path": target_path}],
                },
            },
        )
        fs_request = ACPMessage.request(
            "fs/read_text_file",
            {
                "sessionId": session_id,
                "path": target_path,
            },
        )
        if fs_request.id is None:
            return None
        pending = PendingExternalRequest(
            request_id=fs_request.id,
            kind="fs_read",
            tool_call_id=tool_call_id,
            path=target_path,
        )
        return PreparedFsClientRequest(
            kind="fs_read",
            messages=[created, fs_request],
            pending_request=pending,
        )

    if directives.fs_write_path is not None and directives.fs_write_content is not None:
        target_path = normalize_session_path(session.config.cwd, directives.fs_write_path)
        if target_path is None:
            return None
        tool_call_id = create_tool_call(
            session=session,
            title="Write text file",
            kind="edit",
            # См. комментарий в fs_read-ветке: запись начинается вместе с отправкой RPC.
            status="in_progress",
        )
        created = ACPMessage.notification(
            "session/update",
            {
                "sessionId": session_id,
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": tool_call_id,
                    "title": "Write text file",
                    "kind": "edit",
                    "status": "in_progress",
                    "locations": [{"path": target_path}],
                },
            },
        )
        fs_request = ACPMessage.request(
            "fs/write_text_file",
            {
                "sessionId": session_id,
                "path": target_path,
                "content": directives.fs_write_content,
            },
        )
        if fs_request.id is None:
            return None
        pending = PendingExternalRequest(
            request_id=fs_request.id,
            kind="fs_write",
            tool_call_id=tool_call_id,
            path=target_path,
            expected_new_text=directives.fs_write_content,
        )
        return PreparedFsClientRequest(
            kind="fs_write",
            messages=[created, fs_request],
            pending_request=pending,
        )

    return None


def build_terminal_client_request(
    *,
    session: Session,
    session_id: str,
    directives: PromptDirectives,
) -> PreparedFsClientRequest | None:
    """Готовит исходящий terminal/create request и tool_call lifecycle.

    Возвращает структуру того же формата, что и fs-подготовка, чтобы
    использовать общий пайплайн pending client RPC.

    Пример использования:
        prepared = build_terminal_client_request(
            session=state,
            session_id="sess_1",
            directives=directives,
        )
    """

    if directives.terminal_command is None:
        return None

    tool_call_id = create_tool_call(
        session=session,
        title="Run terminal command",
        kind="execute",
    )
    created = ACPMessage.notification(
        "session/update",
        {
            "sessionId": session_id,
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": tool_call_id,
                "title": "Run terminal command",
                "kind": "execute",
                "status": "pending",
                "rawInput": {
                    "command": directives.terminal_command,
                },
            },
        },
    )
    terminal_create_request = ACPMessage.request(
        "terminal/create",
        {
            "sessionId": session_id,
            "command": directives.terminal_command,
        },
    )
    if terminal_create_request.id is None:
        return None

    pending = PendingExternalRequest(
        request_id=terminal_create_request.id,
        kind="terminal_create",
        tool_call_id=tool_call_id,
        path=directives.terminal_command,
    )
    return PreparedFsClientRequest(
        kind="terminal_create",
        messages=[created, terminal_create_request],
        pending_request=pending,
    )

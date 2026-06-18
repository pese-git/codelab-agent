"""Обработчик управления agent→client RPC запросами.

Содержит логику проверки capabilities, подготовки fs/* и terminal/* requests,
управления pending client request state и обработки response.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ...messages import ACPMessage
from ..state import (
    PendingClientRequestState,
    PreparedFsClientRequest,
    PromptDirectives,
    SessionState,
)

if TYPE_CHECKING:
    pass


class ClientRPCHandler:
    """Управляет agent→client RPC запросами (fs/*, terminal/*).

    Инкапсулирует логику проверки доступности RPC capabilities,
    нормализации путей, подготовки fs/read, fs/write и terminal/create
    requests, а также управления pending request state.
    """

    def can_use_fs_rpc(
        self,
        session: SessionState,
        kind: str,
    ) -> bool:
        """Проверяет доступность fs/* RPC для указанной операции.

        Args:
            session: Состояние сессии
            kind: Тип операции ('fs_read' или 'fs_write')

        Returns:
            True если runtime_capabilities имеет соответствующую capability
        """
        caps = session.runtime_capabilities
        if caps is None:
            return False

        if kind == "fs_read":
            return caps.fs_read
        if kind == "fs_write":
            return caps.fs_write

        return False

    def can_use_terminal_rpc(self, session: SessionState) -> bool:
        """Проверяет доступность terminal/* RPC.

        Args:
            session: Состояние сессии

        Returns:
            True если runtime_capabilities содержит terminal capability
        """
        caps = session.runtime_capabilities
        if caps is None:
            return False
        return caps.terminal

    def can_run_tools(self, session: SessionState) -> bool:
        """Проверяет общую доступность tool-runtime.

        Tool-runtime доступен, если есть хотя бы одна из capabilities:
        terminal, fs_read или fs_write.

        Args:
            session: Состояние сессии

        Returns:
            True если есть хотя бы одна capability
        """
        caps = session.runtime_capabilities
        if caps is None:
            return False
        return caps.terminal or caps.fs_read or caps.fs_write

    def normalize_path(self, cwd: str, candidate: str) -> str | None:
        """Преобразует путь в абсолютный в рамках cwd.

        - Если candidate уже абсолютный, оставляет как есть
        - Если relative, присоединяет к cwd
        - Если пусто/невалидно, возвращает None

        Args:
            cwd: Текущая рабочая директория (base path)
            candidate: Путь из directive (может быть absolute или relative)

        Returns:
            Нормализованный абсолютный путь, или None если невалиден
        """
        if not isinstance(candidate, str) or not candidate.strip():
            return None

        candidate_path = Path(candidate)
        if candidate_path.is_absolute():
            return str(candidate_path)

        return str(Path(cwd) / candidate_path)

    def prepare_fs_read_request(
        self,
        session: SessionState,
        session_id: str,
        directives: PromptDirectives,
    ) -> PreparedFsClientRequest | None:
        """Готовит fs/read_text_file request и связанный tool call.

        Args:
            session: Состояние сессии (будет обновлено)
            session_id: ID сессии
            directives: Prompt directives с fs_read_path

        Returns:
            PreparedFsClientRequest с tool_call и request, или None если невалидно
        """
        if directives.fs_read_path is None:
            return None

        # Проверяем доступность fs_read capability
        if not self.can_use_fs_rpc(session, "fs_read"):
            return None

        # Нормализуем путь
        target_path = self.normalize_path(session.cwd, directives.fs_read_path)
        if target_path is None:
            return None

        # Создаем tool call для отслеживания операции
        from .tool_call_handler import ToolCallHandler

        tool_handler = ToolCallHandler()
        tool_call_id = tool_handler.create_tool_call(
            session=session,
            title="Read text file",
            kind="read",
        )

        # Создаем notification о создании tool call
        created = tool_handler.build_tool_call_notification(
            session_id=session_id,
            tool_call_id=tool_call_id,
            title="Read text file",
            kind="read",
            locations=[{"path": target_path}],
        )

        # Создаем fs/read_text_file request
        fs_request = ACPMessage.request(
            "fs/read_text_file",
            {
                "sessionId": session_id,
                "path": target_path,
            },
        )
        if fs_request.id is None:
            return None

        # Создаем pending request state для корреляции response
        pending = PendingClientRequestState(
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

    def prepare_fs_write_request(
        self,
        session: SessionState,
        session_id: str,
        directives: PromptDirectives,
    ) -> PreparedFsClientRequest | None:
        """Готовит fs/write_text_file request и связанный tool call.

        Args:
            session: Состояние сессии (будет обновлено)
            session_id: ID сессии
            directives: Prompt directives с fs_write_path и fs_write_content

        Returns:
            PreparedFsClientRequest с tool_call и request, или None если невалидно
        """
        if directives.fs_write_path is None or directives.fs_write_content is None:
            return None

        # Проверяем доступность fs_write capability
        if not self.can_use_fs_rpc(session, "fs_write"):
            return None

        # Нормализуем путь
        target_path = self.normalize_path(session.cwd, directives.fs_write_path)
        if target_path is None:
            return None

        # Создаем tool call для отслеживания операции
        from .tool_call_handler import ToolCallHandler

        tool_handler = ToolCallHandler()
        tool_call_id = tool_handler.create_tool_call(
            session=session,
            title="Write text file",
            kind="edit",
        )

        # Создаем notification о создании tool call
        created = tool_handler.build_tool_call_notification(
            session_id=session_id,
            tool_call_id=tool_call_id,
            title="Write text file",
            kind="edit",
            locations=[{"path": target_path}],
        )

        # Создаем fs/write_text_file request
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

        # Создаем pending request state для корреляции response
        pending = PendingClientRequestState(
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

    def prepare_terminal_request(
        self,
        session: SessionState,
        session_id: str,
        directives: PromptDirectives,
    ) -> PreparedFsClientRequest | None:
        """Готовит terminal/create request и связанный tool call.

        Args:
            session: Состояние сессии (будет обновлено)
            session_id: ID сессии
            directives: Prompt directives с terminal_command

        Returns:
            PreparedFsClientRequest с tool_call и request, или None если невалидно
        """
        if directives.terminal_command is None:
            return None

        # Проверяем доступность terminal capability
        if not self.can_use_terminal_rpc(session):
            return None

        # Создаем tool call для отслеживания операции
        from .tool_call_handler import ToolCallHandler

        tool_handler = ToolCallHandler()
        tool_call_id = tool_handler.create_tool_call(
            session=session,
            title="Run terminal command",
            kind="execute",
        )

        # Создаем notification о создании tool call
        created = tool_handler.build_tool_call_notification(
            session_id=session_id,
            tool_call_id=tool_call_id,
            title="Run terminal command",
            kind="execute",
        )

        # Создаем terminal/create request
        terminal_request = ACPMessage.request(
            "terminal/create",
            {
                "sessionId": session_id,
                "command": directives.terminal_command,
            },
        )
        if terminal_request.id is None:
            return None

        # Создаем pending request state для корреляции response
        pending = PendingClientRequestState(
            request_id=terminal_request.id,
            kind="terminal_create",
            tool_call_id=tool_call_id,
            path=directives.terminal_command,
        )

        return PreparedFsClientRequest(
            kind="terminal_create",
            messages=[created, terminal_request],
            pending_request=pending,
        )

    def prepare_fs_request(
        self,
        session: SessionState,
        session_id: str,
        directives: PromptDirectives,
    ) -> PreparedFsClientRequest | None:
        """Помощник: выбирает между fs_read и fs_write на основе directives.

        Проверяет fs_read_path, затем fs_write_path и подготавливает
        соответствующий request.

        Args:
            session: Состояние сессии
            session_id: ID сессии
            directives: Prompt directives

        Returns:
            PreparedFsClientRequest для fs/read или fs/write, или None
        """
        if directives.fs_read_path is not None:
            return self.prepare_fs_read_request(session, session_id, directives)

        if directives.fs_write_path is not None:
            return self.prepare_fs_write_request(session, session_id, directives)

        return None

    def handle_pending_response(
        self,
        session: SessionState,
        session_id: str,
        kind: str,
        result: Any,
        error: dict[str, Any] | None,
    ) -> list[ACPMessage]:
        """Обрабатывает response на ожидаемый RPC request.

        Валидирует результат, обновляет tool call status и генерирует
        соответствующие notifications.

        Args:
            session: Состояние сессии (будет обновлено)
            session_id: ID сессии
            kind: Тип операции ('fs_read', 'fs_write', 'terminal_create')
            result: Результат от клиента (если success)
            error: Ошибка от клиента (если error)

        Returns:
            Список ACPMessage notifications об обновлении tool call
        """
        if session.active_turn is None:
            return []

        pending = session.active_turn.pending_client_request
        if pending is None:
            return []

        from .tool_call_handler import ToolCallHandler

        tool_handler = ToolCallHandler()
        notifications: list[ACPMessage] = []

        # Обработка ошибки
        if error is not None:
            error_message = error.get("message") if isinstance(error.get("message"), str) else ""
            failure_text = f"RPC request failed{f': {error_message}' if error_message else ''}"

            tool_handler.update_tool_call_status(
                session,
                pending.tool_call_id,
                "failed",
                content=[
                    {
                        "type": "content",
                        "content": {
                            "type": "text",
                            "text": failure_text,
                        },
                    }
                ],
            )
            notifications.append(
                tool_handler.build_tool_update_notification(
                    session_id=session_id,
                    tool_call_id=pending.tool_call_id,
                    status="failed",
                    content=[
                        {
                            "type": "content",
                            "content": {
                                "type": "text",
                                "text": failure_text,
                            },
                        }
                    ],
                )
            )
            return notifications

        # Обработка успеха для fs_read
        if kind == "fs_read":
            if not isinstance(result, dict) or not isinstance(result.get("content"), str):
                # Невалидный response format
                tool_handler.update_tool_call_status(
                    session,
                    pending.tool_call_id,
                    "failed",
                    content=[
                        {
                            "type": "content",
                            "content": {
                                "type": "text",
                                "text": "Invalid fs/read response format",
                            },
                        }
                    ],
                )
                notifications.append(
                    tool_handler.build_tool_update_notification(
                        session_id=session_id,
                        tool_call_id=pending.tool_call_id,
                        status="failed",
                        content=[
                            {
                                "type": "content",
                                "content": {
                                    "type": "text",
                                    "text": "Invalid fs/read response format",
                                },
                            }
                        ],
                    )
                )
            else:
                # Успешно прочитали файл
                content_text = result.get("content", "")
                tool_handler.update_tool_call_status(
                    session,
                    pending.tool_call_id,
                    "completed",
                    content=[
                        {
                            "type": "content",
                            "content": {
                                "type": "text",
                                "text": content_text,
                            },
                        }
                    ],
                )
                notifications.append(
                    tool_handler.build_tool_update_notification(
                        session_id=session_id,
                        tool_call_id=pending.tool_call_id,
                        status="completed",
                        content=[
                            {
                                "type": "content",
                                "content": {
                                    "type": "text",
                                    "text": content_text,
                                },
                            }
                        ],
                    )
                )

        # Обработка успеха для fs_write
        elif kind == "fs_write":
            if not isinstance(result, dict):
                # Невалидный response format
                tool_handler.update_tool_call_status(
                    session,
                    pending.tool_call_id,
                    "failed",
                    content=[
                        {
                            "type": "content",
                            "content": {
                                "type": "text",
                                "text": "Invalid fs/write response format",
                            },
                        }
                    ],
                )
                notifications.append(
                    tool_handler.build_tool_update_notification(
                        session_id=session_id,
                        tool_call_id=pending.tool_call_id,
                        status="failed",
                        content=[
                            {
                                "type": "content",
                                "content": {
                                    "type": "text",
                                    "text": "Invalid fs/write response format",
                                },
                            }
                        ],
                    )
                )
            else:
                # Успешно записали файл
                tool_handler.update_tool_call_status(
                    session,
                    pending.tool_call_id,
                    "completed",
                    content=[
                        {
                            "type": "content",
                            "content": {
                                "type": "text",
                                "text": "File written successfully",
                            },
                        }
                    ],
                )
                notifications.append(
                    tool_handler.build_tool_update_notification(
                        session_id=session_id,
                        tool_call_id=pending.tool_call_id,
                        status="completed",
                        content=[
                            {
                                "type": "content",
                                "content": {
                                    "type": "text",
                                    "text": "File written successfully",
                                },
                            }
                        ],
                    )
                )

        # Обработка успеха для terminal
        elif kind == "terminal_create":
            # Terminal response может содержать output
            output_text = ""
            if isinstance(result, dict):
                raw_output = result.get("output")
                if isinstance(raw_output, str):
                    output_text = raw_output

            tool_handler.update_tool_call_status(
                session,
                pending.tool_call_id,
                "completed",
                content=[
                    {
                        "type": "content",
                        "content": {
                            "type": "text",
                            "text": output_text or "Terminal command executed",
                        },
                    }
                ],
            )
            notifications.append(
                tool_handler.build_tool_update_notification(
                    session_id=session_id,
                    tool_call_id=pending.tool_call_id,
                    status="completed",
                    content=[
                        {
                            "type": "content",
                            "content": {
                                "type": "text",
                                "text": output_text or "Terminal command executed",
                            },
                        }
                    ],
                )
            )

        return notifications

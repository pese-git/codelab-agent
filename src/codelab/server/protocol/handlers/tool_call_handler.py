"""Обработчик управления жизненным циклом tool calls.

Содержит логику создания, обновления статуса и финализации tool calls
в контексте обработки prompt-turn.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...messages import ACPMessage
from ..state import SessionState, ToolCallState

if TYPE_CHECKING:
    pass


class ToolCallHandler:
    """Управляет жизненным циклом tool calls в prompt-turn.

    Инкапсулирует логику создания tool calls, обновления их статуса,
    построения notifications и отмены активных tool calls.
    """

    # Матрица допустимых переходов между статусами tool call
    _ALLOWED_TRANSITIONS: dict[str, set[str]] = {
        "pending": {"in_progress", "cancelled", "failed"},
        "in_progress": {"completed", "cancelled", "failed"},
        "completed": set(),
        "cancelled": set(),
        "failed": set(),
    }

    # Поддерживаемые tool kinds для нормализации
    _SUPPORTED_TOOL_KINDS: set[str] = {
        "read",
        "edit",
        "delete",
        "move",
        "search",
        "execute",
        "think",
        "fetch",
        "switch_mode",
        "other",
    }

    # Человекочитаемые titles для каждого kind
    _TOOL_TITLES: dict[str, str] = {
        "read": "Tool read operation",
        "edit": "Tool edit operation",
        "delete": "Tool delete operation",
        "move": "Tool move operation",
        "execute": "Tool execution",
        "search": "Tool search operation",
        "think": "Tool reasoning step",
        "fetch": "Tool fetch operation",
        "switch_mode": "Tool mode switch",
        "other": "Tool operation",
    }

    def can_run_tools(self, session: SessionState) -> bool:
        """Проверяет, доступен ли tool-runtime для текущей сессии.

        Tool-runtime доступен, если клиент заявил о наличии хотя бы одной
        из capability: terminal, fs_read или fs_write.

        Args:
            session: Состояние сессии

        Returns:
            True если есть хотя бы одна capability, иначе False
        """
        # До успешного initialize runtime-возможности не согласованы
        caps = session.runtime_capabilities
        if caps is None:
            return False
        return caps.terminal or caps.fs_read or caps.fs_write

    def create_tool_call(
        self,
        session: SessionState,
        *,
        title: str,
        kind: str,
        tool_name: str | None = None,
        tool_arguments: dict[str, Any] | None = None,
        tool_call_id_from_llm: str | None = None,
    ) -> str:
        """Создает новый tool call, возвращает его ID.

        Использует локально монотонный счетчик для генерации стабильных ID
        вида "call_NNN". Записывает ToolCallState в session.tool_calls.

        Args:
            session: Состояние сессии
            title: Название для UI (e.g., "Tool execution")
            kind: Категория tool (read, edit, delete, move, search, execute,
                think, fetch, switch_mode, other)
            tool_name: Имя инструмента в реестре для отложенного выполнения
            tool_arguments: Аргументы для выполнения инструмента
            tool_call_id_from_llm: ID tool call из ответа LLM (для связки в истории)

        Returns:
            ID вида "call_NNN" (e.g., "call_001", "call_002")
        """
        # Локально монотонный ID делает тесты предсказуемыми и читабельными
        session.tool_call_counter += 1
        tool_call_id = f"call_{session.tool_call_counter:03d}"
        session.tool_calls[tool_call_id] = ToolCallState(
            tool_call_id=tool_call_id,
            title=title,
            kind=kind,
            status="pending",
            tool_name=tool_name,
            tool_arguments=tool_arguments or {},
            tool_call_id_from_llm=tool_call_id_from_llm,
        )
        return tool_call_id

    def update_tool_call_status(
        self,
        session: SessionState,
        tool_call_id: str,
        status: str,
        *,
        content: list[dict[str, Any]] | None = None,
    ) -> None:
        """Обновляет статус tool call с проверкой допустимых переходов.

        Матрица допустимых переходов:
        - pending → in_progress, cancelled, failed
        - in_progress → completed, cancelled, failed
        - completed, cancelled, failed → (терминальные состояния)

        Если переход невалиден, игнорирует обновление.

        Args:
            session: Состояние сессии
            tool_call_id: ID tool call'а для обновления
            status: Новый статус
            content: Опциональный контент (результат tool call)
        """
        state = session.tool_calls.get(tool_call_id)
        if state is None:
            return

        # Явная матрица переходов защищает от нелегальных смен статуса
        next_states = self._ALLOWED_TRANSITIONS.get(state.status, set())
        if status not in next_states and status != state.status:
            return

        state.status = status
        if content is not None:
            state.content = content

    def build_tool_call_notification(
        self,
        session_id: str,
        tool_call_id: str,
        title: str,
        kind: str,
        locations: list[dict[str, str]] | None = None,
    ) -> ACPMessage:
        """Строит tool_call notification для отправки клиенту.

        Создает сообщение с информацией о новом tool call, включающее
        его идентификатор, title, kind и опциональные locations.

        Args:
            session_id: ID сессии
            tool_call_id: ID tool call'а
            title: Название для UI
            kind: Категория tool
            locations: Опциональные locations (e.g., file paths)

        Returns:
            ACPMessage типа notification с sessionUpdate="tool_call"
        """
        update_dict: dict[str, Any] = {
            "sessionUpdate": "tool_call",
            "toolCallId": tool_call_id,
            "title": title,
            "kind": kind,
            "status": "pending",
        }
        if locations is not None:
            update_dict["locations"] = locations

        return ACPMessage.notification(
            "session/update",
            {
                "sessionId": session_id,
                "update": update_dict,
            },
        )

    def build_tool_update_notification(
        self,
        session_id: str,
        tool_call_id: str,
        status: str,
        content: list[dict[str, Any]] | None = None,
    ) -> ACPMessage:
        """Строит tool_call_update notification для отправки клиенту.

        Создает сообщение об изменении статуса существующего tool call,
        опционально включая контент результата.

        Args:
            session_id: ID сессии
            tool_call_id: ID tool call'а
            status: Новый статус (in_progress, completed, cancelled, failed)
            content: Опциональный контент (результаты tool call)

        Returns:
            ACPMessage типа notification с sessionUpdate="tool_call_update"
        """
        update_dict: dict[str, Any] = {
            "sessionUpdate": "tool_call_update",
            "toolCallId": tool_call_id,
            "status": status,
        }
        if content is not None:
            update_dict["content"] = content

        return ACPMessage.notification(
            "session/update",
            {
                "sessionId": session_id,
                "update": update_dict,
            },
        )

    def build_executor_execution_updates(
        self,
        session: SessionState,
        session_id: str,
        tool_call_id: str,
        leave_running: bool = False,
    ) -> list[ACPMessage]:
        """Executor mode: генерирует lifecycle updates для tool execution.

        В режиме executor tool-runtime выполняется автоматически без запроса
        разрешения. Генерирует цепочку: in_progress → completed (или remains running).

        Args:
            session: Состояние сессии (будет обновлено)
            session_id: ID сессии
            tool_call_id: ID tool call'а
            leave_running: Если True, оставляет tool в статусе in_progress

        Returns:
            Список ACPMessage notifications для отправки клиенту
        """
        # Создаем notification о переходе в in_progress
        in_progress = self.build_tool_update_notification(
            session_id=session_id,
            tool_call_id=tool_call_id,
            status="in_progress",
        )
        self.update_tool_call_status(session, tool_call_id, "in_progress")

        if leave_running:
            return [in_progress]

        # Переводим в completed
        completed_content = [
            {
                "type": "content",
                "content": {
                    "type": "text",
                    "text": "Tool completed successfully.",
                },
            }
        ]
        self.update_tool_call_status(
            session,
            tool_call_id,
            "completed",
            content=completed_content,
        )
        completed = self.build_tool_update_notification(
            session_id=session_id,
            tool_call_id=tool_call_id,
            status="completed",
            content=completed_content,
        )
        return [in_progress, completed]

    def build_policy_execution_updates(
        self,
        session: SessionState,
        session_id: str,
        tool_call_id: str,
        allowed: bool,
    ) -> list[ACPMessage]:
        """Policy mode: генерирует updates после решения по разрешению.

        В режиме ask пользователь принимает решение о запуске tool.
        На основе решения (allowed/rejected) генерирует соответствующие
        notifications: completed (если allowed) или cancelled (если rejected).

        Args:
            session: Состояние сессии (будет обновлено)
            session_id: ID сессии
            tool_call_id: ID tool call'а
            allowed: True для разрешения, False для отказа

        Returns:
            Список ACPMessage notifications для отправки клиенту
        """
        if not allowed:
            # Пользователь отклонил выполнение
            self.update_tool_call_status(session, tool_call_id, "cancelled")
            return [
                self.build_tool_update_notification(
                    session_id=session_id,
                    tool_call_id=tool_call_id,
                    status="cancelled",
                )
            ]

        # Пользователь разрешил выполнение
        notifications: list[ACPMessage] = []

        # Переводим в in_progress
        self.update_tool_call_status(session, tool_call_id, "in_progress")
        notifications.append(
            self.build_tool_update_notification(
                session_id=session_id,
                tool_call_id=tool_call_id,
                status="in_progress",
            )
        )

        # Переводим в completed
        completed_content = [
            {
                "type": "content",
                "content": {
                    "type": "text",
                    "text": "Tool completed successfully.",
                },
            }
        ]
        self.update_tool_call_status(
            session,
            tool_call_id,
            "completed",
            content=completed_content,
        )
        notifications.append(
            self.build_tool_update_notification(
                session_id=session_id,
                tool_call_id=tool_call_id,
                status="completed",
                content=completed_content,
            )
        )
        return notifications

    def cancel_active_tools(
        self,
        session: SessionState,
        session_id: str,
    ) -> list[ACPMessage]:
        """Отменяет все активные (pending, in_progress) tool calls.

        Используется при отмене prompt-turn или других событиях,
        требующих отмены всех незавершенных tool calls.
        Игнорирует tool calls в терминальных состояниях.

        Args:
            session: Состояние сессии (будет обновлено)
            session_id: ID сессии

        Returns:
            Список ACPMessage notifications об отмене tool calls
        """
        notifications: list[ACPMessage] = []

        # Итерируем по всем tool calls и отменяем активные
        for tool_call in session.tool_calls.values():
            if tool_call.status not in {"pending", "in_progress"}:
                # Пропускаем завершенные/отмененные tool calls
                continue

            self.update_tool_call_status(
                session,
                tool_call.tool_call_id,
                "cancelled",
            )
            notifications.append(
                self.build_tool_update_notification(
                    session_id=session_id,
                    tool_call_id=tool_call.tool_call_id,
                    status="cancelled",
                )
            )

        return notifications

"""ToolCallHandler - обработчик обновлений вызовов инструментов.

Обрабатывает типы обновлений:
- tool_call: создание нового вызова инструмента
- tool_call_update: обновление статуса существующего вызова
- tool_call_result: результат выполнения инструмента
"""

from __future__ import annotations

from typing import Any

from codelab.client.presentation.chat.context import ChatUpdateContext


class ToolCallHandler:
    """Обработчик обновлений вызовов инструментов.

    Управляет списком tool_calls в состоянии сессии:
    - Добавляет новые tool calls
    - Обновляет статусы существующих
    - Логирует результаты
    """

    def can_handle(self, update_type: str) -> bool:
        """Проверяет, может ли handler обработать этот тип update.

        Args:
            update_type: Тип обновления из update.sessionUpdate

        Returns:
            True если update_type это tool_call, tool_call_update или tool_call_result
        """
        return update_type in {"tool_call", "tool_call_update", "tool_call_result"}

    def handle(self, update_data: dict[str, Any], context: ChatUpdateContext) -> None:
        """Обрабатывает update вызова инструмента.

        Args:
            update_data: Полные данные обновления от сервера
            context: Контекст с состоянием и сервисами
        """
        update = update_data.get("params", {}).get("update", {})
        update_type = update.get("sessionUpdate")
        tool_call_id = update.get("toolCallId")

        if not tool_call_id:
            context.logger.warning(
                "tool_call_update_missing_id",
                update_type=update_type,
            )
            return

        if update_type == "tool_call":
            self._handle_tool_call_created(update, context)
        elif update_type == "tool_call_update":
            self._handle_tool_call_updated(update, context)
        elif update_type == "tool_call_result":
            self._handle_tool_call_result(update, context)

    def _handle_tool_call_created(
        self, update: dict[str, Any], context: ChatUpdateContext
    ) -> None:
        """Обрабатывает создание нового вызова инструмента.

        Args:
            update: Данные обновления
            context: Контекст с состоянием
        """
        tool_call_id = update.get("toolCallId")
        title = update.get("title", "")
        status = update.get("status", "pending")
        kind = update.get("kind")

        tool_call = {
            "toolCallId": tool_call_id,
            "title": title,
            "status": status,
            "kind": kind,
        }

        context.state.add_tool_call(tool_call)
        context.sink.sync_tool_calls(context.session_id, context.state.tool_calls)

        context.logger.info(
            "tool_call_created",
            session_id=context.session_id,
            tool_call_id=tool_call_id,
            title=title,
            status=status,
            kind=kind,
        )

    def _handle_tool_call_updated(
        self, update: dict[str, Any], context: ChatUpdateContext
    ) -> None:
        """Обрабатывает обновление статуса вызова инструмента.

        Args:
            update: Данные обновления
            context: Контекст с состоянием
        """
        tool_call_id = update.get("toolCallId")
        status = update.get("status")
        title = update.get("title")

        if not tool_call_id:
            context.logger.warning(
                "tool_call_update_missing_id",
                update_type="tool_call_update",
            )
            return

        # Собираем поля для обновления
        updates: dict[str, Any] = {}
        if status:
            updates["status"] = status
        if title:
            updates["title"] = title

        if updates:
            context.state.update_tool_call(tool_call_id, **updates)
            context.sink.sync_tool_calls(context.session_id, context.state.tool_calls)

        context.logger.info(
            "tool_call_updated",
            session_id=context.session_id,
            tool_call_id=tool_call_id,
            updates=updates,
        )

    def _handle_tool_call_result(
        self, update: dict[str, Any], context: ChatUpdateContext
    ) -> None:
        """Обрабатывает результат выполнения инструмента.

        Args:
            update: Данные обновления
            context: Контекст с состоянием
        """
        tool_call_id = update.get("toolCallId")
        result = update.get("result")

        context.logger.info(
            "tool_call_result_received",
            session_id=context.session_id,
            tool_call_id=tool_call_id,
            has_result=result is not None,
        )

"""SessionUpdateDispatcher - диспетчер обновлений сессии.

Маршрутизирует session/update события к соответствующим обработчикам
на основе типа обновления (sessionUpdate).
"""

from __future__ import annotations

from typing import Any

import structlog

from codelab.client.presentation.chat.chat_session_state import ChatSessionState
from codelab.client.presentation.chat.context import ChatUpdateContext
from codelab.client.presentation.chat.handlers.config_option_handler import (
    ConfigOptionHandler,
)
from codelab.client.presentation.chat.handlers.message_chunk_handler import (
    MessageChunkHandler,
)
from codelab.client.presentation.chat.handlers.plan_update_handler import (
    PlanUpdateHandler,
)
from codelab.client.presentation.chat.handlers.session_info_handler import (
    SessionInfoHandler,
)
from codelab.client.presentation.chat.handlers.tool_call_handler import (
    ToolCallHandler,
)


class SessionUpdateDispatcher:
    """Диспетчер обновлений сессии.

    Маршрутизирует session/update события к соответствующим обработчикам
    на основе типа обновления (sessionUpdate).

    Поддерживаемые типы обновлений:
    - agent_message_chunk, user_message_chunk -> MessageChunkHandler
    - tool_call, tool_call_update, tool_call_result -> ToolCallHandler
    - plan -> PlanUpdateHandler
    - config_option_update -> ConfigOptionHandler

    Attributes:
        _handlers: Список обработчиков обновлений
        _logger: Logger для логирования
    """

    def __init__(
        self,
        message_chunk_handler: MessageChunkHandler,
        tool_call_handler: ToolCallHandler,
        plan_update_handler: PlanUpdateHandler,
        config_option_handler: ConfigOptionHandler,
        session_info_handler: SessionInfoHandler | None = None,
    ) -> None:
        """Инициализирует диспетчер с обработчиками.

        Args:
            message_chunk_handler: Обработчик message chunks
            tool_call_handler: Обработчик tool calls
            plan_update_handler: Обработчик plan updates
            config_option_handler: Обработчик config option updates
            session_info_handler: Обработчик информационных обновлений
        """
        self._handlers: list[
            MessageChunkHandler
            | ToolCallHandler
            | PlanUpdateHandler
            | ConfigOptionHandler
            | SessionInfoHandler
        ] = [
            message_chunk_handler,
            tool_call_handler,
            plan_update_handler,
            config_option_handler,
        ]
        # SessionInfoHandler опционален — создаём default если не передан
        if session_info_handler is None:
            session_info_handler = SessionInfoHandler()
        self._handlers.append(session_info_handler)
        
        # Оптимизация: dict для O(1) поиска handler'а по update_type
        self._handler_map: dict[str, Any] = {}
        for handler in self._handlers:
            # Регистрируем все типы которые может обрабатывать handler
            # Используем can_handle для определения поддерживаемых типов
            for update_type in [
                "agent_message_chunk",
                "user_message_chunk",
                "tool_call",
                "tool_call_update",
                "tool_call_result",
                "plan",
                "config_option_update",
                "available_commands_update",
                "session_info_update",
            ]:
                if handler.can_handle(update_type):
                    self._handler_map[update_type] = handler
        
        self._logger = structlog.get_logger("session_update_dispatcher")

    def dispatch(
        self,
        update_data: dict[str, Any],
        session_state: ChatSessionState,
        session_id: str,
    ) -> None:
        """Диспетчеризует обновление к соответствующему обработчику.

        Args:
            update_data: Данные обновления от сервера
            session_state: Состояние сессии для модификации
            session_id: ID сессии
        """
        # Извлекаем тип обновления
        update = update_data.get("params", {}).get("update", {})
        update_type = update.get("sessionUpdate")

        if not update_type:
            self._logger.warning(
                "update_missing_type",
                session_id=session_id,
                update_data=update_data,
            )
            return

        self._logger.debug(
            "dispatching_update",
            session_id=session_id,
            update_type=update_type,
        )

        # Создаём контекст для обработчика
        # Примечание: sink и другие зависимости будут установлены позже
        # при интеграции с ChatViewModel
        context = ChatUpdateContext(
            session_id=session_id,
            state=session_state,
            sink=None,
            plan_vm=None,
            event_bus=None,
            _logger=self._logger,
        )

        # O(1) поиск handler'а через dict
        handler = self._handler_map.get(update_type)
        if handler:
            try:
                handler.handle(update_data, context)
                self._logger.debug(
                    "update_handled",
                    session_id=session_id,
                    update_type=update_type,
                    handler=handler.__class__.__name__,
                )
                return
            except Exception as e:
                self._logger.error(
                    "handler_error",
                    session_id=session_id,
                    update_type=update_type,
                    handler=handler.__class__.__name__,
                    error=str(e),
                    exc_info=True,
                )
                return

        # Если обработчик не найден, логируем warning
        self._logger.warning(
            "no_handler_for_update_type",
            session_id=session_id,
            update_type=update_type,
        )

    def dispatch_with_context(
        self,
        update_data: dict[str, Any],
        context: ChatUpdateContext,
    ) -> None:
        """Диспетчеризует обновление с полным контекстом.

        Этот метод используется когда контекст уже создан с sink и другими
        зависимостями (например, при интеграции с ChatViewModel).

        Args:
            update_data: Данные обновления от сервера
            context: Контекст с состоянием и зависимостями
        """
        # Извлекаем тип обновления
        update = update_data.get("params", {}).get("update", {})
        update_type = update.get("sessionUpdate")

        if not update_type:
            self._logger.warning(
                "update_missing_type",
                session_id=context.session_id,
                update_data=update_data,
            )
            return

        self._logger.debug(
            "dispatching_update_with_context",
            session_id=context.session_id,
            update_type=update_type,
        )

        # O(1) поиск handler'а через dict
        handler = self._handler_map.get(update_type)
        if handler:
            try:
                handler.handle(update_data, context)
                self._logger.debug(
                    "update_handled_with_context",
                    session_id=context.session_id,
                    update_type=update_type,
                    handler=handler.__class__.__name__,
                )
                return
            except Exception as e:
                self._logger.error(
                    "handler_error_with_context",
                    session_id=context.session_id,
                    update_type=update_type,
                    handler=handler.__class__.__name__,
                    error=str(e),
                    exc_info=True,
                )
                return

        # Если обработчик не найден, логируем warning
        self._logger.warning(
            "no_handler_for_update_type_with_context",
            session_id=context.session_id,
            update_type=update_type,
        )

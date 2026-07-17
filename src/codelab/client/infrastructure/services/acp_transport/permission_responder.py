"""PermissionResponder - обработка session/request_permission на стороне клиента.

Инкапсулирует полный lifecycle permission-запроса, независимо от транспорта:
1. Парсинг входящего JSON-RPC сообщения.
2. Делегирование в PermissionHandler (с UI-callback, если он установлен).
3. Формирование и отправка ответа серверу.

Отправка ответа выполняется через переданный `send` callable, поэтому
компонент не знает о конкретной реализации транспорта.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import structlog

from codelab.client.messages import RequestPermissionRequest

if TYPE_CHECKING:
    from codelab.client.application.permission_handler import PermissionHandler

SendFn = Callable[[dict[str, Any]], Awaitable[None]]
PermissionUiCallback = Callable[
    [str | int, Any, list[Any], Callable[[str | int, str], None]], None
]


class PermissionResponder:
    """Обрабатывает session/request_permission и отправляет ответ серверу.

    Handler и UI-callback устанавливаются после конструирования (через сеттеры),
    так как UI-callback появляется только после инициализации TUI.
    """

    def __init__(
        self,
        send: SendFn,
        handler: PermissionHandler | None = None,
    ) -> None:
        """Инициализирует responder.

        Аргументы:
            send: Callable для отправки JSON-RPC сообщения серверу.
            handler: PermissionHandler для обработки запросов (опционально).
        """
        self._send = send
        self._handler = handler
        self._callback: PermissionUiCallback | None = None
        self._logger = structlog.get_logger("permission_responder")

    @property
    def handler(self) -> PermissionHandler | None:
        """Текущий PermissionHandler."""
        return self._handler

    @property
    def callback(self) -> PermissionUiCallback | None:
        """Текущий UI-callback для показа модального окна."""
        return self._callback

    def set_handler(self, handler: PermissionHandler) -> None:
        """Установить PermissionHandler для обработки permission requests."""
        self._handler = handler

    def set_callback(self, callback: PermissionUiCallback) -> None:
        """Установить callback для отображения permission modal в UI."""
        self._callback = callback
        self._logger.info(
            "permission_callback_set",
            callback_name=getattr(callback, "__name__", "unknown"),
        )

    async def handle(self, message: dict[str, Any]) -> None:
        """Обрабатывает session/request_permission через PermissionHandler.

        Интегрирует permission request с полным lifecycle:
        1. Парсинг request
        2. Обработка через PermissionHandler
        3. Формирование и отправка response

        Args:
            message: JSON-RPC сообщение с permission request
        """
        self._logger.info(
            "handle_permission_request_with_handler_called",
            message_id=message.get("id"),
            method=message.get("method"),
            has_permission_handler=self._handler is not None,
            has_permission_callback=self._callback is not None,
        )

        if self._handler is None:
            self._logger.warning("permission_handler_not_configured_skipping")
            # Отправить cancel response чтобы сервер не завис
            try:
                cancel_response = {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "result": {"outcome": "cancelled"},
                }
                await self._send(cancel_response)
                self._logger.debug("cancel_response_sent_for_missing_handler")
            except Exception as send_error:
                self._logger.error(
                    "failed_to_send_cancel_response",
                    error=str(send_error),
                )
            return

        try:
            # Парсинг request
            request = RequestPermissionRequest.model_validate(message)

            self._logger.info(
                "handling_permission_request_with_handler",
                request_id=request.id,
                session_id=request.params.sessionId,
                tool_call_id=request.params.toolCall.toolCallId,
                has_ui_callback=self._callback is not None,
            )

            # Обработка через handler с callback если он установлен
            # Если callback=None, PermissionHandler вернет CancelledPermissionOutcome
            outcome = await self._handler.handle_request(
                request=request,
                callback=self._callback,
            )

            self._logger.info(
                "permission_request_handled_successfully",
                request_id=request.id,
                outcome=outcome.outcome,
            )

        except Exception as e:
            self._logger.error(
                "permission_request_handling_error",
                error=str(e),
                error_type=type(e).__name__,
                message_id=message.get("id"),
            )
            # Отправить error response
            try:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "error": {
                        "code": -32603,
                        "message": f"Internal error: {e}",
                    },
                }
                await self._send(error_response)
                self._logger.debug(
                    "error_response_sent",
                    message_id=message.get("id"),
                )
            except Exception as send_error:
                self._logger.error(
                    "failed_to_send_error_response",
                    error=str(send_error),
                )


__all__ = ["PermissionResponder", "PermissionUiCallback", "SendFn"]

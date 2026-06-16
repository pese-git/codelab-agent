"""Middleware для трассировки JSON-RPC сообщений.

Логирует все входящие запросы и исходящие ответы на уровне протокола.
Включается только при активном флаге trace_messages.

Trace логи пишутся в отдельный файл ~/.codelab/logs/traces-{pid}.log
через logger "codelab.trace" в JSON формате (без цветов).

Пример использования:
    from codelab.server.protocol.middleware.message_trace import create_message_trace_middleware

    trace_mw = create_message_trace_middleware(enabled=True)
    protocol = ACPProtocol(middleware=[trace_mw])
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.messages import ACPMessage
from codelab.server.protocol.core import MethodHandler, MiddlewareFn, ProtocolOutcome

if TYPE_CHECKING:
    pass

# Logger для trace логов — пишет в отдельный файл traces-{pid}.log в JSON формате
_trace_logger = structlog.get_logger("codelab.trace")

# Основной logger для обычных логов
logger = structlog.get_logger()


def _truncate_if_needed(data: Any, max_length: int) -> str:
    """Обрезает данные для логирования если нужно.

    Args:
        data: Данные для обрезки
        max_length: Максимальная длина (0 = без ограничений)

    Returns:
        Строковое представление данных
    """
    if max_length <= 0:
        if isinstance(data, str):
            return data
        return json.dumps(data, ensure_ascii=False, default=str)

    raw = json.dumps(data, ensure_ascii=False, default=str)
    if len(raw) > max_length:
        return raw[:max_length] + f"... (truncated, {len(raw)} chars total)"
    return raw


async def message_trace_middleware(
    message: ACPMessage,
    next_handler: MethodHandler,
    *,
    enabled: bool = True,
    connection_id: str | None = None,
    max_payload_length: int = 0,
) -> ProtocolOutcome:
    """Middleware для трассировки сообщений.

    Логирует входящие запросы и исходящие ответы с полным payload.

    Args:
        message: Входящее сообщение
        next_handler: Следующий обработчик в цепочке
        enabled: Включено ли логирование
        connection_id: ID соединения для контекста
        max_payload_length: Максимальная длина payload (0 = без ограничений)

    Returns:
        ProtocolOutcome от next_handler
    """
    if not enabled:
        return await next_handler(message)

    # Логируем входящее сообщение
    method = message.method or "response"
    request_id = str(message.id) if message.id is not None else None

    incoming_payload = {
        "jsonrpc": "2.0",
        "method": message.method,
        "id": message.id,
        "params": message.params,
    }

    trace_context: dict[str, Any] = {
        "direction": "in",
        "trace_type": "message_trace",
        "method": method,
    }
    if connection_id:
        trace_context["connection_id"] = connection_id
    if request_id:
        trace_context["request_id"] = request_id
    trace_context["payload"] = _truncate_if_needed(incoming_payload, max_payload_length)

    _trace_logger.debug("message_trace", **trace_context)

    # Вызываем следующий обработчик
    outcome = await next_handler(message)

    # Логируем исходящий ответ
    outgoing_parts: list[dict[str, Any]] = []

    if outcome.response is not None:
        outgoing_parts.append({
            "type": "response",
            "id": outcome.response.id,
            "result": outcome.response.result,
            "error": outcome.response.error.model_dump() if outcome.response.error else None,
        })

    for notification in outcome.notifications:
        outgoing_parts.append({
            "type": "notification",
            "method": notification.method,
            "params": notification.params,
        })

    if outgoing_parts:
        outgoing_context: dict[str, Any] = {
            "direction": "out",
            "trace_type": "message_trace",
            "method": method,
        }
        if connection_id:
            outgoing_context["connection_id"] = connection_id
        if request_id:
            outgoing_context["request_id"] = request_id
        outgoing_context["payload"] = _truncate_if_needed(
            outgoing_parts if len(outgoing_parts) > 1 else outgoing_parts[0],
            max_payload_length,
        )
        _trace_logger.debug("message_trace", **outgoing_context)

    return outcome


def create_message_trace_middleware(
    enabled: bool = True,
    connection_id: str | None = None,
    max_payload_length: int = 0,
) -> MiddlewareFn:
    """Создает middleware для трассировки сообщений.

    Args:
        enabled: Включено ли логирование
        connection_id: ID соединения для контекста
        max_payload_length: Максимальная длина payload (0 = без ограничений)

    Returns:
        Middleware функция
    """

    async def middleware(message: ACPMessage, next_handler: MethodHandler) -> ProtocolOutcome:
        return await message_trace_middleware(
            message,
            next_handler,
            enabled=enabled,
            connection_id=connection_id,
            max_payload_length=max_payload_length,
        )

    return middleware

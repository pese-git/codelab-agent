"""ClientRpcDispatcher - диспетчер входящих RPC запросов от сервера.

Маршрутизирует RPC запросы (fs/*, terminal/*) к соответствующим обработчикам
на основе имени метода.
"""

from __future__ import annotations

from typing import Any

import structlog

from codelab.client.infrastructure.services.acp_transport.contracts import RpcHandler


class ClientRpcDispatcher:
    """Диспетчер входящих RPC запросов от сервера.

    Маршрутизирует RPC запросы к зарегистрированным обработчикам.
    Обрабатывает ошибки и логирует все операции.

    Attributes:
        _handlers: Список зарегистрированных обработчиков
        _logger: Logger для логирования
    """

    def __init__(self, handlers: list[RpcHandler]) -> None:
        """Инициализирует диспетчер с обработчиками.

        Args:
            handlers: Список обработчиков RPC в порядке приоритета
        """
        if not handlers:
            self._logger = structlog.get_logger("client_rpc_dispatcher")
            self._logger.warning("dispatcher_initialized_with_empty_handlers")
        self._handlers = handlers
        self._logger = structlog.get_logger("client_rpc_dispatcher")

    async def dispatch(
        self, method: str, rpc_id: str | int, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Диспетчеризует RPC запрос к подходящему обработчику.

        Args:
            method: Имя метода RPC (например, "fs/read_text_file")
            rpc_id: Идентификатор запроса
            params: Параметры запроса

        Returns:
            Dict с результатом или ошибкой в формате JSON-RPC
        """
        self._logger.info("rpc_request_received", method=method, rpc_id=rpc_id)

        for handler in self._handlers:
            if handler.can_handle(method):
                handler_name = handler.__class__.__name__
                self._logger.debug(
                    "rpc_handler_found",
                    method=method,
                    rpc_id=rpc_id,
                    handler=handler_name,
                )
                try:
                    result = await handler.handle(rpc_id, params)

                    if result is not None and "error" in result:
                        error_info = result["error"]
                        self._logger.warning(
                            "rpc_handler_returned_error",
                            method=method,
                            rpc_id=rpc_id,
                            handler=handler_name,
                            error_code=error_info.get("code"),
                            error_message=error_info.get("message"),
                        )
                        return result

                    self._logger.debug(
                        "rpc_request_handled",
                        method=method,
                        rpc_id=rpc_id,
                        handler=handler_name,
                        is_error=False,
                    )
                    return result if result is not None else {}

                except Exception as e:
                    self._logger.error(
                        "rpc_handler_exception",
                        method=method,
                        rpc_id=rpc_id,
                        handler=handler_name,
                        error=str(e),
                        exc_info=True,
                    )
                    return {"error": {"code": -32603, "message": str(e)}}

        self._logger.warning(
            "no_handler_for_rpc_method",
            method=method,
            rpc_id=rpc_id,
        )
        return {"error": {"code": -32601, "message": f"Method not found: {method}"}}

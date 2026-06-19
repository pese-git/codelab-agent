"""TerminalWaitHandler - обработчик RPC метода terminal/wait_for_exit."""

from __future__ import annotations

from typing import Any

import structlog

from codelab.client.presentation.chat.executors.terminal_callback_executor import (
    TerminalCallbackExecutor,
)


class TerminalWaitHandler:
    """Обработчик RPC метода terminal/wait_for_exit.

    Делегирует ожидание завершения терминала TerminalCallbackExecutor.
    """

    def __init__(self, executor: TerminalCallbackExecutor) -> None:
        self._executor = executor
        self._logger = structlog.get_logger("terminal_wait_handler")

    def can_handle(self, method: str) -> bool:
        return method == "terminal/wait_for_exit"

    async def handle(
        self, rpc_id: str | int, params: dict[str, Any]
    ) -> dict[str, Any]:
        terminal_id = params.get("terminalId")
        if not isinstance(terminal_id, str):
            self._logger.warning("missing_terminal_id_parameter", rpc_id=rpc_id)
            return {"error": {"code": -32602, "message": "Missing required parameter: terminalId"}}

        self._logger.info("terminal_wait_request", rpc_id=rpc_id, terminal_id=terminal_id)

        result, error = await self._executor.wait_for_exit(terminal_id)
        if result is None:
            error_msg = error or "Failed to wait for terminal exit"
            self._logger.warning("terminal_wait_failed", rpc_id=rpc_id, error=error_msg)
            return {"error": {"code": -32603, "message": error_msg}}

        exit_code, output = result
        response: dict[str, Any] = {}
        if exit_code is not None:
            response["exitCode"] = exit_code
        if output is not None:
            response["output"] = output
        return response

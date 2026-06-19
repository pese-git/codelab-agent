"""TerminalOutputHandler - обработчик RPC метода terminal/output."""

from __future__ import annotations

from typing import Any

import structlog

from codelab.client.presentation.chat.executors.terminal_callback_executor import (
    TerminalCallbackExecutor,
)


class TerminalOutputHandler:
    """Обработчик RPC метода terminal/output.

    Делегирует получение вывода терминала TerminalCallbackExecutor.
    """

    def __init__(self, executor: TerminalCallbackExecutor) -> None:
        self._executor = executor
        self._logger = structlog.get_logger("terminal_output_handler")

    def can_handle(self, method: str) -> bool:
        return method == "terminal/output"

    async def handle(
        self, rpc_id: str | int, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        terminal_id = params.get("terminalId")
        if not isinstance(terminal_id, str):
            self._logger.warning("missing_terminal_id_parameter", rpc_id=rpc_id)
            return {"error": {"code": -32602, "message": "Missing required parameter: terminalId"}}

        self._logger.info("terminal_output_request", rpc_id=rpc_id, terminal_id=terminal_id)

        output_data, error = await self._executor.get_output(terminal_id)
        if output_data is None:
            error_msg = error or "Failed to get terminal output"
            self._logger.warning("terminal_output_failed", rpc_id=rpc_id, error=error_msg)
            return {"error": {"code": -32603, "message": error_msg}}

        return output_data

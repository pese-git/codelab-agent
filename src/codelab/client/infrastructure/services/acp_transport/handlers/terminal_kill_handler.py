"""TerminalKillHandler - обработчик RPC метода terminal/kill."""

from __future__ import annotations

from typing import Any

import structlog

from codelab.client.presentation.chat.executors.terminal_callback_executor import (
    TerminalCallbackExecutor,
)


class TerminalKillHandler:
    """Обработчик RPC метода terminal/kill.

    Делегирует принудительное завершение терминала TerminalCallbackExecutor.
    """

    def __init__(self, executor: TerminalCallbackExecutor) -> None:
        self._executor = executor
        self._logger = structlog.get_logger("terminal_kill_handler")

    def can_handle(self, method: str) -> bool:
        return method == "terminal/kill"

    async def handle(
        self, rpc_id: str | int, params: dict[str, Any]
    ) -> dict[str, Any]:
        terminal_id = params.get("terminalId")
        if not isinstance(terminal_id, str):
            self._logger.warning("missing_terminal_id_parameter", rpc_id=rpc_id)
            return {"error": {"code": -32602, "message": "Missing required parameter: terminalId"}}

        self._logger.info("terminal_kill_request", rpc_id=rpc_id, terminal_id=terminal_id)

        success, error = await self._executor.kill_terminal(terminal_id)
        if not success:
            error_msg = error or "Failed to kill terminal"
            self._logger.warning("terminal_kill_failed", rpc_id=rpc_id, error=error_msg)
            return {"error": {"code": -32603, "message": error_msg}}

        return {}

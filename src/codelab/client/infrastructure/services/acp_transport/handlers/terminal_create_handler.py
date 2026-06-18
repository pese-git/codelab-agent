"""TerminalCreateHandler - обработчик RPC метода terminal/create."""

from __future__ import annotations

from typing import Any

import structlog

from codelab.client.presentation.chat.executors.terminal_callback_executor import (
    TerminalCallbackExecutor,
)


class TerminalCreateHandler:
    """Обработчик RPC метода terminal/create.

    Делегирует создание терминалов TerminalCallbackExecutor.
    """

    def __init__(self, executor: TerminalCallbackExecutor) -> None:
        self._executor = executor
        self._logger = structlog.get_logger("terminal_create_handler")

    def can_handle(self, method: str) -> bool:
        return method == "terminal/create"

    async def handle(
        self, rpc_id: str | int, params: dict[str, Any]
    ) -> dict[str, Any]:
        command = params.get("command")
        if not isinstance(command, str):
            self._logger.warning("missing_command_parameter", rpc_id=rpc_id)
            return {"error": {"code": -32602, "message": "Missing required parameter: command"}}

        self._logger.info("terminal_create_request", rpc_id=rpc_id, command=command)

        terminal_id, error = await self._executor.create_terminal(command)
        if terminal_id is None:
            error_msg = error or "Failed to create terminal"
            self._logger.warning("terminal_create_failed", rpc_id=rpc_id, error=error_msg)
            return {"error": {"code": -32603, "message": error_msg}}

        return {"terminalId": terminal_id}

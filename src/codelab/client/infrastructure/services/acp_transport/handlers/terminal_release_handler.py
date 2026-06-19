"""TerminalReleaseHandler - обработчик RPC метода terminal/release."""

from __future__ import annotations

from typing import Any

import structlog

from codelab.client.presentation.chat.executors.terminal_callback_executor import (
    TerminalCallbackExecutor,
)


class TerminalReleaseHandler:
    """Обработчик RPC метода terminal/release.

    Делегирует освобождение ресурсов терминала TerminalCallbackExecutor.
    """

    def __init__(self, executor: TerminalCallbackExecutor) -> None:
        self._executor = executor
        self._logger = structlog.get_logger("terminal_release_handler")

    def can_handle(self, method: str) -> bool:
        return method == "terminal/release"

    async def handle(
        self, rpc_id: str | int, params: dict[str, Any]
    ) -> dict[str, Any]:
        terminal_id = params.get("terminalId")
        if not isinstance(terminal_id, str):
            self._logger.warning("missing_terminal_id_parameter", rpc_id=rpc_id)
            return {"error": {"code": -32602, "message": "Missing required parameter: terminalId"}}

        self._logger.info("terminal_release_request", rpc_id=rpc_id, terminal_id=terminal_id)

        error = await self._executor.release_terminal(terminal_id)
        if error is not None:
            self._logger.warning("terminal_release_failed", rpc_id=rpc_id, error=error)
            return {"error": {"code": -32603, "message": error}}

        return {}

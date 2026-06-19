"""FsReadHandler - обработчик RPC метода fs/read_text_file."""

from __future__ import annotations

from typing import Any

import structlog

from codelab.client.presentation.chat.executors.fs_callback_executor import (
    FsCallbackExecutor,
)


class FsReadHandler:
    """Обработчик RPC метода fs/read_text_file.

    Делегирует чтение файлов FsCallbackExecutor.
    """

    def __init__(self, executor: FsCallbackExecutor) -> None:
        self._executor = executor
        self._logger = structlog.get_logger("fs_read_handler")

    def can_handle(self, method: str) -> bool:
        return method == "fs/read_text_file"

    async def handle(
        self, rpc_id: str | int, params: dict[str, Any]
    ) -> dict[str, Any]:
        path = params.get("path")
        if not isinstance(path, str):
            self._logger.warning("missing_path_parameter", rpc_id=rpc_id)
            return {"error": {"code": -32602, "message": "Missing required parameter: path"}}

        self._logger.info("fs_read_request", rpc_id=rpc_id, path=path)

        content, error = await self._executor.read_file(path)
        if error is not None:
            self._logger.warning("fs_read_failed", rpc_id=rpc_id, error=error)
            return {"error": {"code": -32603, "message": error}}

        return {"content": content}

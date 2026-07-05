"""FileCacheDecorator — перехват fs/read и fs/write для кэширования.

Слой C — Хранение (Phase 2).

Декоратор оборачивает ToolExecutor и:
- При успешном fs/read → сохраняет содержимое в FileContentCache
- При успешном fs/write → инвалидирует кэш и публикует сигнал
- Ошибки кэша логируются, но не распространяются
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from codelab.server.agent.context.interfaces import FileContentCache
from codelab.server.tools.base import ToolExecutionResult
from codelab.server.tools.executors.decorators.base import (
    ToolExecutorDecorator,
    ToolExecutorProtocol,
)

if TYPE_CHECKING:
    from codelab.server.protocol.state import SessionState

logger = logging.getLogger(__name__)

FS_READ_TOOL = "fs/read"
FS_WRITE_TOOL = "fs/write"


class FileCacheDecorator(ToolExecutorDecorator):
    """Декоратор для кэширования содержимого файлов.

    Перехватывает fs/read и fs/write, обновляя FileContentCache.
    Ошибки кэша не влияют на результат инструмента.

    Attributes:
        _cache: Кэш содержимого файлов
    """

    def __init__(
        self,
        wrapped: ToolExecutorProtocol,
        cache: FileContentCache,
    ) -> None:
        super().__init__(wrapped)
        self._cache = cache

    async def execute(
        self,
        session: SessionState,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        """Выполнить инструмент с кэшированием файловых операций."""
        result = await self._wrapped.execute(session, arguments)

        if not result.success:
            return result

        tool_name = arguments.get("tool_name", "")
        path = arguments.get("path", "")

        if not path:
            return result

        try:
            if tool_name == FS_READ_TOOL:
                self._handle_read(path, result)
            elif tool_name == FS_WRITE_TOOL:
                self._handle_write(path)
        except Exception:
            logger.exception("file_cache_decorator_error: tool=%s path=%s", tool_name, path)

        return result

    def _handle_read(self, path: str, result: ToolExecutionResult) -> None:
        """Обработать успешный fs/read — сохранить в кэш."""
        content = result.output
        if content is None:
            return

        try:
            self._cache.set(path, content)
            logger.debug("file_cache_set: path=%s", path)
        except Exception:
            logger.exception("file_cache_set_failed: path=%s", path)

    def _handle_write(self, path: str) -> None:
        """Обработать успешный fs/write — инвалидировать кэш."""
        try:
            self._cache.invalidate(path)
            logger.debug("file_cache_invalidate: path=%s", path)
        except Exception:
            logger.exception("file_cache_invalidation_failed: path=%s", path)

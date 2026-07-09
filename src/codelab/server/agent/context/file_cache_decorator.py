"""FileCacheDecorator — перехват fs/read и fs/write для кэширования.

Слой C — Хранение (Phase 2).

Декоратор оборачивает ToolExecutor и:
- При fs/read → сначала проверяет кэш, при промахе выполняет RPC и сохраняет в кэш
- При fs/write → инвалидирует кэш
- Ошибки кэша логируются, но не распространяются
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.agent.context.interfaces import FileContentCache
from codelab.server.tools.base import ToolExecutionResult
from codelab.server.tools.executors.decorators.base import (
    ToolExecutorDecorator,
    ToolExecutorProtocol,
)

if TYPE_CHECKING:
    from codelab.server.protocol.state import SessionState

logger = structlog.get_logger(__name__)

FS_READ_TOOL = "fs/read"
FS_WRITE_TOOL = "fs/write"


class FileCacheDecorator(ToolExecutorDecorator):
    """Декоратор для кэширования содержимого файлов.

    Перехватывает fs/read и fs/write, обновляя FileContentCache.
    При fs/read сначала проверяет кэш — при попадании возвращает без RPC.
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
        """Выполнить инструмент с кэшированием файловых операций.
        
        При fs/read сначала проверяет кэш. При попадании возвращает
        содержимое из кэша без вызова wrapped.execute(). При промахе
        выполняет RPC и сохраняет результат в кэш.
        """
        tool_name = arguments.get("tool_name", "")
        path = arguments.get("path", "")

        # Проверка кэша перед чтением файла
        if tool_name == FS_READ_TOOL and path:
            try:
                cached_content = self._cache.get(path)
                if cached_content is not None:
                    logger.debug("file_cache_hit", path=path)
                    return ToolExecutionResult(
                        success=True,
                        output=cached_content,
                        metadata={"from_cache": True, "path": path},
                    )
            except Exception:
                logger.exception("file_cache_get_failed", path=path)

        # Кэш не содержит файл — выполняем RPC
        result = await self._wrapped.execute(session, arguments)

        if not result.success:
            return result

        if not path:
            return result

        try:
            if tool_name == FS_READ_TOOL:
                self._handle_read(path, result)
            elif tool_name == FS_WRITE_TOOL:
                self._handle_write(path)
        except Exception:
            logger.exception("file_cache_decorator_error", tool=tool_name, path=path)

        return result

    def _handle_read(self, path: str, result: ToolExecutionResult) -> None:
        """Обработать успешный fs/read — сохранить в кэш."""
        content = result.output
        if content is None:
            return

        try:
            self._cache.set(path, content)
            logger.debug("file_cache_set", path=path)
        except Exception:
            logger.exception("file_cache_set_failed", path=path)

    def _handle_write(self, path: str) -> None:
        """Обработать успешный fs/write — инвалидировать кэш."""
        try:
            self._cache.invalidate(path)
            logger.debug("file_cache_invalidate", path=path)
        except Exception:
            logger.exception("file_cache_invalidation_failed", path=path)

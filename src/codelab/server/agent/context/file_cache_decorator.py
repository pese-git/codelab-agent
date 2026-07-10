"""FileCacheDecorator — перехват fs/read и fs/write для кэширования.

Слой C — Хранение (Phase 2).

Декоратор оборачивает ToolExecutor и:
- При fs/read → сначала проверяет кэш, при промахе выполняет RPC и сохраняет в кэш
- При fs/write → инвалидирует кэш
- Ошибки кэша логируются, но не распространяются

Фаза 4: поддерживает SessionFileCacheRegistry для изоляции кэша по сессиям.
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
    from codelab.server.agent.context.file_cache import SessionFileCacheRegistry
    from codelab.server.protocol.state import SessionState

logger = structlog.get_logger(__name__)


FS_READ_TOOL = "fs/read"
FS_WRITE_TOOL = "fs/write"


class FileCacheDecorator(ToolExecutorDecorator):
    """Декоратор для кэширования содержимого файлов.

    Перехватывает fs/read и fs/write, обновляя FileContentCache.
    При fs/read сначала проверяет кэш — при попадании возвращает без RPC.
    Ошибки кэша не влияют на результат инструмента.

    Поддерживает два режима:
    - Простой: один FileContentCache на все сессии
    - Session-aware: SessionFileCacheRegistry для изоляции кэша по сессиям

    Attributes:
        _cache: Кэш содержимого файлов (для простого режима)
        _session_registry: Реестр кэшей по сессиям (для session-aware режима)
    """

    def __init__(
        self,
        wrapped: ToolExecutorProtocol,
        cache: FileContentCache | None = None,
        session_registry: SessionFileCacheRegistry | None = None,
    ) -> None:
        super().__init__(wrapped)
        self._cache = cache
        self._session_registry = session_registry

    def _get_cache_for_session(self, session: SessionState) -> FileContentCache | None:
        """Получить кэш для конкретной сессии."""
        if self._session_registry is not None:
            return self._session_registry.get_or_create(session.session_id)
        return self._cache

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
        operation = arguments.get("operation", "")
        path = arguments.get("path", "")

        logger.debug(
            "file_cache_decorator.execute",
            operation=operation,
            path=path,
            has_cache=self._cache is not None,
            has_registry=self._session_registry is not None,
        )

        # Проверка кэша перед чтением файла
        if operation == "read" and path:
            cache = self._get_cache_for_session(session)
            if cache is not None:
                try:
                    cached_content = cache.get(path)
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

        cache = self._get_cache_for_session(session)
        if cache is None:
            return result

        try:
            if operation == "read":
                self._handle_read(path, result, cache)
            elif operation == "write":
                self._handle_write(path, cache)
        except Exception:
            logger.exception(
                "file_cache_decorator_error",
                operation=operation,
                path=path,
            )

        return result

    def _handle_read(self, path: str, result: ToolExecutionResult, cache: FileContentCache) -> None:
        """Обработать успешный fs/read — сохранить в кэш."""
        content = result.output
        if content is None:
            return

        try:
            cache.set(path, content)
            logger.debug("file_cache_set", path=path)
        except Exception:
            logger.exception("file_cache_set_failed", path=path)

    def _handle_write(self, path: str, cache: FileContentCache) -> None:
        """Обработать успешный fs/write — инвалидировать кэш."""
        try:
            cache.invalidate(path)
            logger.debug("file_cache_invalidate", path=path)
        except Exception:
            logger.exception("file_cache_invalidation_failed", path=path)

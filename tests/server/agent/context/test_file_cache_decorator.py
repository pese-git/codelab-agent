"""Unit тесты для FileCacheDecorator."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from codelab.server.agent.context.file_cache import InMemoryFileCache
from codelab.server.agent.context.file_cache_decorator import FileCacheDecorator
from codelab.server.tools.base import ToolExecutionResult


@pytest.fixture
def mock_executor():
    """Мокированный executor."""
    executor = MagicMock()
    executor.execute = AsyncMock()
    return executor


@pytest.fixture
def cache():
    """Кэш для тестов."""
    return InMemoryFileCache()


@pytest.fixture
def decorator(mock_executor, cache):
    """FileCacheDecorator для тестов."""
    return FileCacheDecorator(mock_executor, cache)


class TestFileCacheDecorator:
    """Тесты для FileCacheDecorator."""

    @pytest.mark.asyncio
    async def test_fs_read_caches_content(self, decorator, mock_executor, cache):
        """fs/read сохраняет содержимое в кэш."""
        mock_executor.execute.return_value = ToolExecutionResult(
            success=True,
            output="file content",
        )
        session = MagicMock()
        arguments = {"tool_name": "fs/read", "path": "/test.py"}

        result = await decorator.execute(session, arguments)

        assert result.success is True
        assert cache.get("/test.py") == "file content"

    @pytest.mark.asyncio
    async def test_fs_write_invalidates_cache(self, decorator, mock_executor, cache):
        """fs/write инвалидирует кэш."""
        cache.set("/test.py", "old content")
        mock_executor.execute.return_value = ToolExecutionResult(
            success=True,
            output="written",
        )
        session = MagicMock()
        arguments = {"tool_name": "fs/write", "path": "/test.py"}

        result = await decorator.execute(session, arguments)

        assert result.success is True
        assert cache.get("/test.py") is None

    @pytest.mark.asyncio
    async def test_fs_write_publishes_invalidation_signal(self, decorator, mock_executor, cache):
        """fs/write публикует сигнал инвалидации."""
        received: list[str] = []
        cache.signal_bus.subscribe(lambda path: received.append(path))
        mock_executor.execute.return_value = ToolExecutionResult(
            success=True,
            output="written",
        )
        session = MagicMock()
        arguments = {"tool_name": "fs/write", "path": "/test.py"}

        await decorator.execute(session, arguments)

        assert received == ["/test.py"]

    @pytest.mark.asyncio
    async def test_failed_tool_does_not_cache(self, decorator, mock_executor, cache):
        """Неуспешный инструмент не кэшируется."""
        mock_executor.execute.return_value = ToolExecutionResult(
            success=False,
            error="read error",
        )
        session = MagicMock()
        arguments = {"tool_name": "fs/read", "path": "/test.py"}

        result = await decorator.execute(session, arguments)

        assert result.success is False
        assert cache.get("/test.py") is None

    @pytest.mark.asyncio
    async def test_non_file_tool_not_cached(self, decorator, mock_executor, cache):
        """Не файловые инструменты не кэшируются."""
        mock_executor.execute.return_value = ToolExecutionResult(
            success=True,
            output="terminal output",
        )
        session = MagicMock()
        arguments = {"tool_name": "terminal/run", "command": "ls"}

        result = await decorator.execute(session, arguments)

        assert result.success is True
        assert cache.size == 0

    @pytest.mark.asyncio
    async def test_missing_path_not_cached(self, decorator, mock_executor, cache):
        """Отсутствие path не кэшируется."""
        mock_executor.execute.return_value = ToolExecutionResult(
            success=True,
            output="content",
        )
        session = MagicMock()
        arguments = {"tool_name": "fs/read"}

        result = await decorator.execute(session, arguments)

        assert result.success is True
        assert cache.size == 0

    @pytest.mark.asyncio
    async def test_cache_error_does_not_propagate(self, decorator, mock_executor, cache):
        """Ошибка кэша не распространяется."""
        mock_executor.execute.return_value = ToolExecutionResult(
            success=True,
            output="content",
        )
        session = MagicMock()
        arguments = {"tool_name": "fs/read", "path": "/test.py"}

        with pytest.MonkeyPatch().context() as m:
            m.setattr(cache, "set", MagicMock(side_effect=Exception("cache error")))
            result = await decorator.execute(session, arguments)

        assert result.success is True
        assert result.output == "content"

    @pytest.mark.asyncio
    async def test_invalidate_error_does_not_propagate(self, decorator, mock_executor, cache):
        """Ошибка инвалидации не распространяется."""
        cache.set("/test.py", "content")
        mock_executor.execute.return_value = ToolExecutionResult(
            success=True,
            output="written",
        )
        session = MagicMock()
        arguments = {"tool_name": "fs/write", "path": "/test.py"}

        with pytest.MonkeyPatch().context() as m:
            m.setattr(cache, "invalidate", MagicMock(side_effect=Exception("cache error")))
            result = await decorator.execute(session, arguments)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_fs_read_with_none_output_not_cached(self, decorator, mock_executor, cache):
        """fs/read с None output не кэшируется."""
        mock_executor.execute.return_value = ToolExecutionResult(
            success=True,
            output=None,
        )
        session = MagicMock()
        arguments = {"tool_name": "fs/read", "path": "/test.py"}

        result = await decorator.execute(session, arguments)

        assert result.success is True
        assert cache.size == 0

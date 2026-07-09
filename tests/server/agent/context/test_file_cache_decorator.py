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
        arguments = {"operation": "read", "path": "/test.py"}

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
        arguments = {"operation": "write", "path": "/test.py"}

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
        arguments = {"operation": "write", "path": "/test.py"}

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
        arguments = {"operation": "read", "path": "/test.py"}

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
        arguments = {"command": "ls"}

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
        arguments = {"operation": "read"}

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
        arguments = {"operation": "read", "path": "/test.py"}

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
        arguments = {"operation": "write", "path": "/test.py"}

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
        arguments = {"operation": "read", "path": "/test.py"}

        result = await decorator.execute(session, arguments)

        assert result.success is True
        assert cache.size == 0

    @pytest.mark.asyncio
    async def test_fs_read_returns_cached_content_without_rpc(self, decorator, mock_executor, cache):
        """fs/read возвращает содержимое из кэша без вызова wrapped.execute()."""
        # Предварительно заполняем кэш
        cache.set("/test.py", "cached content")
        session = MagicMock()
        arguments = {"operation": "read", "path": "/test.py"}

        result = await decorator.execute(session, arguments)

        # Проверяем, что результат из кэша
        assert result.success is True
        assert result.output == "cached content"
        assert result.metadata == {"from_cache": True, "path": "/test.py"}
        # Проверяем, что wrapped.execute() НЕ вызывался
        mock_executor.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_fs_read_cache_miss_calls_rpc(self, decorator, mock_executor, cache):
        """fs/read при промахе кэша вызывает wrapped.execute() и сохраняет в кэш."""
        mock_executor.execute.return_value = ToolExecutionResult(
            success=True,
            output="fresh content",
        )
        session = MagicMock()
        arguments = {"operation": "read", "path": "/test.py"}

        result = await decorator.execute(session, arguments)

        # Проверяем, что wrapped.execute() был вызван
        mock_executor.execute.assert_called_once()
        # Проверяем, что результат сохранён в кэш
        assert cache.get("/test.py") == "fresh content"
        assert result.success is True
        assert result.output == "fresh content"
        # metadata не должен содержать from_cache при промахе
        assert result.metadata is None or not result.metadata.get("from_cache")

    @pytest.mark.asyncio
    async def test_fs_read_cache_get_error_falls_back_to_rpc(self, decorator, mock_executor, cache):
        """Ошибка при получении из кэша fallback на RPC."""
        mock_executor.execute.return_value = ToolExecutionResult(
            success=True,
            output="rpc content",
        )
        session = MagicMock()
        arguments = {"operation": "read", "path": "/test.py"}

        with pytest.MonkeyPatch().context() as m:
            m.setattr(cache, "get", MagicMock(side_effect=Exception("cache get error")))
            result = await decorator.execute(session, arguments)

        # Проверяем, что wrapped.execute() был вызван (fallback)
        mock_executor.execute.assert_called_once()
        assert result.success is True
        assert result.output == "rpc content"

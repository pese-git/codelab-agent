"""Тесты покрытия непокрытых веток CachedSessionStorage."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from codelab.server.protocol.state import SessionState
from codelab.server.storage.cached import CachedSessionStorage


@pytest.fixture
def backend() -> AsyncMock:
    """Создаёт mock backend хранилища."""
    return AsyncMock()


@pytest.fixture
def storage(backend: AsyncMock) -> CachedSessionStorage:
    """Создаёт кэширующее хранилище с mock backend."""
    return CachedSessionStorage(backend=backend, max_size=2)


class TestCachedStoragePutUpdate:
    """Тесты обновления существующей записи в кэше."""

    @pytest.mark.asyncio
    async def test_put_updates_existing_cache_entry(
        self,
        storage: CachedSessionStorage,
        backend: AsyncMock,
    ) -> None:
        """Повторное сохранение той же сессии обновляет кэш (строки 55-56)."""
        session1 = SessionState(session_id="s1", cwd="/tmp", mcp_servers=[])
        session2 = SessionState(session_id="s1", cwd="/work", mcp_servers=[])

        await storage.save_session(session1)
        await storage.save_session(session2)

        cached = storage._cache["s1"]
        assert cached.cwd == "/work"
        assert storage.cache_size == 1


class TestCachedStorageLoadFromBackend:
    """Тесты загрузки сессии из backend в кэш."""

    @pytest.mark.asyncio
    async def test_load_from_backend_caches_session(
        self,
        storage: CachedSessionStorage,
        backend: AsyncMock,
    ) -> None:
        """Загрузка из backend помещает сессию в кэш (строки 77-80)."""
        session = SessionState(session_id="s1", cwd="/tmp", mcp_servers=[])
        backend.load_session.return_value = session

        result = await storage.load_session("s1")

        assert result is session
        assert "s1" in storage._cache
        backend.load_session.assert_awaited_once_with("s1")

    @pytest.mark.asyncio
    async def test_load_from_backend_none_not_cached(
        self,
        storage: CachedSessionStorage,
        backend: AsyncMock,
    ) -> None:
        """Отсутствующая сессия не добавляется в кэш."""
        backend.load_session.return_value = None

        result = await storage.load_session("missing")

        assert result is None
        assert "missing" not in storage._cache


class TestCachedStorageSessionExists:
    """Тесты проверки существования сессии в кэше."""

    @pytest.mark.asyncio
    async def test_session_exists_cache_hit(
        self,
        storage: CachedSessionStorage,
        backend: AsyncMock,
    ) -> None:
        """Сессия в кэше найдена без обращения к backend (строка 99)."""
        session = SessionState(session_id="s1", cwd="/tmp", mcp_servers=[])
        storage._cache["s1"] = session

        result = await storage.session_exists("s1")

        assert result is True
        backend.session_exists.assert_not_called()

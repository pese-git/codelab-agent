"""Unit тесты для FileContentCache и SessionFileCacheRegistry."""

from codelab.server.agent.context.file_cache import (
    InMemoryFileCache,
    InvalidationSignalBus,
    SessionFileCacheRegistry,
)


class TestInvalidationSignalBus:
    """Тесты для InvalidationSignalBus."""

    def test_publish_calls_subscribers(self):
        """publish() вызывает всех подписчиков."""
        bus = InvalidationSignalBus()
        received: list[str] = []
        bus.subscribe(lambda path: received.append(path))

        bus.publish("/test.py")

        assert received == ["/test.py"]

    def test_publish_multiple_subscribers(self):
        """publish() вызывает нескольких подписчиков."""
        bus = InvalidationSignalBus()
        received1: list[str] = []
        received2: list[str] = []
        bus.subscribe(lambda path: received1.append(path))
        bus.subscribe(lambda path: received2.append(path))

        bus.publish("/test.py")

        assert received1 == ["/test.py"]
        assert received2 == ["/test.py"]

    def test_unsubscribe(self):
        """unsubscribe() удаляет подписчика."""
        bus = InvalidationSignalBus()
        received: list[str] = []

        def callback(path: str) -> None:
            received.append(path)

        bus.subscribe(callback)
        bus.unsubscribe(callback)

        bus.publish("/test.py")

        assert received == []

    def test_publish_handles_callback_error(self):
        """publish() обрабатывает ошибки callback'ов."""
        bus = InvalidationSignalBus()
        received: list[str] = []

        def failing_callback(path: str) -> None:
            raise ValueError("test error")

        bus.subscribe(failing_callback)
        bus.subscribe(lambda path: received.append(path))

        bus.publish("/test.py")

        assert received == ["/test.py"]


class TestInMemoryFileCache:
    """Тесты для InMemoryFileCache."""

    def test_get_returns_none_on_miss(self):
        """get() возвращает None при промахе."""
        cache = InMemoryFileCache()
        assert cache.get("/nonexistent.py") is None

    def test_set_and_get(self):
        """set() + get() работает."""
        cache = InMemoryFileCache()
        cache.set("/test.py", "content")
        assert cache.get("/test.py") == "content"

    def test_get_updates_access_order(self):
        """get() перемещает в конец (most recently used)."""
        cache = InMemoryFileCache(max_files=3)
        cache.set("/a.py", "a")
        cache.set("/b.py", "b")
        cache.set("/c.py", "c")

        cache.get("/a.py")

        assert list(cache._cache.keys()) == ["/b.py", "/c.py", "/a.py"]

    def test_lru_eviction(self):
        """При превышении max_files — LRU eviction."""
        cache = InMemoryFileCache(max_files=3)
        cache.set("/a.py", "a")
        cache.set("/b.py", "b")
        cache.set("/c.py", "c")

        cache.set("/d.py", "d")

        assert cache.size == 3
        assert cache.get("/a.py") is None
        assert cache.get("/b.py") == "b"
        assert cache.get("/d.py") == "d"

    def test_lru_eviction_respects_access_order(self):
        """LRU eviction учитывает порядок доступа."""
        cache = InMemoryFileCache(max_files=3)
        cache.set("/a.py", "a")
        cache.set("/b.py", "b")
        cache.set("/c.py", "c")

        cache.get("/a.py")
        cache.set("/d.py", "d")

        assert cache.get("/b.py") is None
        assert cache.get("/a.py") == "a"

    def test_set_updates_existing(self):
        """set() обновляет существующую запись."""
        cache = InMemoryFileCache()
        cache.set("/test.py", "old")
        cache.set("/test.py", "new")

        assert cache.get("/test.py") == "new"
        assert cache.size == 1

    def test_invalidate_removes_entry(self):
        """invalidate() удаляет запись."""
        cache = InMemoryFileCache()
        cache.set("/test.py", "content")

        cache.invalidate("/test.py")

        assert cache.get("/test.py") is None

    def test_invalidate_publishes_signal(self):
        """invalidate() публикует сигнал."""
        bus = InvalidationSignalBus()
        cache = InMemoryFileCache(signal_bus=bus)
        received: list[str] = []
        bus.subscribe(lambda path: received.append(path))

        cache.invalidate("/test.py")

        assert received == ["/test.py"]

    def test_invalidate_nonexistent_publishes_signal(self):
        """invalidate() несуществующего пути публикует сигнал."""
        bus = InvalidationSignalBus()
        cache = InMemoryFileCache(signal_bus=bus)
        received: list[str] = []
        bus.subscribe(lambda path: received.append(path))

        cache.invalidate("/nonexistent.py")

        assert received == ["/nonexistent.py"]

    def test_clear(self):
        """clear() очищает кэш."""
        cache = InMemoryFileCache()
        cache.set("/a.py", "a")
        cache.set("/b.py", "b")

        cache.clear()

        assert cache.size == 0
        assert cache.get("/a.py") is None

    def test_signal_bus_property(self):
        """signal_bus property возвращает шину."""
        bus = InvalidationSignalBus()
        cache = InMemoryFileCache(signal_bus=bus)
        assert cache.signal_bus is bus


class TestSessionFileCacheRegistry:
    """Тесты для SessionFileCacheRegistry."""

    def test_get_or_create_new_session(self):
        """get_or_create() создаёт новый кэш."""
        registry = SessionFileCacheRegistry()
        cache = registry.get_or_create("session_1")

        assert cache is not None
        assert "session_1" in registry.active_sessions

    def test_get_or_create_existing_session(self):
        """get_or_create() возвращает существующий кэш."""
        registry = SessionFileCacheRegistry()
        cache1 = registry.get_or_create("session_1")
        cache2 = registry.get_or_create("session_1")

        assert cache1 is cache2

    def test_get_returns_none_for_unknown(self):
        """get() возвращает None для неизвестной сессии."""
        registry = SessionFileCacheRegistry()
        assert registry.get("unknown") is None

    def test_close_session_clears_cache(self):
        """close_session() очищает кэш."""
        registry = SessionFileCacheRegistry()
        cache = registry.get_or_create("session_1")
        cache.set("/test.py", "content")

        registry.close_session("session_1")

        assert "session_1" not in registry.active_sessions
        assert cache.size == 0

    def test_close_session_nonexistent(self):
        """close_session() несуществующей сессии — no-op."""
        registry = SessionFileCacheRegistry()
        registry.close_session("nonexistent")

    def test_active_sessions(self):
        """active_sessions возвращает список активных сессий."""
        registry = SessionFileCacheRegistry()
        registry.get_or_create("session_1")
        registry.get_or_create("session_2")

        sessions = registry.active_sessions

        assert set(sessions) == {"session_1", "session_2"}

    def test_close_all(self):
        """close_all() закрывает все сессии."""
        registry = SessionFileCacheRegistry()
        registry.get_or_create("session_1")
        registry.get_or_create("session_2")

        registry.close_all()

        assert registry.active_sessions == []

    def test_shared_signal_bus(self):
        """Все кэши используют общую шину сигналов."""
        bus = InvalidationSignalBus()
        registry = SessionFileCacheRegistry(signal_bus=bus)
        cache1 = registry.get_or_create("session_1")
        cache2 = registry.get_or_create("session_2")

        assert cache1.signal_bus is bus
        assert cache2.signal_bus is bus

    def test_max_files_per_session(self):
        """max_files_per_session применяется к каждому кэшу."""
        registry = SessionFileCacheRegistry(max_files_per_session=5)
        cache = registry.get_or_create("session_1")

        assert cache._max_files == 5

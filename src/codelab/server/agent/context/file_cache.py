"""FileContentCache — кэш содержимого файлов.

Слой C — Хранение (Phase 2).

Компоненты:
- InMemoryFileCache: LRU кэш с сигналом инвалидации
- SessionFileCacheRegistry: управление жизненным циклом кэша сессий
- InvalidationSignalBus: единый источник сигналов изменения (интеграция с Фазой 4)
"""

from __future__ import annotations

import contextlib
import logging
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from codelab.server.agent.context.interfaces import FileContentCache

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

InvalidationCallback = Callable[[str], None]


@dataclass
class InvalidationSignalBus:
    """Единый источник сигналов изменения файлов.

    Точка интеграции Фаза 2 ↔ Фаза 4:
    FileCacheDecorator.invalidate() публикует сигнал →
    ContextReconciler подписывается для обнаружения изменений.
    """

    _callbacks: list[InvalidationCallback] = field(default_factory=list)

    def subscribe(self, callback: InvalidationCallback) -> None:
        """Подписаться на сигналы инвалидации."""
        self._callbacks.append(callback)

    def unsubscribe(self, callback: InvalidationCallback) -> None:
        """Отписаться от сигналов."""
        with contextlib.suppress(ValueError):
            self._callbacks.remove(callback)

    def publish(self, path: str) -> None:
        """Опубликовать сигнал изменения файла."""
        for callback in self._callbacks:
            try:
                callback(path)
            except Exception:
                logger.exception(
                    "invalidation_callback_failed: path=%s callback=%s",
                    path,
                    callback.__name__,
                )


class InMemoryFileCache(FileContentCache):
    """LRU кэш содержимого файлов.

    При достижении cache_max_files вытесняет наименее недавно использованную запись.
    invalidate() публикует сигнал в InvalidationSignalBus.

    Attributes:
        _cache: OrderedDict для LRU (ключ → содержимое)
        _max_files: Максимальное количество файлов в кэше
        _signal_bus: Шина сигналов инвалидации
    """

    def __init__(
        self,
        max_files: int = 1000,
        signal_bus: InvalidationSignalBus | None = None,
    ) -> None:
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._max_files = max_files
        self._signal_bus = signal_bus or InvalidationSignalBus()

    @property
    def signal_bus(self) -> InvalidationSignalBus:
        """Шина сигналов инвалидации."""
        return self._signal_bus

    @property
    def size(self) -> int:
        """Текущий размер кэша."""
        return len(self._cache)

    def get(self, path: str) -> str | None:
        """Получить содержимое из кэша.

        При попадании — перемещает в конец (most recently used).
        """
        if path not in self._cache:
            logger.debug("file_cache_miss: path=%s", path)
            return None

        self._cache.move_to_end(path)
        logger.debug("file_cache_hit: path=%s", path)
        return self._cache[path]

    def set(self, path: str, content: str) -> None:
        """Сохранить содержимое в кэш.

        При превышении max_files — LRU eviction.
        """
        if path in self._cache:
            self._cache.move_to_end(path)
            self._cache[path] = content
            return

        if len(self._cache) >= self._max_files:
            evicted_path, _ = self._cache.popitem(last=False)
            logger.debug("file_cache_evicted: path=%s", evicted_path)

        self._cache[path] = content

    def invalidate(self, path: str) -> None:
        """Сбросить кэш по пути. Публикует сигнал изменения."""
        if path in self._cache:
            del self._cache[path]
            logger.debug("file_cache_invalidated: path=%s", path)

        self._signal_bus.publish(path)

    def clear(self) -> None:
        """Очистить весь кэш."""
        self._cache.clear()


class SessionFileCacheRegistry:
    """Реестр файловых кэшей для каждой сессии.

    Управляет жизненным циклом: создание при начале сессии,
    освобождение памяти при закрытии.
    """

    def __init__(
        self,
        max_files_per_session: int = 1000,
        signal_bus: InvalidationSignalBus | None = None,
    ) -> None:
        self._caches: dict[str, InMemoryFileCache] = {}
        self._max_files = max_files_per_session
        self._signal_bus = signal_bus or InvalidationSignalBus()

    def get_or_create(self, session_id: str) -> InMemoryFileCache:
        """Получить или создать кэш для сессии."""
        if session_id not in self._caches:
            self._caches[session_id] = InMemoryFileCache(
                max_files=self._max_files,
                signal_bus=self._signal_bus,
            )
            logger.debug("file_cache_created: session_id=%s", session_id)

        return self._caches[session_id]

    def get(self, session_id: str) -> InMemoryFileCache | None:
        """Получить кэш сессии (без создания)."""
        return self._caches.get(session_id)

    def close_session(self, session_id: str) -> None:
        """Освободить память кэша при закрытии сессии."""
        cache = self._caches.pop(session_id, None)
        if cache is not None:
            cache.clear()
            logger.debug("file_cache_closed: session_id=%s", session_id)

    @property
    def active_sessions(self) -> list[str]:
        """Список активных сессий."""
        return list(self._caches.keys())

    def close_all(self) -> None:
        """Закрыть все сессии."""
        for session_id in list(self._caches.keys()):
            self.close_session(session_id)

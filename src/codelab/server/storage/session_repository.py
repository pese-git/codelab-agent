"""Доменный порт хранилища сессий (каркас D4-d, ADR-006).

`SessionRepository` — единственный шов между доменным агрегатом `Session` и
wire-DTO `SessionState`. После switch'а резидентом рабочей модели становится
домен, а `SessionState` живёт только внутри этого порта и на диске.

Асимметрия порта — CQRS-lite (решение D4-d, тезис 3):
- `load_session`/`save_session` — доменные (write-model, богатый агрегат);
- `list_sessions` — облегчённая wire-проекция (read-model): для `session/list`
  нужны title/updated_at/cwd, реконструировать поведение агрегата незачем.

Кэш держит ДОМЕННЫЙ агрегат (решение D4-d, тезис 1): in-place-мутационный
контракт turn'а держится на идентичности резидента — `load_session` на cache-hit
обязан вернуть ТОТ ЖЕ объект, иначе мутации разных участков turn'а разъезжаются
(split-brain). Поэтому `to_domain` выполняется только на cache-miss,
`to_protocol` — на `save_session`.

НЕ наследует `SessionStorage`: имена методов совпадают намеренно (чтобы switch
call-сайтов был механическим), но тип рабочей модели другой — доменный `Session`
вместо wire `SessionState`, поэтому это не подтип и не взаимозаменяемо с backend.
"""

from __future__ import annotations

from collections import OrderedDict

import structlog

from ..domain.session import Session
from ..mapping.session_mapper import SessionMapper
from ..protocol.state import SessionState
from .base import SessionStorage

logger = structlog.get_logger()

DEFAULT_CACHE_SIZE = 200  # максимум резидентных сессий в памяти


class SessionRepository:
    """Хранилище сессий, типизированное доменным агрегатом.

    Оборачивает wire-типизированный `SessionStorage` backend и держит LRU-кэш
    доменных агрегатов. Backend отвечает за диск, репозиторий — за конверсию
    и идентичность резидента.

    Пример использования:
        repository = SessionRepository(backend=JsonFileStorage(path))
        session = await repository.load_session("sess_1")
        session.set_title("Моя сессия")
        await repository.save_session(session)
    """

    def __init__(
        self,
        backend: SessionStorage,
        max_size: int = DEFAULT_CACHE_SIZE,
    ) -> None:
        """Инициализирует репозиторий.

        Args:
            backend: Wire-типизированное хранилище для персистентности.
                Ожидается backend БЕЗ собственного кэша сессий: кэш резидента
                живёт здесь, второй уровень кэширования дал бы split-brain.
            max_size: Максимальное количество резидентных сессий в LRU-кэше.
        """
        self._backend = backend
        self._max_size = max_size
        # OrderedDict работает как LRU: move_to_end при каждом обращении
        self._cache: OrderedDict[str, Session] = OrderedDict()

    async def load_session(self, session_id: str) -> Session | None:
        """Возвращает резидентный доменный агрегат сессии.

        На cache-hit возвращает ТОТ ЖЕ объект (идентичность резидента —
        основа in-place-мутационного контракта turn'а).

        Returns:
            Доменный `Session` либо None, если сессии не существует.
        """
        cached = self._cache.get(session_id)
        if cached is not None:
            self._cache.move_to_end(session_id)
            return cached

        state = await self._backend.load_session(session_id)
        if state is None:
            return None

        session = SessionMapper.to_domain(state)
        self._put(session)
        return session

    async def save_session(self, session: Session) -> None:
        """Персистит доменный агрегат и оставляет его резидентным."""
        state = SessionMapper.to_protocol(session)
        await self._backend.save_session(state)
        # Backend штампует метку сохранения на wire-DTO; возвращаем её в резидент,
        # иначе доменный `updated_at` разъедется с тем, что легло на диск.
        session.updated_at = state.updated_at
        self._put(session)

    async def delete_session(self, session_id: str) -> bool:
        """Удаляет сессию из кэша и backend."""
        self._cache.pop(session_id, None)
        return await self._backend.delete_session(session_id)

    async def session_exists(self, session_id: str) -> bool:
        """Проверяет существование сессии в кэше или backend."""
        if session_id in self._cache:
            return True
        return await self._backend.session_exists(session_id)

    async def list_sessions(
        self,
        cwd: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> tuple[list[SessionState], str | None]:
        """Возвращает wire-проекцию списка сессий (read-model, CQRS-lite).

        Делегирует в backend, минуя кэш резидентов — как и `CachedSessionStorage`:
        значения читаются с диска, поэтому несохранённые мутации резидента здесь
        не видны (поведение сохранено как есть).
        """
        return await self._backend.list_sessions(cwd=cwd, cursor=cursor, limit=limit)

    def _put(self, session: Session) -> None:
        """Добавить в кэш, вытолкнув самую старую запись при переполнении."""
        session_id = str(session.id)
        if session_id in self._cache:
            self._cache.move_to_end(session_id)
            self._cache[session_id] = session
            return
        if len(self._cache) >= self._max_size:
            evicted_id, _ = self._cache.popitem(last=False)
            logger.debug("session_repository_cache_evicted", session_id=evicted_id)
        self._cache[session_id] = session

    @property
    def cache_size(self) -> int:
        """Текущее количество резидентных сессий."""
        return len(self._cache)

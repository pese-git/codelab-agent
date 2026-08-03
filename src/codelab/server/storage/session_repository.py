"""Доменный порт хранилища сессий (каркас D4-d1, ADR-006).

`SessionRepository` — единственный шов между доменным агрегатом `Session` и
wire-DTO `SessionState`. После switch'а рабочей моделью прикладных путей
становится домен, а `SessionState` живёт только внутри этого порта и на диске.

Асимметрия порта — CQRS-lite (решение D4-d, тезис 3):
- `load_session`/`save_session` — доменные (write-model, богатый агрегат);
- `list_sessions` — облегчённая wire-проекция (read-model): для `session/list`
  нужны title/updated_at/cwd, реконструировать поведение агрегата незачем.

БЕЗ КЭША — намеренно (ревизия тезиса 1 по итогам аудита D4-d, 2026-07-27).
Прод-вход (`codelab serve` → `cli.py`) собирает `JsonFileStorage` без обёртки,
поэтому сегодня каждый `load_session` отдаёт свежий объект, а `domain_session`
пересобирается на turn и выбрасывается. Резидентной идентичности в проде нет.
Кэш доменных агрегатов ввёл бы её — и вместе с ней незаявленное изменение
поведения: сайты, которые мутируют сессию без `save` (например `session/load`
в `handlers/session.py` — правит `cwd`/`mcp_servers` и не сохраняет), начали бы
удерживать мутации в памяти. Поэтому switch типа (D4-d1) делается
behavior-neutral, а резидентный кэш — отдельным осознанным шагом (D4-d2).

НЕ наследует `SessionStorage`: имена методов совпадают намеренно (чтобы switch
call-сайтов был механическим), но тип рабочей модели другой — доменный `Session`
вместо wire `SessionState`, поэтому это не подтип и не взаимозаменяемо с backend.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog

from ..domain.session import Session
from ..mapping.session_mapper import SessionMapper
from ..protocol.state import SessionState
from .base import SessionStorage

logger = structlog.get_logger()


class SessionRepository:
    """Хранилище сессий, типизированное доменным агрегатом.

    Оборачивает wire-типизированный `SessionStorage` backend: backend отвечает
    за персистентность, репозиторий — за конверсию на границе.

    Пример использования:
        repository = SessionRepository(backend=JsonFileStorage(path))
        session = await repository.load_session("sess_1")
        session.set_title("Моя сессия")
        await repository.save_session(session)
    """

    def __init__(self, backend: SessionStorage) -> None:
        """Инициализирует репозиторий.

        Args:
            backend: Wire-типизированное хранилище для персистентности.
        """
        self._backend = backend
        # Блокировки на сессию для `transaction()`: turn разорван круговыми обменами
        # с клиентом, поэтому пересекающиеся запросы по одной сессии — норма, и без
        # сериализации они затирают решения друг друга (ADR-007).
        self._locks: dict[str, asyncio.Lock] = {}

    @asynccontextmanager
    async def transaction(self, session_id: str) -> AsyncIterator[Session | None]:
        """Область транзакции над сессией: одна загрузка, запись на успешном выходе.

        Инвариант владения из ADR-007: состояние принадлежит транзакции, а не
        процессу и не объекту. Область даёт три вещи конструктивно, а не
        дисциплиной вызывающего:

        * одна загрузка — вторая давала бы вторую копию, и мутации первой терялись
          бы (так был устроен дефект P2-42);
        * блокировка на сессию — пересекающиеся запросы не затирают решения друг
          друга;
        * запись при успешном выходе и её отсутствие при исключении — забыть
          сохранение больше нельзя, а неудачная транзакция не оставляет полуправки.

        Отдаёт `None`, если сессии нет: вызывающий возвращает свою ошибку, записи не
        происходит.

        Повторный вход по той же сессии внутри области — взаимная блокировка:
        транзакция одна на запрос, вложенных не бывает.

        Пример использования:
            async with repository.transaction("sess_1") as session:
                if session is None:
                    return not_found()
                session.set_title("Моя сессия")
        """
        lock = self._locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            session = await self.load_session(session_id)
            yield session
            if session is None:
                return
            await self.save_session(session)
            logger.debug("session_transaction_committed", session_id=session_id)

    async def load_session(self, session_id: str) -> Session | None:
        """Загружает сессию как доменный агрегат.

        Returns:
            Доменный `Session` либо None, если сессии не существует.
        """
        state = await self._backend.load_session(session_id)
        if state is None:
            return None
        return SessionMapper.to_domain(state)

    async def save_session(self, session: Session) -> None:
        """Персистит доменный агрегат."""
        state = SessionMapper.to_protocol(session)
        await self._backend.save_session(state)
        # Backend штампует метку сохранения и ревизию на wire-DTO. Сегодня он
        # делает это in-place на объекте вызывающего, поэтому тот видит свежую
        # метку сразу после save (её кладут в session_info-нотификации). Для
        # агрегата этот объект — одноразовая проекция, и без возврата штампов он
        # остаётся на ревизии загрузки: следующая запись упирается в CAS. Ровно
        # этот класс дефектов дал зависший turn на шаге 3 (ADR-006, фаза D).
        session.updated_at = state.updated_at
        session.revision = state.revision

    async def delete_session(self, session_id: str) -> bool:
        """Удаляет сессию."""
        return await self._backend.delete_session(session_id)

    async def session_exists(self, session_id: str) -> bool:
        """Проверяет существование сессии."""
        return await self._backend.session_exists(session_id)

    async def list_sessions(
        self,
        cwd: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> tuple[list[SessionState], str | None]:
        """Возвращает wire-проекцию списка сессий (read-model, CQRS-lite).

        Для поиска сессии по вторичному ключу с последующей мутацией эта
        проекция НЕ подходит — используйте `iter_sessions`.
        """
        return await self._backend.list_sessions(cwd=cwd, cursor=cursor, limit=limit)

    async def iter_sessions(
        self,
        cwd: str | None = None,
        page_size: int = 100,
    ) -> AsyncIterator[Session]:
        """Доменный обход всех сессий с внутренней пагинацией (write-model).

        Примитив для поиска сессии по вторичному ключу (`active_turn`,
        cancelled-tombstones и т.п.): выдаёт агрегаты, которые ЗАКОННО мутировать
        и сохранять — в отличие от read-model `list_sessions`. Именующие обёртки
        (`find_session_by_permission_request_id` и соседи) остаются на своих
        местах и строятся поверх этого обхода.

        ВНИМАНИЕ: найдя нужную сессию, прекратите обход (`break`/`return`).
        Продолжать итерацию ПОСЛЕ `save_session` нельзя: курсор постраничного
        обхода опирается на порядок по `updated_at`, а сохранение меняет метку и
        переставляет сессию — оставшиеся страницы могут задвоиться или пропустить
        записи.

        Полный скан: индекса вторичных ключей у хранилища нет (как и сегодня).
        """
        cursor: str | None = None
        while True:
            page, cursor = await self._backend.list_sessions(
                cwd=cwd, cursor=cursor, limit=page_size
            )
            for state in page:
                yield SessionMapper.to_domain(state)
            if cursor is None:
                return

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

from ..domain.session import Session
from ..mapping.session_mapper import SessionMapper
from ..protocol.state import SessionState
from .base import SessionStorage


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
        # Backend штампует метку сохранения на wire-DTO. Сегодня он делает это
        # in-place на объекте вызывающего, поэтому тот видит свежую метку сразу
        # после save (её кладут в session_info-нотификации). Возвращаем штамп в
        # домен, чтобы switch остался behavior-neutral.
        session.updated_at = state.updated_at

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
        проекция НЕ подходит — такие пути должны получить доменные finder'ы
        (см. аудит D4-d: `permissions`, `client_rpc_response`, `core.cancel_all`).
        """
        return await self._backend.list_sessions(cwd=cwd, cursor=cursor, limit=limit)

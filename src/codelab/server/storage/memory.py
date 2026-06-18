"""In-memory реализация хранилища сессий."""

from __future__ import annotations

from datetime import UTC, datetime

from ..protocol.state import SessionState
from .base import SessionStorage


class InMemoryStorage(SessionStorage):
    """Хранилище сессий в памяти процесса.

    Простая реализация для development и тестирования.
    Все данные теряются при перезапуске сервера.

    Пример использования:
        storage = InMemoryStorage()
        await storage.save_session(session)
        loaded = await storage.load_session(session_id)
    """

    def __init__(self) -> None:
        """Инициализирует пустое хранилище."""
        self._sessions: dict[str, SessionState] = {}

    async def save_session(self, session: SessionState) -> None:
        """Сохраняет сессию в памяти.

        Обновляет временную метку updated_at при каждом сохранении.

        Args:
            session: Состояние сессии для сохранения.

        Raises:
            StorageError: При ошибке сохранения (не должно происходить для памяти).
        """
        # Обновить updated_at при каждом сохранении
        session.updated_at = datetime.now(UTC).isoformat()
        self._sessions[session.session_id] = session

    async def load_session(self, session_id: str) -> SessionState | None:
        """Загружает сессию из памяти.

        Args:
            session_id: Идентификатор сессии.

        Returns:
            SessionState если найдена, None если не существует.

        Raises:
            StorageError: При ошибке загрузки (не должно происходить для памяти).
        """
        return self._sessions.get(session_id)

    async def delete_session(self, session_id: str) -> bool:
        """Удаляет сессию из памяти.

        Args:
            session_id: Идентификатор сессии.

        Returns:
            True если сессия была удалена, False если не существовала.

        Raises:
            StorageError: При ошибке удаления (не должно происходить для памяти).
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    async def list_sessions(
        self,
        cwd: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> tuple[list[SessionState], str | None]:
        """Возвращает список сессий с фильтрацией и пагинацией.

        Фильтрует по рабочей директории и поддерживает курсор-based пагинацию.

        Args:
            cwd: Фильтр по рабочей директории (опционально).
            cursor: Курсор для пагинации (session_id последней сессии предыдущей страницы).
            limit: Максимальное количество сессий на странице.

        Returns:
            Кортеж (список сессий, следующий курсор или None).

        Raises:
            StorageError: При ошибке получения списка (не должно происходить для памяти).
        """
        # Фильтрация по cwd
        sessions = list(self._sessions.values())
        if cwd is not None:
            sessions = [s for s in sessions if s.cwd == cwd]

        # Сортировка по updated_at (новые первыми)
        sessions.sort(key=lambda s: s.updated_at, reverse=True)

        # Пагинация
        start_index = 0
        if cursor:
            # Найти позицию курсора (session_id последней сессии предыдущей страницы)
            for i, s in enumerate(sessions):
                if s.session_id == cursor:
                    start_index = i + 1
                    break

        # Получить страницу
        page = sessions[start_index : start_index + limit]

        # Следующий курсор (если есть ещё сессии)
        next_cursor = None
        if start_index + limit < len(sessions):
            next_cursor = page[-1].session_id if page else None

        return page, next_cursor

    async def session_exists(self, session_id: str) -> bool:
        """Проверяет существование сессии.

        Args:
            session_id: Идентификатор сессии.

        Returns:
            True если сессия существует, False иначе.

        Raises:
            StorageError: При ошибке проверки (не должно происходить для памяти).
        """
        return session_id in self._sessions

"""Базовый интерфейс для хранилища сессий ACP."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..protocol.state import SessionState


class SessionStorage(ABC):
    """Абстрактный интерфейс для хранилища сессий.

    Определяет контракт для различных backend'ов хранения:
    - InMemoryStorage - хранение в памяти (текущее поведение)
    - JsonFileStorage - персистентное хранение в JSON файлах
    - SQLiteStorage - хранение в SQLite БД (опционально)

    Все методы должны быть асинхронными для совместимости с async/await
    в основном протоколе.

    Пример использования:
        >>> storage = InMemoryStorage()  # конкретная реализация
        >>> session = SessionState(session_id="sess_1", cwd="/tmp", mcp_servers=[])
        >>> await storage.save_session(session)
        >>> loaded = await storage.load_session("sess_1")
        >>> assert loaded.session_id == "sess_1"
    """

    @abstractmethod
    async def save_session(self, session: SessionState) -> None:
        """Сохраняет или обновляет сессию в хранилище.

        Если сессия с таким ID уже существует, она будет обновлена.
        Если сессии не существует, она будет создана.

        Args:
            session: Состояние сессии для сохранения.

        Raises:
            StorageError: При ошибке сохранения.

        Пример:
            >>> session = SessionState(session_id="sess_1", cwd="/work", mcp_servers=[])
            >>> await storage.save_session(session)
        """
        pass

    @abstractmethod
    async def load_session(self, session_id: str) -> SessionState | None:
        """Загружает сессию из хранилища по ID.

        Args:
            session_id: Идентификатор сессии.

        Returns:
            SessionState если найдена, None если не существует.

        Raises:
            StorageError: При ошибке загрузки.

        Пример:
            >>> session = await storage.load_session("sess_1")
            >>> if session:
            ...     print(f"Found session {session.cwd}")
        """
        pass

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        """Удаляет сессию из хранилища.

        Args:
            session_id: Идентификатор сессии.

        Returns:
            True если сессия была удалена, False если не существовала.

        Raises:
            StorageError: При ошибке удаления.

        Пример:
            >>> deleted = await storage.delete_session("sess_1")
            >>> print(f"Deleted: {deleted}")
        """
        pass

    @abstractmethod
    async def list_sessions(
        self,
        cwd: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> tuple[list[SessionState], str | None]:
        """Возвращает список сессий с пагинацией.

        Позволяет получать сессии постранично и фильтровать по рабочей директории.

        Args:
            cwd: Фильтр по рабочей директории (опционально).
                Если указана, вернутся только сессии с совпадающей cwd.
            cursor: Курсор для пагинации (опционально).
                Используется для получения следующей страницы результатов.
            limit: Максимальное количество сессий в ответе (по умолчанию 100).

        Returns:
            Кортеж (список сессий, следующий курсор или None).
            Если нет больше сессий, следующий курсор будет None.

        Raises:
            StorageError: При ошибке получения списка.

        Пример:
            >>> sessions, next_cursor = await storage.list_sessions(limit=10)
            >>> print(f"Got {len(sessions)} sessions")
            >>> if next_cursor:
            ...     more_sessions, _ = await storage.list_sessions(cursor=next_cursor)
        """
        pass

    @abstractmethod
    async def session_exists(self, session_id: str) -> bool:
        """Проверяет существование сессии.

        Args:
            session_id: Идентификатор сессии.

        Returns:
            True если сессия существует, False иначе.

        Raises:
            StorageError: При ошибке проверки.

        Пример:
            >>> exists = await storage.session_exists("sess_1")
            >>> if not exists:
            ...     print("Session not found")
        """
        pass

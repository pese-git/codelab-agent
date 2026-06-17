"""Infrastructure реализации Repository интерфейсов.

Содержит конкретные реализации хранилищ для:
- InMemorySessionRepository - in-memory хранилище для разработки
- FileSessionRepository - файловое хранилище для persistence
"""

from __future__ import annotations

import structlog

from codelab.client.domain import Session, SessionRepository


class InMemorySessionRepository(SessionRepository):
    """In-memory реализация SessionRepository.
    
    Хранит сессии в памяти. Используется для:
    - Разработки и тестирования
    - Временных сессий в течение одного запуска
    """
    
    def __init__(self) -> None:
        """Инициализирует in-memory хранилище."""
        self._sessions: dict[str, Session] = {}
        self._logger = structlog.get_logger("in_memory_session_repo")
    
    async def save(self, session: Session) -> None:
        """Сохраняет сессию в памяти.
        
        Аргументы:
            session: Session для сохранения
        """
        self._sessions[session.id] = session
        self._logger.debug("session_saved", session_id=session.id)
    
    async def load(self, session_id: str) -> Session | None:
        """Загружает сессию из памяти.
        
        Аргументы:
            session_id: ID сессии
        
        Возвращает:
            Session или None если не найдена
        """
        session = self._sessions.get(session_id)
        if session is None:
            self._logger.debug("session_not_found", session_id=session_id)
        return session
    
    async def delete(self, session_id: str) -> None:
        """Удаляет сессию из памяти.
        
        Аргументы:
            session_id: ID сессии
        """
        self._sessions.pop(session_id, None)
        self._logger.debug("session_deleted", session_id=session_id)
    
    async def list_all(self) -> list[Session]:
        """Возвращает список всех сессий.
        
        Возвращает:
            Список Session сущностей
        """
        return list(self._sessions.values())
    
    async def exists(self, session_id: str) -> bool:
        """Проверяет наличие сессии.
        
        Аргументы:
            session_id: ID сессии
        
        Возвращает:
            True если сессия существует
        """
        return session_id in self._sessions

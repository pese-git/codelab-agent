"""Repository интерфейсы - абстракции для доступа к данным.

Содержит:
- SessionRepository - сохранение и загрузка сессий
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .entities import Session


class SessionRepository(ABC):
    """Repository для работы с Session сущностями.
    
    Обеспечивает абстрактный доступ к хранилищу сессий,
    независимо от реализации (in-memory, file, database и т.д.).
    """
    
    @abstractmethod
    async def save(self, session: Session) -> None:
        """Сохраняет сессию в хранилище.
        
        Аргументы:
            session: Session сущность для сохранения
        
        Raises:
            RepositoryError: При ошибке сохранения
        """
        ...
    
    @abstractmethod
    async def load(self, session_id: str) -> Session | None:
        """Загружает сессию по ID.
        
        Аргументы:
            session_id: ID сессии для загрузки
        
        Возвращает:
            Session или None если не найдена
        """
        ...
    
    @abstractmethod
    async def delete(self, session_id: str) -> None:
        """Удаляет сессию по ID.
        
        Аргументы:
            session_id: ID сессии для удаления
        """
        ...
    
    @abstractmethod
    async def list_all(self) -> list[Session]:
        """Возвращает список всех сессий.
        
        Возвращает:
            Список всех Session сущностей
        """
        ...
    
    @abstractmethod
    async def exists(self, session_id: str) -> bool:
        """Проверяет наличие сессии.
        
        Аргументы:
            session_id: ID сессии
        
        Возвращает:
            True если сессия существует, False иначе
        """
        ...

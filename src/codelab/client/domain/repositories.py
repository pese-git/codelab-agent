"""Repository интерфейсы - абстракции для доступа к данным.

Содержит:
- SessionRepository - сохранение и загрузка сессий
- HistoryRepository - управление историей сообщений
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

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


class HistoryRepository(ABC):
    """Repository для управления историей сообщений.
    
    Обеспечивает сохранение и загрузку истории
    обмена сообщениями между клиентом и сервером.
    """
    
    @abstractmethod
    async def save_message(
        self,
        session_id: str,
        message_data: dict[str, Any],
    ) -> None:
        """Сохраняет сообщение в историю.
        
        Аргументы:
            session_id: ID сессии
            message_data: Данные сообщения
        """
        ...
    
    @abstractmethod
    async def load_history(self, session_id: str) -> list[dict[str, Any]]:
        """Загружает историю сообщений для сессии.
        
        Аргументы:
            session_id: ID сессии
        
        Возвращает:
            Список сообщений в порядке хронологии
        """
        ...
    
    @abstractmethod
    async def clear_history(self, session_id: str) -> None:
        """Очищает историю для сессии.
        
        Аргументы:
            session_id: ID сессии
        """
        ...
    
    @abstractmethod
    async def delete_history(self, session_id: str) -> None:
        """Удаляет всю историю для сессии.
        
        Аргументы:
            session_id: ID сессии
        """
        ...

"""Entities - основные сущности предметной области.

Содержит:
- Session - сессия с сервером ACP
- Permission - запрос разрешения на действие
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass
class Session:
    """Entity для ACP сессии.
    
    Представляет активную сессию с ACP-сервером и хранит:
    - metadata сессии (ID, время создания)
    - конфигурацию сервера (хост, порт)
    - capabilities (возможности клиента и сервера)
    - статус сессии
    """
    
    id: str
    """Уникальный ID сессии."""
    
    server_host: str
    """Адрес ACP сервера."""
    
    server_port: int
    """Порт ACP сервера."""
    
    client_capabilities: dict[str, Any]
    """Возможности этого клиента (fs, terminal и т.д.)."""
    
    server_capabilities: dict[str, Any]
    """Возможности сервера, полученные при initialize."""
    
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    """Время создания сессии."""
    
    is_authenticated: bool = False
    """Авторизован ли клиент на этой сессии."""
    
    @classmethod
    def create(
        cls,
        server_host: str,
        server_port: int,
        client_capabilities: dict[str, Any],
        server_capabilities: dict[str, Any],
        session_id: str | None = None,
    ) -> Session:
        """Фабрика для создания новой сессии.
        
        Аргументы:
            server_host: Адрес сервера
            server_port: Порт сервера
            client_capabilities: Возможности клиента
            server_capabilities: Возможности сервера
            session_id: ID сессии (если None, генерируется новый)
        
        Возвращает:
            Новую Session сущность
        """
        return cls(
            id=session_id or str(uuid4()),
            server_host=server_host,
            server_port=server_port,
            client_capabilities=client_capabilities,
            server_capabilities=server_capabilities,
        )


@dataclass
class Permission:
    """Entity для запроса разрешения на действие.
    
    Представляет запрос от сервера на выполнение действия,
    которое требует подтверждения от пользователя.
    """
    
    id: str
    """Уникальный ID запроса разрешения."""
    
    action: str
    """Тип действия (read_file, write_file, run_terminal и т.д.)."""
    
    resource: str
    """Ресурс, на который запрашивается разрешение (путь файла, команда и т.д.)."""
    
    session_id: str
    """ID сессии, которой требуется разрешение."""
    
    details: dict[str, Any] = field(default_factory=dict)
    """Дополнительные детали для пользователя."""
    
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    """Время создания запроса."""
    
    @classmethod
    def create(
        cls,
        action: str,
        resource: str,
        session_id: str,
        details: dict[str, Any] | None = None,
    ) -> Permission:
        """Фабрика для создания запроса разрешения.
        
        Аргументы:
            action: Тип действия
            resource: Ресурс
            session_id: ID сессии
            details: Дополнительные детали
        
        Возвращает:
            Permission сущность
        """
        return cls(
            id=str(uuid4()),
            action=action,
            resource=resource,
            session_id=session_id,
            details=details or {},
        )

"""Entities - основные сущности предметной области.

Содержит:
- Session - сессия с сервером ACP
- Permission - запрос разрешения на действие
- ClientCapabilities - возможности клиента
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class ClientCapabilities:
    """Domain model для возможностей клиента.

    Инкапсулирует возможности клиента (файловая система, терминал, мультимодальный ввод).
    """

    fs_read: bool = False
    fs_write: bool = False
    terminal: bool = False
    image_prompts: bool = False
    embedded_context: bool = False

    @property
    def supports_fs(self) -> bool:
        return self.fs_read or self.fs_write

    @property
    def supports_multimodal(self) -> bool:
        return self.image_prompts or self.embedded_context

    def can_read_files(self) -> bool:
        return self.fs_read

    def can_write_files(self) -> bool:
        return self.fs_write

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClientCapabilities:
        return cls(
            fs_read=bool(data.get("fs_read", False)),
            fs_write=bool(data.get("fs_write", False)),
            terminal=bool(data.get("terminal", False)),
            image_prompts=bool(data.get("image_prompts", False)),
            embedded_context=bool(data.get("embedded_context", False)),
        )


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
    
    client_capabilities: ClientCapabilities
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
        client_capabilities: dict[str, Any] | ClientCapabilities,
        server_capabilities: dict[str, Any],
        session_id: str | None = None,
    ) -> Session:
        """Фабрика для создания новой сессии.
        
        Аргументы:
            server_host: Адрес сервера
            server_port: Порт сервера
            client_capabilities: Возможности клиента (dict или ClientCapabilities)
            server_capabilities: Возможности сервера
            session_id: ID сессии (если None, генерируется новый)
        
        Возвращает:
            Новую Session сущность
        """
        caps = (
            client_capabilities
            if isinstance(client_capabilities, ClientCapabilities)
            else ClientCapabilities.from_dict(client_capabilities)
        )
        return cls(
            id=session_id or str(uuid4()),
            server_host=server_host,
            server_port=server_port,
            client_capabilities=caps,
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

"""Entities - основные сущности предметной области.

Содержит:
- Session - сессия с сервером ACP
- Message - сообщение протокола
- Permission - запрос разрешения на действие
- ToolCall - вызов инструмента агентом
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
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
class Message:
    """Entity для сообщения протокола.
    
    Представляет JSON-RPC сообщение с типизацией и metadata.
    """
    
    id: str
    """Уникальный ID сообщения."""
    
    message_type: Literal["request", "response", "notification"]
    """Тип сообщения: request, response или notification."""
    
    method: str | None = None
    """Метод для request/notification."""
    
    params: dict[str, Any] | None = None
    """Параметры метода."""
    
    result: Any = None
    """Результат успешного выполнения (для response)."""
    
    error: dict[str, Any] | None = None
    """Ошибка выполнения (для response)."""
    
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    """Время создания сообщения."""
    
    @classmethod
    def request(
        cls,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> Message:
        """Создает request сообщение.
        
        Аргументы:
            method: Метод для вызова
            params: Параметры метода
        
        Возвращает:
            Message сущность с типом request
        """
        return cls(
            id=str(uuid4()),
            message_type="request",
            method=method,
            params=params,
        )
    
    @classmethod
    def response(
        cls,
        result: Any = None,
        error: dict[str, Any] | None = None,
    ) -> Message:
        """Создает response сообщение.
        
        Аргументы:
            result: Результат успешного выполнения
            error: Ошибка выполнения
        
        Возвращает:
            Message сущность с типом response
        """
        return cls(
            id=str(uuid4()),
            message_type="response",
            result=result,
            error=error,
        )
    
    @classmethod
    def notification(cls, method: str, params: dict[str, Any] | None = None) -> Message:
        """Создает notification сообщение.
        
        Аргументы:
            method: Метод для вызова
            params: Параметры метода
        
        Возвращает:
            Message сущность с типом notification
        """
        return cls(
            id=str(uuid4()),
            message_type="notification",
            method=method,
            params=params,
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


@dataclass
class ToolCall:
    """Entity для вызова инструмента агентом.
    
    Представляет вызов инструмента (tool use) от сервера,
    который требует выполнения на стороне клиента.
    """
    
    id: str
    """Уникальный ID вызова инструмента."""
    
    tool_name: str
    """Имя инструмента."""
    
    tool_use_id: str
    """ID tool use из протокола ACP."""
    
    input_schema: dict[str, Any]
    """JSON schema для input инструмента."""
    
    input: dict[str, Any]
    """Параметры вызова инструмента."""
    
    session_id: str
    """ID сессии, для которой вызывается инструмент."""
    
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    """Время создания вызова."""
    
    result: str | None = None
    """Результат выполнения инструмента."""
    
    error: str | None = None
    """Ошибка при выполнении инструмента."""
    
    @classmethod
    def create(
        cls,
        tool_name: str,
        tool_use_id: str,
        input_schema: dict[str, Any],
        input_data: dict[str, Any],
        session_id: str,
    ) -> ToolCall:
        """Фабрика для создания вызова инструмента.
        
        Аргументы:
            tool_name: Имя инструмента
            tool_use_id: ID из протокола
            input_schema: JSON schema
            input_data: Параметры вызова
            session_id: ID сессии
        
        Возвращает:
            ToolCall сущность
        """
        return cls(
            id=str(uuid4()),
            tool_name=tool_name,
            tool_use_id=tool_use_id,
            input_schema=input_schema,
            input=input_data,
            session_id=session_id,
        )

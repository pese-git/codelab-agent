"""Events - доменные события для Event-Driven архитектуры.

Доменные события представляют важные изменения в системе, которые произошли
в результате бизнес-логики. Они используются для слабой связанности между
компонентами и асинхронной обработки.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class DomainEvent(ABC):
    """Базовый класс для всех доменных событий.
    
    Все события в системе наследуют этот класс и должны быть неизменяемыми
    (frozen=True), так как события - это факты, которые произошли.
    """

    # Идентификатор агрегата (обычно session_id), который генерировал событие
    aggregate_id: str
    # Когда произошло событие (UTC-aware)
    occurred_at: datetime

    def __hash__(self) -> int:
        """Хешируемость для использования в наборах."""
        return hash((self.aggregate_id, self.occurred_at))


# ============================================================================
# Session Events
# ============================================================================


@dataclass(frozen=True)
class SessionCreatedEvent(DomainEvent):
    """Событие: новая сессия была создана."""

    session_id: str  # ID созданной сессии
    server_host: str  # Хост сервера
    server_port: int  # Порт сервера


@dataclass(frozen=True)
class SessionInitializedEvent(DomainEvent):
    """Событие: сессия была инициализирована (получены capabilities)."""

    session_id: str  # ID инициализированной сессии
    capabilities: dict[str, Any]  # Capabilities сервера


@dataclass(frozen=True)
class SessionClosedEvent(DomainEvent):
    """Событие: сессия была закрыта."""

    session_id: str  # ID закрытой сессии
    reason: str  # Причина закрытия


@dataclass(frozen=True)
class SessionLoadedEvent(DomainEvent):
    """Событие: существующая сессия была загружена."""

    session_id: str  # ID загруженной сессии
    from_storage: bool  # Загружена из хранилища или из памяти


# ============================================================================
# Prompt Events
# ============================================================================


@dataclass(frozen=True)
class PromptStartedEvent(DomainEvent):
    """Событие: начался prompt turn."""

    session_id: str  # ID сессии
    prompt_text: str  # Текст промпта


@dataclass(frozen=True)
class PromptCompletedEvent(DomainEvent):
    """Событие: prompt turn завершился успешно."""

    session_id: str  # ID сессии
    stop_reason: str  # Причина остановки (e.g., "tool_use", "end_turn")


@dataclass(frozen=True)
class PromptCancelledEvent(DomainEvent):
    """Событие: prompt turn был отменён пользователем."""

    session_id: str  # ID сессии
    reason: str  # Причина отмены


# ============================================================================
# Permission Events
# ============================================================================


@dataclass(frozen=True)
class PermissionRequestedEvent(DomainEvent):
    """Событие: запрошено разрешение на действие."""

    session_id: str  # ID сессии
    action: str  # Действие (e.g., "execute", "read")
    resource: str  # Ресурс (e.g., "/path/to/file")
    permission_id: str  # Уникальный ID этого запроса


@dataclass(frozen=True)
class PermissionGrantedEvent(DomainEvent):
    """Событие: разрешение было дано."""

    session_id: str  # ID сессии
    permission_id: str  # ID разрешённого запроса
    action: str  # Действие


@dataclass(frozen=True)
class PermissionDeniedEvent(DomainEvent):
    """Событие: разрешение было отклонено."""

    session_id: str  # ID сессии
    permission_id: str  # ID отклонённого запроса
    action: str  # Действие


# ============================================================================
# Error Events
# ============================================================================


@dataclass(frozen=True)
class ErrorOccurredEvent(DomainEvent):
    """Событие: в системе произошла ошибка."""

    error_message: str  # Текст ошибки
    error_type: str  # Тип ошибки (e.g., "TransportError", "ValidationError")
    session_id: str | None = None  # Опциональный ID сессии, где произошла ошибка


@dataclass(frozen=True)
class ConnectionLostEvent(DomainEvent):
    """Событие: соединение с сервером потеряно."""

    session_id: str  # ID сессии
    error_message: str | None = None  # Опциональное описание ошибки


@dataclass(frozen=True)
class ConnectionRestoredEvent(DomainEvent):
    """Событие: соединение с сервером восстановлено."""

    session_id: str  # ID сессии


# ============================================================================
# Tool Call Events
# ============================================================================


@dataclass(frozen=True)
class ToolCallStartedEvent(DomainEvent):
    """Событие: инструмент начал выполняться."""

    session_id: str  # ID сессии
    tool_name: str  # Имя инструмента
    tool_use_id: str  # Уникальный ID вызова


@dataclass(frozen=True)
class ToolCallCompletedEvent(DomainEvent):
    """Событие: инструмент завершил выполнение."""

    session_id: str  # ID сессии
    tool_name: str  # Имя инструмента
    tool_use_id: str  # ID вызова
    result: Any  # Результат выполнения


@dataclass(frozen=True)
class ToolCallFailedEvent(DomainEvent):
    """Событие: выполнение инструмента не удалось."""

    session_id: str  # ID сессии
    tool_name: str  # Имя инструмента
    tool_use_id: str  # ID вызова
    error_message: str  # Описание ошибки


# ============================================================================
# Config Events
# ============================================================================


@dataclass(frozen=True)
class ConfigOptionUpdatedEvent(DomainEvent):
    """Событие: конфигурационная опция сессии была обновлена."""

    session_id: str  # ID сессии
    config_options: list[dict[str, Any]]  # Полный список config options

"""Domain layer - бизнес-логика и интерфейсы сущностей.

Этот слой содержит:
- Entities (Session, Message, Permission, ToolCall и т.д.)
- Repositories интерфейсы (SessionRepository, HistoryRepository и т.д.)
- Domain Services интерфейсы (TransportService и т.д.)

Domain слой не зависит от других слоев архитектуры.
"""

from .entities import Message, Permission, Session, ToolCall
from .repositories import HistoryRepository, SessionRepository
from .services import SessionService, TransportService

__all__ = [
    "Session",
    "Message",
    "Permission",
    "ToolCall",
    "SessionRepository",
    "HistoryRepository",
    "TransportService",
    "SessionService",
]

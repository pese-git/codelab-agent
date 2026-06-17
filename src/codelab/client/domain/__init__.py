"""Domain layer - бизнес-логика и интерфейсы сущностей.

Этот слой содержит:
- Entities (Session, Permission и т.д.)
- Repositories интерфейсы (SessionRepository и т.д.)
- Domain Services интерфейсы (TransportService и т.д.)

Domain слой не зависит от других слоев архитектуры.
"""

from .entities import Permission, Session
from .repositories import SessionRepository
from .services import TransportService

__all__ = [
    "Session",
    "Permission",
    "SessionRepository",
    "TransportService",
]

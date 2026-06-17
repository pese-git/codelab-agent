"""Модуль управления навигацией для TUI приложения.

Предоставляет централизованное управление показом и скрытием экранов,
модальных окон и синхронизацией с ViewModels.
"""

from .manager import (
    ModalNotFoundError,
    NavigationError,
    NavigationManager,
    OperationTimeoutError,
    ScreenStackError,
)
from .operations import (
    NavigationOperation,
    OperationPriority,
    OperationType,
)
from .queue import (
    OperationQueue,
    OperationQueueError,
)
from .tracker import ModalWindowTracker

__all__ = [
    # Manager
    "NavigationManager",
    "NavigationError",
    "ScreenStackError",
    "ModalNotFoundError",
    "OperationTimeoutError",
    # Operations
    "NavigationOperation",
    "OperationType",
    "OperationPriority",
    # Queue
    "OperationQueue",
    "OperationQueueError",
    # Tracker
    "ModalWindowTracker",
]

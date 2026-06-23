"""Базовый декоратор для tool executors.

Реализует Decorator Pattern для добавления дополнительной функциональности
к tool executors без изменения их исходного кода.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from codelab.server.tools.base import ToolExecutionResult

if TYPE_CHECKING:
    from codelab.server.protocol.state import SessionState


@runtime_checkable
class ToolExecutorProtocol(Protocol):
    """Протокол для tool executor.
    
    Определяет интерфейс для выполнения инструментов.
    """
    
    async def execute(
        self,
        session: SessionState,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        """Выполнить инструмент.
        
        Args:
            session: Состояние сессии.
            arguments: Аргументы инструмента.
        
        Returns:
            Результат выполнения инструмента.
        """
        ...


class ToolExecutorDecorator(ABC):
    """Базовый абстрактный декоратор для tool executors.
    
    Реализует Decorator Pattern: оборачивает другой executor
    и добавляет дополнительную функциональность (timeout, retry, metrics, etc).
    
    Subclasses должны реализовать метод execute(), вызывая self._wrapped.execute()
    для делегирования выполнения обёрнутому executor.
    
    Example:
        >>> class TimeoutDecorator(ToolExecutorDecorator):
        ...     async def execute(self, session, arguments):
        ...         return await asyncio.wait_for(
        ...             self._wrapped.execute(session, arguments),
        ...             timeout=self._timeout,
        ...         )
    """
    
    def __init__(self, wrapped: ToolExecutorProtocol) -> None:
        """Инициализация декоратора.
        
        Args:
            wrapped: Оборачиваемый executor.
        """
        self._wrapped = wrapped
    
    @abstractmethod
    async def execute(
        self,
        session: SessionState,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        """Выполнить инструмент с дополнительной логикой.
        
        Args:
            session: Состояние сессии.
            arguments: Аргументы инструмента.
        
        Returns:
            Результат выполнения инструмента.
        """
        ...

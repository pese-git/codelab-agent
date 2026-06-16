"""Базовый класс для всех executors инструментов."""

from abc import ABC, abstractmethod
from typing import Any

from codelab.server.protocol.state import SessionState
from codelab.server.tools.base import ToolExecutionResult


class ToolExecutor(ABC):
    """Базовый класс для асинхронного выполнения инструментов.
    
    Все executor-ы должны наследоваться от этого класса и реализовать
    метод execute() для выполнения инструмента в контексте сессии.
    """

    @abstractmethod
    async def execute(
        self,
        session: SessionState,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        """Выполнить инструмент в контексте сессии.
        
        Args:
            session: Состояние текущей сессии
            arguments: Словарь аргументов инструмента
            
        Returns:
            ToolExecutionResult с результатом выполнения
            
        Raises:
            Может выбросить исключения, которые будут обработаны
            в execute_tool() реестра.
        """
        pass

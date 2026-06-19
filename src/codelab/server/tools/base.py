"""Базовые интерфейсы для системы инструментов."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from codelab.server.domain.value_objects import FileLocation


@dataclass
class ToolDefinition:
    """Определение инструмента для LLM."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    kind: str  # "terminal", "filesystem", "other"
    requires_permission: bool = True


@dataclass
class ToolExecutionResult:
    """Результат выполнения инструмента.

    Domain model — не содержит ACP-specific content.
    Для конвертации в ACP format использовать ToolResultMapper.

    Атрибуты:
        success: Успешно ли выполнен инструмент
        output: Текстовый вывод инструмента (опционально)
        error: Сообщение об ошибке при неудачном выполнении (опционально)
        metadata: Дополнительные метаданные для специфичных инструментов (опционально)
        locations: Затронутые файлы (domain model)
        raw_output: Исходный результат выполнения для ACP rawOutput
    """

    success: bool
    output: str | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None
    locations: list[FileLocation] = field(default_factory=list)
    raw_output: dict[str, Any] = field(default_factory=dict)


class ToolRegistry(ABC):
    """Реестр инструментов с механизмом выполнения."""

    @abstractmethod
    def register(
        self,
        tool: ToolDefinition,
        handler: Callable,
    ) -> None:
        """Регистрация инструмента и его обработчика.

        Args:
            tool: Определение инструмента (ToolDefinition)
            handler: Callable обработчик инструмента
        """
        pass

    @abstractmethod
    def register_tool(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        kind: str,
        executor: Callable,
        requires_permission: bool = True,
    ) -> None:
        """Регистрация инструмента."""
        pass

    @abstractmethod
    def get_available_tools(
        self,
        session_id: str,
        include_permission_required: bool = True,
    ) -> list[ToolDefinition]:
        """Получить доступные инструменты для сессии."""
        pass

    @abstractmethod
    def get(self, name: str) -> ToolDefinition | None:
        """Получить определение инструмента по имени.
        
        Args:
            name: Имя инструмента
            
        Returns:
            Определение инструмента или None, если не найден
        """
        pass

    @abstractmethod
    def list_tools(self) -> list[ToolDefinition]:
        """Получить список всех зарегистрированных инструментов.
        
        Returns:
            Список определений инструментов
        """
        pass

    @abstractmethod
    def to_llm_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        """Преобразовать определения инструментов для LLM."""
        pass

    @abstractmethod
    async def execute_tool(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        session: Any = None,
    ) -> ToolExecutionResult:
        """Выполнить инструмент."""
        pass

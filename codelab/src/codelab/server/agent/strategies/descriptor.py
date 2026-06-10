"""StrategyDescriptor и StrategyDependencies.

Self-describing стратегии выполнения с metadata для UI и factory для создания экземпляров.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codelab.server.agent.base import LLMAgent
    from codelab.server.agent.event_bus.bus import AgentEventBus
    from codelab.server.agent.execution_engine import ExecutionEngine
    from codelab.server.agent.registry import AgentRegistry
    from codelab.server.observability.tracer import Tracer


@dataclass
class StrategyDependencies:
    """Контейнер зависимостей для создания стратегии.
    
    Единый контейнер для DI, упрощает factory в StrategyDescriptor.
    
    Attributes:
        event_bus: Шина событий для вызова агентов
        execution_engine: Движок выполнения для сборки контекста
        tracer: Tracer для observability (опционально)
        agent_name: Имя агента по умолчанию
    """
    
    event_bus: AgentEventBus
    execution_engine: ExecutionEngine
    tracer: Tracer | None = None
    agent_name: str = "primary"


@dataclass
class StrategyDescriptor:
    """Self-describing стратегия выполнения.
    
    Содержит всю информацию о стратегии:
    - name: уникальный идентификатор
    - display_name: отображаемое имя для UI
    - description: описание для UI
    - factory: создает экземпляр стратегии
    - validator: проверяет доступность через AgentRegistry
    
    Attributes:
        name: Уникальный идентификатор ("single", "hierarchical", etc.)
        display_name: Отображаемое имя для UI ("Single", "Hierarchical", etc.)
        description: Описание стратегии для UI
        factory: Callable[[StrategyDependencies], LLMAgent] — создает экземпляр
        validator: Callable[[AgentRegistry], bool] — проверяет доступность
    
    Example:
        >>> descriptor = StrategyDescriptor(
        ...     name="single",
        ...     display_name="Single",
        ...     description="Single agent execution",
        ...     factory=lambda deps: SingleStrategy(...),
        ...     validator=lambda registry: True,
        ... )
    """
    
    name: str
    display_name: str
    description: str
    factory: Callable[[StrategyDependencies], LLMAgent]
    validator: Callable[[AgentRegistry], bool]
    
    def is_available(self, registry: AgentRegistry) -> bool:
        """Проверить доступность стратегии.
        
        Args:
            registry: AgentRegistry для проверки агентов
        
        Returns:
            True если стратегия доступна для выполнения
        """
        return self.validator(registry)
    
    def create_instance(self, deps: StrategyDependencies) -> LLMAgent:
        """Создать экземпляр стратегии.
        
        Args:
            deps: Зависимости для создания стратегии
        
        Returns:
            Экземпляр стратегии (LLMAgent)
        """
        return self.factory(deps)

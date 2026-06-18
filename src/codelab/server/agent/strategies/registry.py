"""StrategyRegistry — единый источник истины о доступных стратегиях.

Registry Pattern, аналогично AgentRegistry, LLMProviderRegistry, ToolRegistry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from codelab.server.agent.registry import AgentRegistry
    from codelab.server.agent.strategies.base import LLMCallStrategy
    
    from .descriptor import StrategyDependencies, StrategyDescriptor

logger = structlog.get_logger()


class StrategyRegistry:
    """Реестр стратегий выполнения.
    
    Единый источник истины о доступных стратегиях.
    Паттерн: Registry (как AgentRegistry, LLMProviderRegistry).
    
    Responsibilities:
    - Хранение StrategyDescriptor для каждой стратегии
    - Фильтрация доступных стратегий через validator
    - Создание экземпляров стратегий через factory
    
    Attributes:
        _descriptors: Мапа name → StrategyDescriptor
    
    Example:
        >>> registry = StrategyRegistry()
        >>> registry.register(SINGLE_STRATEGY_DESCRIPTOR)
        >>> available = registry.get_available(agent_registry)
        >>> strategy = registry.create_instance("single", deps)
    """
    
    def __init__(self) -> None:
        """Инициализация пустого реестра."""
        self._descriptors: dict[str, StrategyDescriptor] = {}
    
    def register(self, descriptor: StrategyDescriptor) -> None:
        """Зарегистрировать стратегию.
        
        Args:
            descriptor: StrategyDescriptor для регистрации
        
        Raises:
            ValueError: Если стратегия с таким name уже зарегистрирована
        """
        if descriptor.name in self._descriptors:
            raise ValueError(
                f"Strategy '{descriptor.name}' already registered. "
                f"Use a different name or unregister the existing one first."
            )
        
        self._descriptors[descriptor.name] = descriptor
        logger.info(
            "Strategy registered",
            name=descriptor.name,
            display_name=descriptor.display_name,
        )
    
    def unregister(self, name: str) -> bool:
        """Удалить стратегию из реестра.
        
        Args:
            name: Имя стратегии для удаления
        
        Returns:
            True если стратегия была удалена, False если не найдена
        """
        if name in self._descriptors:
            del self._descriptors[name]
            logger.info("Strategy unregistered", name=name)
            return True
        return False
    
    def get(self, name: str) -> StrategyDescriptor | None:
        """Получить descriptor по имени.
        
        Args:
            name: Имя стратегии
        
        Returns:
            StrategyDescriptor или None если не найдена
        """
        return self._descriptors.get(name)
    
    def get_available(
        self,
        agent_registry: AgentRegistry,
    ) -> list[StrategyDescriptor]:
        """Получить список доступных стратегий.
        
        Стратегия доступна если validator возвращает True.
        
        Args:
            agent_registry: AgentRegistry для проверки агентов
        
        Returns:
            Список StrategyDescriptor доступных стратегий
        """
        available = []
        for descriptor in self._descriptors.values():
            if descriptor.is_available(agent_registry):
                available.append(descriptor)
        
        logger.debug(
            "Available strategies",
            total=len(self._descriptors),
            available=len(available),
            names=[d.name for d in available],
        )
        
        return available
    
    def create_instance(
        self,
        name: str,
        deps: StrategyDependencies,
    ) -> LLMCallStrategy | None:
        """Создать экземпляр стратегии.
        
        Args:
            name: Имя стратегии
            deps: Зависимости для создания стратегии
        
        Returns:
            Экземпляр стратегии (LLMCallStrategy) или None если стратегия не найдена
        """
        descriptor = self.get(name)
        if descriptor is None:
            logger.warning("Strategy not found for instantiation", name=name)
            return None
        
        try:
            instance = descriptor.create_instance(deps)
            logger.debug("Strategy instance created", name=name)
            return instance
        except Exception as e:
            logger.error(
                "Failed to create strategy instance",
                name=name,
                error=str(e),
            )
            return None
    
    def list_all(self) -> list[StrategyDescriptor]:
        """Получить все зарегистрированные стратегии.
        
        Returns:
            Список всех StrategyDescriptor
        """
        return list(self._descriptors.values())
    
    def is_registered(self, name: str) -> bool:
        """Проверить регистрацию стратегии.
        
        Args:
            name: Имя стратегии
        
        Returns:
            True если стратегия зарегистрирована
        """
        return name in self._descriptors
    
    def clear(self) -> None:
        """Очистить реестр."""
        self._descriptors.clear()
        logger.info("Strategy registry cleared")

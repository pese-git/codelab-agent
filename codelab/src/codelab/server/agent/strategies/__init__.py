"""Стратегии вызова LLM.

Модуль определяет интерфейс LLMCallStrategy и его реализации
для Strategy Pattern в AgentLoop.
"""

from .base import LLMCallStrategy
from .descriptor import StrategyDependencies, StrategyDescriptor
from .dispatcher import StrategyDispatcher
from .legacy_adapter import LegacyCallStrategy
from .registry import StrategyRegistry

__all__ = [
    "LLMCallStrategy",
    "LegacyCallStrategy",
    "StrategyDependencies",
    "StrategyDescriptor",
    "StrategyDispatcher",
    "StrategyRegistry",
]

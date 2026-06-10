"""Стратегии вызова LLM.

Модуль определяет интерфейс LLMCallStrategy и его реализации
для Strategy Pattern в AgentLoop.
"""

from .base import LLMCallStrategy
from .dispatcher import StrategyDispatcher
from .legacy_adapter import LegacyCallStrategy

__all__ = [
    "LLMCallStrategy",
    "LegacyCallStrategy",
    "StrategyDispatcher",
]

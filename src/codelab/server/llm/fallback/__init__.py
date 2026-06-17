"""Fallback модуль для LLM провайдеров.

Обеспечивает автоматическое переключение между провайдерами при ошибках.
MVP: Sequential fallback — перебирает провайдеры по порядку.
Extension points: CircuitBreaker, CostFallback, SmartFallback.
"""

from codelab.server.llm.fallback.base import FallbackContext, FallbackStrategy
from codelab.server.llm.fallback.circuit_breaker import CircuitBreaker
from codelab.server.llm.fallback.config import FallbackConfig
from codelab.server.llm.fallback.factory import FallbackStrategyFactory
from codelab.server.llm.fallback.orchestrator import FallbackOrchestrator
from codelab.server.llm.fallback.sequential import SequentialFallback

__all__ = [
    "FallbackStrategy",
    "FallbackContext",
    "SequentialFallback",
    "CircuitBreaker",
    "FallbackConfig",
    "FallbackStrategyFactory",
    "FallbackOrchestrator",
]

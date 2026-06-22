"""Decorators для tool executors.

Предоставляет декораторы для добавления дополнительной функциональности
к tool executors через Decorator Pattern.

Доступные декораторы:
- TimeoutDecorator: Добавляет timeout для выполнения инструментов
- RetryDecorator: Добавляет retry логику с exponential backoff

Example:
    >>> from codelab.server.tools.executors.decorators import (
    ...     TimeoutDecorator,
    ...     RetryDecorator,
    ... )
    >>> 
    >>> # Создаём chain of decorators
    >>> executor = mcp_executor
    >>> executor = TimeoutDecorator(executor, timeout=30.0)
    >>> executor = RetryDecorator(executor, max_retries=3)
    >>> 
    >>> # Выполняем инструмент
    >>> result = await executor.execute(session, arguments)
"""

from .base import ToolExecutorDecorator, ToolExecutorProtocol
from .retry import RetryDecorator
from .timeout import TimeoutDecorator

__all__ = [
    "ToolExecutorDecorator",
    "ToolExecutorProtocol",
    "TimeoutDecorator",
    "RetryDecorator",
]

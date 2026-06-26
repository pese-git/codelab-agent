"""Decorators для tool executors.

Предоставляет декораторы для добавления дополнительной функциональности
к tool executors через Decorator Pattern.

Доступные декораторы:
- TimeoutDecorator: Добавляет timeout для выполнения инструментов
- RetryDecorator: Добавляет retry логику с exponential backoff
- MetricsDecorator: Собирает метрики выполнения (duration, success/failure)
- TracingDecorator: Создаёт trace spans для distributed tracing
- ProjectStructureDecorator: Извлекает структуру проекта из terminal output

Example:
    >>> from codelab.server.tools.executors.decorators import (
    ...     TimeoutDecorator,
    ...     RetryDecorator,
    ...     MetricsDecorator,
    ...     TracingDecorator,
    ...     ProjectStructureDecorator,
    ... )
    >>> 
    >>> # Создаём chain of decorators
    >>> executor = mcp_executor
    >>> executor = TimeoutDecorator(executor, timeout=30.0)
    >>> executor = RetryDecorator(executor, max_retries=3)
    >>> executor = MetricsDecorator(executor)
    >>> executor = TracingDecorator(executor)
    >>> executor = ProjectStructureDecorator(executor)
    >>> 
    >>> # Выполняем инструмент
    >>> result = await executor.execute(session, arguments)
"""

from .base import ToolExecutorDecorator, ToolExecutorProtocol
from .metrics import (
    MetricsCollector,
    MetricsDecorator,
    ToolMetrics,
    get_global_metrics_collector,
)
from .project_structure import ProjectStructureDecorator
from .retry import RetryDecorator
from .timeout import TimeoutDecorator
from .tracing import (
    SpanStatus,
    TraceRecorder,
    TraceSpan,
    TracingDecorator,
    generate_span_id,
    generate_trace_id,
    get_global_trace_recorder,
)

__all__ = [
    "ToolExecutorDecorator",
    "ToolExecutorProtocol",
    "TimeoutDecorator",
    "RetryDecorator",
    "MetricsDecorator",
    "MetricsCollector",
    "ToolMetrics",
    "get_global_metrics_collector",
    "TracingDecorator",
    "TraceRecorder",
    "TraceSpan",
    "SpanStatus",
    "generate_trace_id",
    "generate_span_id",
    "get_global_trace_recorder",
    "ProjectStructureDecorator",
]

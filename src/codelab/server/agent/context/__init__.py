"""Context Manager — единая точка входа для управления контекстом агента.

4-слойная архитектура (A-D):
- Слой A: Сбор контекста (TaskAnalyzer, ContextGatherer, DependencyGraph, TokenBudgetManager)
- Слой B: Жизненный цикл (ContextEpoch, ContextSnapshot, ContextReconciler)
- Слой C: Хранение (FileContentCache, CodeSkeletonizer, TokenCounter, ContextCompactor)
- Слой D: Мультиагент (ChildSessionManager, process_subagent_response)
"""

from codelab.server.agent.context.file_cache import (
    InMemoryFileCache,
    InvalidationSignalBus,
    SessionFileCacheRegistry,
)
from codelab.server.agent.context.file_cache_decorator import FileCacheDecorator
from codelab.server.agent.context.interfaces import (
    CodeSkeletonizer,
    ContextCompactor,
    ContextManager,
    ContextSource,
    FileContentCache,
    TokenCounter,
)
from codelab.server.agent.context.skeletonizer import (
    NoOpSkeletonizer,
    PythonASTSkeletonizer,
)
from codelab.server.agent.context.token_counter import (
    ApproximateTokenCounter,
    TiktokenCounter,
    create_token_counter,
)

__all__ = [
    "ApproximateTokenCounter",
    "CodeSkeletonizer",
    "ContextCompactor",
    "ContextManager",
    "ContextSource",
    "FileCacheDecorator",
    "FileContentCache",
    "InMemoryFileCache",
    "InvalidationSignalBus",
    "NoOpSkeletonizer",
    "PythonASTSkeletonizer",
    "SessionFileCacheRegistry",
    "TiktokenCounter",
    "TokenCounter",
    "create_token_counter",
]

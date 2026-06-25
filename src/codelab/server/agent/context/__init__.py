"""Context Manager — единая точка входа для управления контекстом агента.

4-слойная архитектура (A-D):
- Слой A: Сбор контекста (TaskAnalyzer, ContextGatherer, DependencyGraph, TokenBudgetManager)
- Слой B: Жизненный цикл (ContextEpoch, ContextSnapshot, ContextReconciler)
- Слой C: Хранение (FileContentCache, CodeSkeletonizer, TokenCounter, ContextCompactor)
- Слой D: Мультиагент (ChildSessionManager, process_subagent_response)
"""

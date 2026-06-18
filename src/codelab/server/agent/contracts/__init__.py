"""Контракты сообщений для мультиагентной шины событий.

Этот пакет определяет все типы данных, которые проходят через AgentEventBus:
- DomainEvent — базовый класс всех событий
- Контракты запросов/ответов: AgentRequest, AgentResponse, AgentResult
- Контракты broadcast: ContextBroadcast, ChoreographyAnswer
- Утилиты: TokenUsage, ToolCall
- Lifecycle events: AgentRegistered, AgentUnregistered, AgentListChanged
- Исключения: AgentBusError и производные

Важно: AgentResponse из contracts — это DomainEvent для EventBus,
НЕ AgentResponse из server/agent/base.py (результт вызова LLMAgent).
"""

from codelab.server.agent.contracts.base import (
    AgentBusError,
    AgentDispatchError,
    AgentListChanged,
    AgentNotFoundError,
    AgentRegistered,
    AgentRequest,
    AgentResponse,
    AgentResult,
    AgentUnregistered,
    BroadcastPartialFailure,
    ChoreographyAnswer,
    ContextBroadcast,
    DomainEvent,
    TokenUsage,
    ToolCall,
)

__all__ = [
    "DomainEvent",
    "TokenUsage",
    "ToolCall",
    "AgentRequest",
    "AgentResponse",
    "AgentResult",
    "ContextBroadcast",
    "ChoreographyAnswer",
    "AgentRegistered",
    "AgentUnregistered",
    "AgentListChanged",
    "AgentBusError",
    "AgentNotFoundError",
    "AgentDispatchError",
    "BroadcastPartialFailure",
]

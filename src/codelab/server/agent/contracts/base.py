"""Совместимость: контракты шины переехали в `contracts.events`.

Тонкий re-export для внешних потребителей, импортирующих `contracts.base`.
Новый код должен импортировать из `codelab.server.agent.contracts.events`
(или из `codelab.server.agent.contracts`).
"""

from codelab.server.agent.contracts.events import (
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
    "AgentBusError",
    "AgentDispatchError",
    "AgentListChanged",
    "AgentNotFoundError",
    "AgentRegistered",
    "AgentRequest",
    "AgentResponse",
    "AgentResult",
    "AgentUnregistered",
    "BroadcastPartialFailure",
    "ChoreographyAnswer",
    "ContextBroadcast",
    "DomainEvent",
    "TokenUsage",
    "ToolCall",
]

"""Контракты сообщений для мультиагентной шины событий.

Этот пакет определяет все типы данных, которые проходят через AgentEventBus,
плюс порты гексагона (ADR-005):

Event-bus контракты:
- DomainEvent — базовый класс всех событий
- Контракты запросов/ответов: AgentRequest, AgentResponse, AgentResult
- Контракты broadcast: ContextBroadcast, ChoreographyAnswer
- Утилиты: TokenUsage, ToolCall
- Lifecycle events: AgentRegistered, AgentUnregistered, AgentListChanged
- Исключения: AgentBusError и производные

Hexagon ports (ADR-005):
- SessionView — read-only сессия (Фаза 1)
- ContentCodec — декодирование входного контента (Фаза 2)
- ToolGateway — реестр инструментов (Фаза 3)
- UpdateSink — эмиссия прогресса (Фаза 3)
- AgentRunner — driving-порт входа в turn (Фаза 4)
- ChildSessionFactory — фабрика child-сессий (Фаза 4)
- LLMPort — порт вызова LLM (ADR-001)
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
from codelab.server.agent.contracts.ports import (
    AgentRunner,
    ChildSessionFactory,
    ContentCodec,
    LLMPort,
    SessionView,
    ToolGateway,
    UpdateSink,
)

__all__ = [
    # Event-bus контракты
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
    # Hexagon ports (ADR-005)
    "SessionView",
    "ContentCodec",
    "ToolGateway",
    "UpdateSink",
    "AgentRunner",
    "ChildSessionFactory",
    "LLMPort",
]

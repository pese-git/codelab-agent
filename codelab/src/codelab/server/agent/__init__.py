"""Компоненты LLM агента для ACP сервера.

Включает интеграцию с LLM провайдерами, управление инструментами,
и оркестрацию выполнения агентом.
"""

from codelab.server.agent.base import (
    AgentContext,
    AgentResponse,
    LLMAgent,
)
from codelab.server.agent.config import (
    AgentConfigLoader,
    AgentConfigResolver,
    AgentMarkdownConfig,
    AgentMode,
    AgentPermission,
    AgentsGlobalConfig,
    AgentTOMLConfig,
    ResolvedAgent,
    SessionMetrics,
)
from codelab.server.agent.contracts.base import (
    AgentBusError,
    AgentDispatchError,
    AgentListChanged,
    AgentNotFoundError,
    AgentRegistered,
    AgentRequest,
    AgentResult,
    AgentUnregistered,
    BroadcastPartialFailure,
    ChoreographyAnswer,
    ContextBroadcast,
    DomainEvent,
    TokenUsage,
    ToolCall,
)
from codelab.server.agent.contracts.base import (
    AgentResponse as ContractAgentResponse,
)
from codelab.server.agent.event_bus.abstract import (
    AbstractEventBus,
    Handler,
    Subscription,
)
from codelab.server.agent.event_bus.bus import AgentEventBus, RetryConfig
from codelab.server.agent.event_bus.routing import (
    AgentRoutingInterface,
    RequestHandler,
)
from codelab.server.agent.registry import AgentRegistry

__all__ = [
    # Original agent classes
    "LLMAgent",
    "AgentContext",
    "AgentResponse",
    # Config models
    "AgentMode",
    "AgentPermission",
    "AgentTOMLConfig",
    "AgentsGlobalConfig",
    "AgentMarkdownConfig",
    "ResolvedAgent",
    "SessionMetrics",
    "AgentConfigLoader",
    "AgentConfigResolver",
    # Event Bus contracts
    "DomainEvent",
    "TokenUsage",
    "ToolCall",
    "AgentRequest",
    "ContractAgentResponse",
    "AgentResult",
    "ContextBroadcast",
    "ChoreographyAnswer",
    "AgentRegistered",
    "AgentUnregistered",
    "AgentListChanged",
    # Event Bus exceptions
    "AgentBusError",
    "AgentNotFoundError",
    "AgentDispatchError",
    "BroadcastPartialFailure",
    # Event Bus implementation
    "AbstractEventBus",
    "Subscription",
    "Handler",
    "AgentRoutingInterface",
    "RequestHandler",
    "AgentEventBus",
    "RetryConfig",
    # Registry
    "AgentRegistry",
]

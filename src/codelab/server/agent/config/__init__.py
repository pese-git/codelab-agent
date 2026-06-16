"""Конфигурация мультиагентной системы.

Включает:
- Pydantic модели (AgentRole, AgentTOMLConfig, AgentsGlobalConfig, etc.)
- AgentConfigLoader — загрузка из 4 источников
- AgentConfigResolver — разрешение defaults
"""

from codelab.server.agent.config.loader import AgentConfigLoader
from codelab.server.agent.config.models import (
    AgentMarkdownConfig,
    AgentPermission,
    AgentRole,
    AgentsGlobalConfig,
    AgentTOMLConfig,
    ResolvedAgent,
    SessionMetrics,
)
from codelab.server.agent.config.resolver import AgentConfigResolver

__all__ = [
    "AgentRole",
    "AgentPermission",
    "AgentTOMLConfig",
    "AgentsGlobalConfig",
    "AgentMarkdownConfig",
    "ResolvedAgent",
    "SessionMetrics",
    "AgentConfigLoader",
    "AgentConfigResolver",
]

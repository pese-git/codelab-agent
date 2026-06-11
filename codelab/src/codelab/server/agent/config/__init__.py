"""Конфигурация мультиагентной системы.

Включает:
- Pydantic модели (AgentMode, AgentTOMLConfig, AgentsGlobalConfig, etc.)
- AgentConfigLoader — загрузка из 4 источников
- AgentConfigResolver — разрешение defaults
"""

from codelab.server.agent.config.loader import AgentConfigLoader
from codelab.server.agent.config.models import (
    AgentMarkdownConfig,
    AgentMode,
    AgentPermission,
    AgentsGlobalConfig,
    AgentTOMLConfig,
    ResolvedAgent,
    SessionMetrics,
)
from codelab.server.agent.config.resolver import AgentConfigResolver

__all__ = [
    "AgentMode",
    "AgentPermission",
    "AgentTOMLConfig",
    "AgentsGlobalConfig",
    "AgentMarkdownConfig",
    "ResolvedAgent",
    "SessionMetrics",
    "AgentConfigLoader",
    "AgentConfigResolver",
]

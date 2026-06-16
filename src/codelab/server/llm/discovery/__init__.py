"""Discovery модуль для обнаружения доступных моделей."""

from codelab.server.llm.discovery.base import ModelDiscovery
from codelab.server.llm.discovery.config import DiscoveryConfig
from codelab.server.llm.discovery.static import StaticDiscovery

__all__ = [
    "ModelDiscovery",
    "StaticDiscovery",
    "DiscoveryConfig",
]

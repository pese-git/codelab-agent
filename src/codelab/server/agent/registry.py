"""Реестр агентов с hot reload и регистрацией в EventBus.

AgentRegistry:
- Загружает конфигурации через AgentConfigLoader
- Разрешает defaults через AgentConfigResolver
- Создаёт LLMAdapter через AgentFactory
- Регистрирует агентов в AgentEventBus
- Публикует lifecycle events при изменениях
- Поддерживает hot reload через watchdog (опционально)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from codelab.server.agent.config import (
    AgentConfigLoader,
    AgentConfigResolver,
    AgentsGlobalConfig,
    ResolvedAgent,
)
from codelab.server.agent.event_bus.bus import AgentEventBus

if TYPE_CHECKING:
    from codelab.server.agent.factory import AgentFactory

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Единый реестр агентов с hot reload.

    Attributes:
        _loader: Загрузчик конфигураций
        _resolver: Разрешатель конфигураций
        _event_bus: Шина событий для регистрации агентов
        _agent_factory: Фабрика создания LLMAdapter
        _agents: Текущие разрешённые агенты
        _initialized: Флаг инициализации
    """

    def __init__(
        self,
        event_bus: AgentEventBus,
        agent_factory: AgentFactory,
        global_config: AgentsGlobalConfig | None = None,
        global_config_dir: Path | None = None,
        project_config_dir: Path | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._agent_factory = agent_factory
        self._global_config = global_config or AgentsGlobalConfig()
        self._loader = AgentConfigLoader(
            global_config_dir=global_config_dir,
            project_config_dir=project_config_dir,
        )
        self._resolver = AgentConfigResolver(
            loader=self._loader,
            global_config=self._global_config,
        )
        self._agents: dict[str, ResolvedAgent] = {}
        self._initialized = False

    async def initialize(
        self,
        global_toml: dict[str, Any] | None = None,
        project_toml: dict[str, Any] | None = None,
    ) -> None:
        """Инициализировать реестр — загрузить и зарегистрировать агентов.

        Args:
            global_toml: Глобальная TOML конфигурация
            project_toml: Проектная TOML конфигурация
        """
        self._agents = self._resolver.resolve_all(global_toml, project_toml)

        # Регистрируем каждого агента в EventBus
        for name, agent in self._agents.items():
            await self._register_agent(name, agent)

        self._initialized = True
        logger.info("AgentRegistry initialized with %d agents", len(self._agents))

    async def reload(
        self,
        global_toml: dict[str, Any] | None = None,
        project_toml: dict[str, Any] | None = None,
    ) -> dict[str, list[str]]:
        """Hot reload — перезагрузить конфигурацию и обновить регистрацию.

        Args:
            global_toml: Глобальная TOML конфигурация
            project_toml: Проектная TOML конфигурация

        Returns:
            dict с ключами 'added' и 'removed' — списки имён агентов.
        """
        old_names = set(self._agents.keys())
        new_agents = self._resolver.resolve_all(global_toml, project_toml)
        new_names = set(new_agents.keys())

        added = new_names - old_names
        removed = old_names - new_names

        # unregister удалённых
        for name in removed:
            await self._event_bus.unregister_agent(name)

        # register новых
        for name in added:
            await self._register_agent(name, new_agents[name])

        self._agents = new_agents

        # Публикуем AgentListChanged
        from codelab.server.agent.contracts.base import AgentListChanged

        if added or removed:
            await self._event_bus.publish(
                AgentListChanged(added=list(added), removed=list(removed))
            )

        logger.info(
            "AgentRegistry reloaded: +%d -%d", len(added), len(removed)
        )
        return {"added": list(added), "removed": list(removed)}

    async def _register_agent(self, name: str, agent: ResolvedAgent) -> None:
        """Зарегистрировать агента в EventBus через AgentFactory.

        Создаёт LLMAdapter через фабрику и регистрирует его handler
        в EventBus. Каждый агент получает свой адаптер с правильной моделью.

        Args:
            name: Имя агента
            agent: Разрешённая конфигурация
        """
        # Создаём LLMAdapter через фабрику (с правильной моделью)
        adapter = await self._agent_factory.create_adapter(agent)

        # Регистрируем handler адаптера в EventBus
        await adapter.register_with_bus(self._event_bus, name)

        logger.debug("agent registered in EventBus: %s (model=%s)", name, agent.model)

    def get(self, agent_name: str) -> ResolvedAgent | None:
        """Получить конфигурацию агента.

        Args:
            agent_name: Имя агента

        Returns:
            ResolvedAgent или None
        """
        return self._agents.get(agent_name)

    def get_all(self) -> dict[str, ResolvedAgent]:
        """Получить все конфигурации агентов."""
        return dict(self._agents)

    def get_primary_agents(self) -> dict[str, ResolvedAgent]:
        """Получить агентов с role=primary."""
        from codelab.server.agent.config.models import AgentRole

        return {
            name: agent
            for name, agent in self._agents.items()
            if agent.role == AgentRole.PRIMARY
        }

    def get_subagents(self) -> dict[str, ResolvedAgent]:
        """Получить агентов с role=subagent."""
        from codelab.server.agent.config.models import AgentRole

        return {
            name: agent
            for name, agent in self._agents.items()
            if agent.role == AgentRole.SUBAGENT
        }

    def get_orchestrator(self) -> ResolvedAgent | None:
        """Получить агента с role=orchestrator."""
        from codelab.server.agent.config.models import AgentRole

        for _name, agent in self._agents.items():
            if agent.role == AgentRole.ORCHESTRATOR:
                return agent
        return None

    @property
    def is_initialized(self) -> bool:
        """Проверить инициализацию."""
        return self._initialized

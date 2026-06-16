"""Разрешитель конфигурации агентов.

Применяет defaults из глобальных настроек к конфигурациям агентов.
Приоритет разрешения:
- model: agent → global.default_model
- temperature: agent → модель по умолчанию → 0.0
- steps: agent → global.max_steps → None
- prompt: agent.prompt → тело Markdown
"""

from __future__ import annotations

import logging
from typing import Any

from codelab.server.agent.config.loader import AgentConfigLoader
from codelab.server.agent.config.models import (
    AgentMarkdownConfig,
    AgentPermission,
    AgentsGlobalConfig,
    ResolvedAgent,
)

logger = logging.getLogger(__name__)


class AgentConfigResolver:
    """Разрешает конфигурации агентов с defaults из глобальных настроек."""

    def __init__(
        self,
        loader: AgentConfigLoader,
        global_config: AgentsGlobalConfig | None = None,
    ) -> None:
        self.loader = loader
        self.global_config = global_config or AgentsGlobalConfig()
        self._raw_configs: dict[str, AgentMarkdownConfig] = {}
        self._resolved: dict[str, ResolvedAgent] = {}

    def resolve_all(
        self,
        global_toml: dict[str, Any] | None = None,
        project_toml: dict[str, Any] | None = None,
    ) -> dict[str, ResolvedAgent]:
        """Загрузить и разрешить все конфигурации.

        Args:
            global_toml: Глобальная TOML конфигурация
            project_toml: Проектная TOML конфигурация

        Returns:
            dict[agent_name] → ResolvedAgent (только enabled агенты)
        """
        self._raw_configs = self.loader.load_all(global_toml, project_toml)
        self._resolved = {}

        for name, md_config in self._raw_configs.items():
            if not md_config.enabled:
                logger.debug("Skipping disabled agent: %s", name)
                continue

            resolved = self._resolve(name, md_config)
            self._resolved[name] = resolved

        logger.info("Resolved %d agents", len(self._resolved))
        return self._resolved

    def _resolve(self, name: str, md_config: AgentMarkdownConfig) -> ResolvedAgent:
        """Разрешить конфигурацию одного агента с defaults."""
        # Разрешение model
        model = md_config.model or self.global_config.default_model

        # Разрешение temperature
        temperature = md_config.temperature if md_config.temperature is not None else 0.0

        # Разрешение max_steps
        max_steps = md_config.max_steps or self.global_config.max_steps

        # Разрешение prompt
        prompt = md_config.prompt

        # Извлекаем permissions
        permissions_dict = md_config.permissions or {}
        permissions = AgentPermission(
            edit=permissions_dict.get("edit", False),
            bash=permissions_dict.get("bash", False),
            webfetch=permissions_dict.get("webfetch", False),
            task=permissions_dict.get("task", False),
        )

        # Извлекаем vendor-specific params из extra
        additional_params = md_config.model_extra or {}

        return ResolvedAgent(
            name=name,
            enabled=md_config.enabled,
            role=md_config.role,
            priority=md_config.priority,
            model=model,
            temperature=temperature,
            max_steps=max_steps,
            tools=list(md_config.tools),
            permissions=permissions,
            prompt=prompt,
            additional_params=additional_params,
        )

    def get_resolved(self) -> dict[str, ResolvedAgent]:
        """Вернуть разрешённые конфигурации."""
        return dict(self._resolved)

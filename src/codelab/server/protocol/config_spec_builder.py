"""ConfigSpecBuilder — построение config specs для ACP протокола.

Инкапсулирует логику построения конфигурационных спецификаций
из различных источников: AgentRegistry, StrategyRegistry, LLMProviderRegistry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from ..agent.registry import AgentRegistry
    from ..agent.strategies.registry import StrategyRegistry
    from .handlers.config_option_builder import ConfigOptionBuilder

logger = structlog.get_logger()


# Default config specs (используются если ConfigOptionBuilder не доступен)
_DEFAULT_CONFIG_SPECS: dict[str, dict[str, Any]] = {
    "mode": {
        "name": "Session Mode",
        "category": "mode",
        "default": "standard",
        "options": [
            {
                "value": "plan",
                "name": "Plan",
                "description": "Read-only planning mode",
            },
            {
                "value": "standard",
                "name": "Standard",
                "description": "Confirm changes before execution",
            },
            {
                "value": "bypass",
                "name": "Bypass",
                "description": "Full autonomy, no confirmation",
            },
        ],
    },
    "model": {
        "name": "Model",
        "category": "model",
        "default": "openai/gpt-4o",
        "options": [
            {
                "value": "openai/gpt-4o",
                "name": "GPT-4o",
                "description": "Balanced speed and quality",
            }
        ],
    },
}

# Metadata для стратегий (display_name, description)
_STRATEGY_METADATA = {
    "single": {
        "name": "Single",
        "description": "Single agent execution",
    },
    "multi_orchestrated": {
        "name": "Multi-Orchestrated",
        "description": "Orchestrator + subagents collaboration",
    },
    "multi_choreographed": {
        "name": "Multi-Choreographed",
        "description": "Multiple subagents peer collaboration",
    },
    "hierarchical": {
        "name": "Hierarchical",
        "description": "Primary delegates to subagents",
    },
}


class ConfigSpecBuilder:
    """Строит config specs из registry-источников.

    Отвечает за построение конфигурационных спецификаций для:
    - mode: ACP standard (permission behavior)
    - model: из ConfigOptionBuilder
    - _agent: из AgentRegistry
    - _active_strategy: из StrategyRegistry

    Attributes:
        config_option_builder: Билдер config options из LLM Registry.
        agent_registry: Реестр агентов.
        strategy_registry: Реестр стратегий.
    """

    def __init__(
        self,
        config_option_builder: ConfigOptionBuilder | None = None,
        agent_registry: AgentRegistry | None = None,
        strategy_registry: StrategyRegistry | None = None,
    ) -> None:
        """Инициализирует ConfigSpecBuilder.

        Args:
            config_option_builder: Билдер config options (опционально).
            agent_registry: Реестр агентов (опционально).
            strategy_registry: Реестр стратегий (опционально).
        """
        self._config_option_builder = config_option_builder
        self._agent_registry = agent_registry
        self._strategy_registry = strategy_registry

    def build(self) -> dict[str, dict[str, Any]]:
        """Собирает все config specs.

        Returns:
            Dict config_id -> spec.
        """
        if self._config_option_builder:
            additional_specs = {
                "mode": _DEFAULT_CONFIG_SPECS["mode"],
                "_agent": self._build_agent_spec(),
                "_active_strategy": self._build_strategy_spec(),
            }
            default_model = self._get_default_model()
            return self._config_option_builder.build_config_specs(
                default_model=default_model,
                additional_specs=additional_specs,
            )

        # Fallback без config_option_builder
        specs = dict(_DEFAULT_CONFIG_SPECS)
        specs["_agent"] = self._build_agent_spec()
        specs["_active_strategy"] = self._build_strategy_spec()
        return specs

    def _get_default_model(self) -> str:
        """Получить модель по умолчанию из конфигурации или Registry.

        Returns:
            Модель в формате "provider/model" (например, "openrouter/gpt-4o").
        """
        # Fallback: взять первую модель из Registry
        if self._config_option_builder is not None:
            models = self._config_option_builder.get_model_list()
            if models:
                return models[0].full_id

        # Последний fallback
        return "openai/gpt-4o"

    def _build_agent_spec(self) -> dict[str, Any]:
        """Построить config spec для _agent из AgentRegistry.

        Формирует список primary agents из Registry как options
        для IDE dropdown. Агенты сортируются по priority.

        Returns:
            Config spec для _agent option.
        """
        # Fallback если Registry не инициализирован
        if not self._agent_registry:
            return self._default_agent_spec()

        # Проверяем инициализацию Registry
        is_initialized = getattr(self._agent_registry, "is_initialized", False)
        if not is_initialized:
            return self._default_agent_spec()

        # Получаем primary agents из Registry
        get_primary = getattr(self._agent_registry, "get_primary_agents", None)
        if get_primary is None:
            return self._default_agent_spec()

        primary_agents = get_primary()
        if not primary_agents:
            return self._default_agent_spec()

        # Сортируем по priority (меньше = выше приоритет)
        sorted_agents = sorted(primary_agents.values(), key=lambda a: a.priority)

        options = []
        for agent in sorted_agents:
            options.append({
                "value": agent.name,
                "name": agent.name.capitalize(),
                "description": f"{agent.model} (priority: {agent.priority})",
            })

        default_agent = sorted_agents[0].name

        return {
            "id": "_agent",
            "name": "Agent",
            "category": "_agent",
            "type": "select",
            "default": default_agent,
            "options": options,
        }

    def _default_agent_spec(self) -> dict[str, Any]:
        """Возвращает дефолтный spec для _agent."""
        return {
            "id": "_agent",
            "name": "Agent",
            "category": "_agent",
            "type": "select",
            "default": "primary",
            "options": [
                {
                    "value": "primary",
                    "name": "Primary",
                    "description": "Default agent",
                }
            ],
        }

    def _build_strategy_spec(self) -> dict[str, Any]:
        """Построить config spec для _active_strategy из StrategyRegistry.

        Формирует список доступных стратегий из StrategyRegistry.get_available().
        Включает ТОЛЬКО стратегии, доступные для выполнения (validator возвращает True).

        Returns:
            Config spec для _active_strategy option.
        """
        # Fallback если StrategyRegistry не доступен
        if not self._strategy_registry or not self._agent_registry:
            return self._default_strategy_spec()

        # Получить доступные стратегии из Registry
        try:
            available = self._strategy_registry.get_available(self._agent_registry)
        except Exception:
            # Fallback при ошибке
            available = []

        # Если нет доступных стратегий, вернуть только "single"
        if not available:
            return self._default_strategy_spec()

        # Формировать options из descriptors
        options = []
        for descriptor in available:
            meta = _STRATEGY_METADATA.get(descriptor.name, {})
            options.append({
                "value": descriptor.name,
                "name": meta.get("name", descriptor.display_name),
                "description": meta.get("description", descriptor.description),
            })

        # Текущая стратегия по умолчанию — первая доступная
        default_strategy = available[0].name if available else "single"

        return {
            "id": "_active_strategy",
            "name": "Strategy",
            "category": "strategy",
            "type": "select",
            "default": default_strategy,
            "options": options,
        }

    def _default_strategy_spec(self) -> dict[str, Any]:
        """Возвращает дефолтный spec для _active_strategy."""
        return {
            "id": "_active_strategy",
            "name": "Strategy",
            "category": "strategy",
            "type": "select",
            "default": "single",
            "options": [
                {
                    "value": "single",
                    "name": "Single",
                    "description": "Single agent execution",
                }
            ],
        }

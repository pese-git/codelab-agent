"""AgentFactory — фабрика создания LLMAdapter из конфигурации агента.

Создаёт LLMAdapter с правильным LLMProvider для каждого агента
на основе ResolvedAgent.model. Использует LLMProviderRegistry и
ModelResolver для выбора провайдера.

Архитектурное решение:
- Каждый агент может использовать свою модель (coder=gpt-4o, tester=claude-sonnet)
- AgentFactory резолвит модель через ModelResolver и создаёт LLMAdapter
- LLMAdapter переиспользуется для всех вызовов агента (singleton per agent)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from codelab.server.agent.config.models import ResolvedAgent
from codelab.server.agent.llm_adapter import LLMAdapter

if TYPE_CHECKING:
    from codelab.server.llm.registry import LLMProviderRegistry
    from codelab.server.observability.tracer import Tracer
    from codelab.server.tools.base import ToolRegistry

logger = structlog.get_logger()


class AgentFactory:
    """Фабрика создания LLMAdapter из конфигурации агента.

    Создаёт и кэширует LLMAdapter для каждого агента.
    При первом вызове резолвит модель через ModelResolver,
    создаёт LLMProvider и оборачивает в LLMAdapter.

    Attributes:
        _llm_registry: Реестр LLM провайдеров
        _tool_registry: Реестр инструментов
        _tracer: Tracer для observability
        _adapters: Кэш созданных адаптеров (agent_name → LLMAdapter)
    """

    def __init__(
        self,
        llm_registry: LLMProviderRegistry,
        tool_registry: ToolRegistry,
        tracer: Tracer | None = None,
    ) -> None:
        self._llm_registry = llm_registry
        self._tool_registry = tool_registry
        self._tracer = tracer
        self._adapters: dict[str, LLMAdapter] = {}

    async def create_adapter(
        self,
        agent: ResolvedAgent,
        default_model: str = "openai/gpt-4o",
    ) -> LLMAdapter:
        """Создать или получить кэшированный LLMAdapter для агента.

        Args:
            agent: Конфигурация агента (ResolvedAgent)
            default_model: Модель по умолчанию если агент не указал свою

        Returns:
            LLMAdapter, готовый к регистрации в EventBus

        Raises:
            ValueError: Если модель агента не может быть резолвлена
        """
        if agent.name in self._adapters:
            return self._adapters[agent.name]

        # Резолвим модель агента
        model_ref = agent.model if agent.model else default_model
        provider = await self._resolve_provider(model_ref)

        logger.info(
            "creating LLMAdapter for agent",
            agent_name=agent.name,
            model=model_ref,
            provider=provider.name,
        )

        adapter = LLMAdapter(
            llm_provider=provider,
            tool_registry=self._tool_registry,
            tracer=self._tracer,
            name=agent.name,
            model=agent.model,
        )

        self._adapters[agent.name] = adapter
        return adapter

    async def _resolve_provider(self, model_ref: str):
        """Резолвить провайдер из model_ref.

        Args:
            model_ref: Ссылка на модель в формате "provider/model"

        Returns:
            LLMProvider для данной модели
        """
        from codelab.server.llm.resolver import ModelRef

        ref = ModelRef.parse(model_ref)

        try:
            provider = await self._llm_registry.get_provider(ref.provider_id)
            return provider
        except Exception:
            logger.warning(
                "failed to resolve provider %s, using default",
                ref.provider_id,
            )
            # Fallback: берём первый доступный провайдер
            providers = self._llm_registry.get_registered_providers()
            if providers:
                return await self._llm_registry.get_provider(providers[0])
            raise ValueError(
                f"No LLM providers registered. Cannot resolve '{model_ref}'"
            ) from None

    def get_adapter(self, agent_name: str) -> LLMAdapter | None:
        """Получить кэшированный адаптер по имени агента.

        Args:
            agent_name: Имя агента

        Returns:
            LLMAdapter или None если не создан
        """
        return self._adapters.get(agent_name)

    def clear_cache(self) -> None:
        """Очистить кэш адаптеров (для hot reload)."""
        self._adapters.clear()

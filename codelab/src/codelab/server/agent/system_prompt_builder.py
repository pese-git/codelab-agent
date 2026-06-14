"""SystemPromptBuilder — формирование system prompt для LLM.

Формирует system prompt из трёх частей (в порядке приоритета для LLM):
1. Agent prompt (роль агента из ~/.codelab/agents/*.md)
2. Global prompt (общие инструкции из config.agent.system_prompt)
3. MCP info (информация о подключённых MCP серверах)

Архитектурное решение:
- SystemPromptBuilder — единый ответственный за формирование system prompt
- Резолвит agent prompt через AgentRegistry (session.config_values["_agent"])
- Не зависит от MCP manager напрямую — принимает Any для loose coupling
- Согласован с паттерном HistoryBuilder / ToolFilter / MessageSanitizer

Порядок объединения:
    {agent_prompt}    ← "Ты — агент-программист..."
    \n\n
    {global_prompt}   ← "Используй update_plan, инструменты..."
    \n\n
    {mcp_info}        ← "You have access to MCP servers..."

Пример использования:
    builder = SystemPromptBuilder("You are a helpful assistant.", agent_registry)
    system_prompt = builder.build(session, mcp_manager=mcp_manager)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codelab.server.agent.registry import AgentRegistry
    from codelab.server.protocol.state import SessionState

logger = logging.getLogger(__name__)


class SystemPromptBuilder:
    """Формирует system prompt из agent prompt, конфигурации и MCP информации.

    Attributes:
        _global_prompt: Глобальный системный промпт из конфигурации.
        _agent_registry: Реестр агентов для резолва agent prompt.
    """

    def __init__(
        self,
        global_prompt: str = "",
        agent_registry: AgentRegistry | None = None,
    ) -> None:
        """Инициализация билдера.

        Args:
            global_prompt: Глобальный системный промпт (из config.agent.system_prompt).
            agent_registry: Реестр агентов для получения agent-specific prompt.
        """
        self._global_prompt = global_prompt
        self._agent_registry = agent_registry

    def build(
        self,
        session: SessionState,
        mcp_manager: Any | None = None,
    ) -> str | None:
        """Собрать system prompt.

        Формирует system prompt из:
        1. Agent prompt (роль агента из ~/.codelab/agents/*.md)
        2. Глобального системного промпта (если задан)
        3. Информации о MCP серверах (если mcp_manager подключён и имеет серверы)

        Args:
            session: Состояние сессии (для получения _agent из config_values).
            mcp_manager: MCP manager с подключёнными серверами (опционально).

        Returns:
            Текст system prompt или None если ничего не задано.
        """
        parts: list[str] = []

        # 1. Agent prompt (роль агента)
        agent_prompt = self._resolve_agent_prompt(session)
        if agent_prompt:
            parts.append(agent_prompt)

        # 2. Глобальный системный промпт из конфигурации
        if self._global_prompt:
            parts.append(self._global_prompt)

        # 3. Информация о подключённых MCP серверах
        if mcp_manager is not None:
            mcp_info = self._format_mcp_info(mcp_manager)
            if mcp_info:
                parts.append(mcp_info)

        if not parts:
            return None

        result = "\n\n".join(parts)

        agent_name = session.config_values.get("_agent", "")
        logger.debug(
            "system_prompt built",
            agent_name=agent_name or "default",
            has_agent_prompt=bool(agent_prompt),
            has_global_prompt=bool(self._global_prompt),
            has_mcp_info=mcp_manager is not None,
            total_length=len(result),
        )

        return result

    def _resolve_agent_prompt(self, session: SessionState) -> str:
        """Резолвить agent prompt из AgentRegistry.

        Args:
            session: Состояние сессии (для получения _agent из config_values).

        Returns:
            Текст agent prompt или пустая строка.
        """
        if self._agent_registry is None:
            return ""

        agent_name = session.config_values.get("_agent", "")
        if not agent_name:
            return ""

        agent = self._agent_registry.get(agent_name)
        if agent is None:
            logger.debug("agent not found in registry", agent_name=agent_name)
            return ""

        return agent.prompt or ""

    def _format_mcp_info(self, mcp_manager: Any) -> str:
        """Сформировать текст о MCP серверах для LLM.

        Args:
            mcp_manager: MCPManager с подключёнными серверами.

        Returns:
            Форматированный текст или пустая строка.
        """
        server_count = getattr(mcp_manager, "server_count", 0)
        if server_count == 0:
            return ""

        server_ids = getattr(mcp_manager, "server_ids", [])
        if not server_ids:
            return ""

        lines = [
            "You have access to the following MCP (Model Context Protocol) servers:",
        ]

        for server_id in server_ids:
            tools = mcp_manager.get_tools_for_server(server_id)
            tool_names = [t.name.split(":")[-1] for t in tools]
            names_str = ", ".join(tool_names)
            lines.append(
                f"- **{server_id}** ({len(tools)} tools): {names_str}"
            )

        lines.append(
            "\nWhen the user asks about MCP capabilities, "
            "reference these servers and their tools."
        )

        return "\n".join(lines)

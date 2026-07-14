"""LlmCaller — изоляция вызова LLM через стратегию.

Отвечает за:
- построение system prompt (agent + config + MCP info);
- вызов стратегии (execute на первой итерации, иначе continue_execution);
- стриминг: эмит текстовых дельт через ``on_delta`` (без повторного эмита
  полного текста — см. AgentLoop);
- ленивую реинициализацию стратегии для continue_execution после permission.

Скрытое инстанс-состояние «был ли стрим» вынесено в возвращаемый
``LlmCallResult`` — call() чист относительно входа.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from codelab.server.agent.base import AgentResponse
    from codelab.server.agent.strategies.base import LLMCallStrategy
    from codelab.server.agent.system_prompt_builder import SystemPromptBuilder
    from codelab.server.mcp.manager import MCPManager
    from codelab.server.protocol.handlers.pipeline.stages.agent_loop.updates import (
        SessionUpdateSink,
    )
    from codelab.server.protocol.state import SessionState

logger = structlog.get_logger()


@dataclass
class LlmCallResult:
    """Результат одного вызова LLM.

    Attributes:
        response: Ответ стратегии.
        streamed: Были ли доставлены текстовые дельты через ``on_delta``.
            Если True, AgentLoop не эмитит полный текст повторно (иначе дубль).
    """

    response: AgentResponse
    streamed: bool


class LlmCaller:
    """Вызов LLM через LLMCallStrategy с поддержкой стриминга."""

    def __init__(
        self,
        strategy: LLMCallStrategy,
        system_prompt_builder: SystemPromptBuilder,
        streaming_enabled: bool = False,
    ) -> None:
        """Инициализация.

        Args:
            strategy: Стратегия вызова LLM (StrategyDispatcher).
            system_prompt_builder: Билдер system prompt (config + MCP info).
            streaming_enabled: Включён ли стриминг текстовых дельт.
        """
        self._strategy = strategy
        self._system_prompt_builder = system_prompt_builder
        self._streaming_enabled = streaming_enabled

    async def call(
        self,
        session: SessionState,
        prompt: str | None,
        mcp_manager: MCPManager | None,
        iteration: int,
        sink: SessionUpdateSink,
    ) -> LlmCallResult:
        """Вызвать LLM через стратегию.

        Args:
            session: Состояние сессии.
            prompt: Текст промпта (None для продолжения).
            mcp_manager: MCP manager.
            iteration: Номер итерации (execute на первой, иначе continue).
            sink: Канал доставки для стриминг-дельт.

        Returns:
            LlmCallResult с ответом и признаком стриминга.
        """
        # Формируем system prompt (agent + config + MCP info)
        system_prompt = self._system_prompt_builder.build(session, mcp_manager)

        # Стриминг: on_delta эмитит текстовые дельты как agent_message_chunk
        # вживую. Полный текст ответа НЕ эмитится повторно (см. AgentLoop).
        streamed = False
        on_delta = None
        if self._streaming_enabled:
            session_id = session.session_id

            async def on_delta(delta: str) -> None:
                nonlocal streamed
                streamed = True
                await sink.emit_streaming_delta(session_id, delta)

        if iteration == 1 and prompt:
            response = await self._strategy.execute(
                session,
                prompt,
                mcp_manager,
                system_prompt=system_prompt,
                on_delta=on_delta,
            )
        else:
            response = await self._strategy.continue_execution(
                session,
                mcp_manager,
                on_delta=on_delta,
            )

        return LlmCallResult(response=response, streamed=streamed)

    def ensure_strategy_selected(self, session: SessionState, session_id: str) -> None:
        """Гарантировать, что стратегия выбрана (для continue_execution).

        StrategyDispatcher имеет ``_current_strategy_name`` и ``select_strategy``,
        но LLMCallStrategy Protocol их не определяет — проверяем динамически.
        Используется в resume_after_permission после permission approval.
        """
        strategy_name_attr = getattr(self._strategy, "_current_strategy_name", None)
        if strategy_name_attr is None:
            select_fn = getattr(self._strategy, "select_strategy", None)
            if callable(select_fn):
                select_fn(session, context_meta=None)
                logger.debug(
                    "resume_after_permission: strategy re-initialized",
                    strategy=getattr(self._strategy, "_current_strategy_name", "unknown"),
                    session_id=session_id,
                )

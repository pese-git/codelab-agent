"""CoreAgentRunner — реализация driving-порта `AgentRunner` (ADR-005, Фаза 4).

Связка `ExecutionEngine` (сборка контекста через порты `SessionView`/`ToolGateway`/
`ContentCodec`) + `LLMPort` (вызов LLM). Не зависит от `protocol`/ACP: любой драйвер
(ACP turn-loop, fake-харнесс, потенциальный A2A) подаёт turn через один вход.

Границы: один `run_turn`/`continue_turn` = один вызов LLM. Цикл tool-calling,
эмиссия `session/update` и permission-flow — ответственность driving-адаптера,
не этого класса (см. design.md).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codelab.server.agent.contracts.events import AgentResult
    from codelab.server.agent.contracts.ports import LLMPort, SessionView
    from codelab.server.agent.core.execution_engine import ExecutionEngine


class CoreAgentRunner:
    """Реализация `AgentRunner` поверх `ExecutionEngine` + `LLMPort`."""

    def __init__(self, execution_engine: ExecutionEngine, llm: LLMPort) -> None:
        self._execution_engine = execution_engine
        self._llm = llm

    async def run_turn(
        self, session: SessionView, prompt: str, *, system_prompt: str | None = None
    ) -> AgentResult:
        """Начать turn: собрать контекст и выполнить один вызов LLM."""
        context = await self._execution_engine.build_context(
            session, prompt, system_prompt=system_prompt
        )
        return await self._llm.call(
            context.conversation_history,
            context.available_tools,
            context.config,
            session_id=context.session_id,
        )

    async def continue_turn(
        self, session: SessionView, *, system_prompt: str | None = None
    ) -> AgentResult:
        """Продолжить turn после tool_results: пересобрать историю и вызвать LLM."""
        context = await self._execution_engine.build_continuation_context(session)
        return await self._llm.call(
            context.history,
            context.available_tools,
            context.config,
            session_id=context.session_id,
        )

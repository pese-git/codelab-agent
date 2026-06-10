"""LLMLoopStage — тонкий адаптер pipeline → AgentLoop.

Responsibilities:
- Создание AgentLoop с нужной стратегией (лениво)
- Интеграция с pipeline (PromptContext → AgentLoopResult → PromptContext)

НЕ отвечает за:
- Цикл итераций (делает AgentLoop)
- Вызов LLM (делает LLMCallStrategy)
- Обработку tool_calls (делает AgentLoop)

Архитектурное решение:
- Strategy Pattern — выбор стратегии через LLMCallStrategy
- Single Responsibility — LLMLoopStage только адаптер
- Open/Closed — добавление стратегии не требует изменения LLMLoopStage
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.agent.strategies.legacy_adapter import LegacyCallStrategy
from codelab.server.protocol.content.extractor import ContentExtractor
from codelab.server.protocol.content.formatter import ContentFormatter
from codelab.server.protocol.content.validator import ContentValidator
from codelab.server.protocol.handlers.pipeline.stages.agent_loop import AgentLoop
from codelab.server.protocol.handlers.replay_manager import ReplayManager
from codelab.server.protocol.stop_reasons import StopReason

from ..base import PromptStage
from ..context import PromptContext

if TYPE_CHECKING:
    from codelab.server.agent.orchestrator import AgentOrchestrator
    from codelab.server.agent.strategies.base import LLMCallStrategy
    from codelab.server.agent.strategies.dispatcher import StrategyDispatcher
    from codelab.server.observability.tracer import Tracer
    from codelab.server.protocol.handlers.global_policy_manager import GlobalPolicyManager
    from codelab.server.protocol.handlers.permission_manager import PermissionManager
    from codelab.server.protocol.handlers.plan_builder import PlanBuilder
    from codelab.server.protocol.handlers.state_manager import StateManager
    from codelab.server.protocol.handlers.tool_call_handler import ToolCallHandler
    from codelab.server.protocol.state import LLMLoopResult, SessionState
    from codelab.server.tools.base import ToolRegistry

logger = structlog.get_logger()


class LLMLoopStage(PromptStage):
    """Тонкий адаптер pipeline → AgentLoop.

    Поддерживает два пути выполнения через LLMCallStrategy:
    - Legacy: через LegacyCallStrategy → AgentOrchestrator → NaiveAgent
    - EventBus: через StrategyDispatcher → SingleStrategy → LLMAdapter

    Стратегия выбирается лениво при первом вызове process().

    Example:
        stage = LLMLoopStage(
            tool_registry=tool_registry,
            strategy_dispatcher=strategy_dispatcher,  # EventBus путь
            ...
        )
        result = await stage.process(context)
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        tool_call_handler: ToolCallHandler,
        permission_manager: PermissionManager,
        state_manager: StateManager,
        plan_builder: PlanBuilder,
        global_policy_manager: GlobalPolicyManager | None = None,
        strategy_dispatcher: StrategyDispatcher | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        """Инициализация LLMLoopStage.

        Args:
            tool_registry: Реестр инструментов для выполнения.
            tool_call_handler: Обработчик tool calls для управления состоянием.
            permission_manager: Менеджер разрешений для permission requests.
            state_manager: Менеджер состояния сессии.
            plan_builder: Построитель планов выполнения.
            global_policy_manager: Менеджер глобальных политик (опционально).
            strategy_dispatcher: StrategyDispatcher для EventBus пути (опционально).
                Если None, используется LegacyCallStrategy.
            tracer: Tracer для observability (опционально).
        """
        self._tool_registry = tool_registry
        self._tool_call_handler = tool_call_handler
        self._permission_manager = permission_manager
        self._state_manager = state_manager
        self._plan_builder = plan_builder
        self._global_policy_manager = global_policy_manager
        self._strategy_dispatcher = strategy_dispatcher
        self._tracer = tracer

        # Компоненты для AgentLoop
        self._content_extractor = ContentExtractor()
        self._content_validator = ContentValidator()
        self._content_formatter = ContentFormatter()
        self._replay_manager = ReplayManager()

        # Лениво создаваемый AgentLoop
        self._agent_loop: AgentLoop | None = None

        strategy_name = "event_bus" if strategy_dispatcher else "legacy"
        logger.info(
            "LLMLoopStage initialized",
            strategy=strategy_name,
            tracer_enabled=tracer is not None,
        )

    def _get_or_create_agent_loop(self, context: PromptContext) -> AgentLoop:
        """Лениво создать AgentLoop с нужной стратегией.

        Args:
            context: Контекст pipeline для получения agent_orchestrator.

        Returns:
            AgentLoop с нужной стратегией.

        Raises:
            ValueError: Если стратегия не доступна.
        """
        if self._agent_loop is not None:
            return self._agent_loop

        # Определить стратегию
        strategy: LLMCallStrategy
        if self._strategy_dispatcher is not None:
            strategy = self._strategy_dispatcher
        else:
            agent_orchestrator = context.meta.get("agent_orchestrator")
            if agent_orchestrator is None:
                raise ValueError("No LLM strategy available: neither strategy_dispatcher nor agent_orchestrator")
            strategy = LegacyCallStrategy(agent_orchestrator)

        self._agent_loop = AgentLoop(
            strategy=strategy,
            tool_registry=self._tool_registry,
            tool_call_handler=self._tool_call_handler,
            permission_manager=self._permission_manager,
            state_manager=self._state_manager,
            content_extractor=self._content_extractor,
            content_validator=self._content_validator,
            content_formatter=self._content_formatter,
            replay_manager=self._replay_manager,
            plan_builder=self._plan_builder,
            global_policy_manager=self._global_policy_manager,
        )
        return self._agent_loop

    async def process(self, context: PromptContext) -> PromptContext:
        """Обработать prompt через AgentLoop.

        Args:
            context: Контекст pipeline.

        Returns:
            Обновлённый контекст с результатами.
        """
        # Demo mode: нет LLM
        agent_orchestrator: AgentOrchestrator | None = context.meta.get("agent_orchestrator")
        if agent_orchestrator is None and self._strategy_dispatcher is None:
            if context.raw_text:
                ack_text = f"ACK: {context.raw_text[:80]}"
                ack_content = {"type": "text", "text": ack_text}
                from codelab.server.messages import ACPMessage
                context.notifications.append(
                    ACPMessage.notification(
                        "session/update",
                        {
                            "sessionId": context.session_id,
                            "update": {
                                "sessionUpdate": "agent_message_chunk",
                                "content": ack_content,
                            },
                        },
                    )
                )
                self._replay_manager.save_agent_message_chunk(context.session, ack_content)
                self._state_manager.add_assistant_message(context.session, ack_text)
            return context

        agent_loop = self._get_or_create_agent_loop(context)
        mcp_manager = self._get_mcp_manager(context)

        result = await agent_loop.run(
            session=context.session,
            session_id=context.session_id,
            initial_prompt=context.raw_text,
            mcp_manager=mcp_manager,
        )

        context.notifications.extend(result.notifications)
        context.stop_reason = result.stop_reason or StopReason.END_TURN
        context.pending_permission = result.pending_permission

        if result.pending_permission:
            context.should_stop = True

        return context

    async def execute_pending_tool(
        self,
        session: SessionState,
        session_id: str,
        tool_call_id: str,
        agent_orchestrator: AgentOrchestrator,
        mcp_manager: Any | None = None,
    ) -> LLMLoopResult:
        """Выполнить pending tool после permission approval.

        Делегирует в legacy execute_pending_tool для обратной совместимости с тестами.
        """
        notifications: list[ACPMessage] = []

        # Выполнить pending tool
        tool_result = await self._execute_pending_tool_legacy(
            session, session_id, tool_call_id, mcp_manager
        )

        if tool_result is None:
            from codelab.server.protocol.state import LLMLoopResult
            return LLMLoopResult(notifications=notifications, stop_reason="end_turn")

        # Продолжить LLM loop через legacy метод
        llm_loop_result = await self._run_llm_loop(
            session=session,
            session_id=session_id,
            agent_orchestrator=agent_orchestrator,
            initial_prompt_text="",
            tool_results=[tool_result],
            mcp_manager=mcp_manager,
        )

        from codelab.server.protocol.state import LLMLoopResult
        return LLMLoopResult(
            notifications=notifications + llm_loop_result.notifications,
            stop_reason=llm_loop_result.stop_reason,
            final_text=llm_loop_result.final_text,
            pending_permission=llm_loop_result.pending_permission,
            pending_tool_calls=llm_loop_result.pending_tool_calls,
            tool_results=llm_loop_result.tool_results,
        )

    async def _execute_pending_tool_legacy(
        self,
        session: SessionState,
        session_id: str,
        tool_call_id: str,
        mcp_manager: Any | None,
    ) -> ToolResult | None:
        """Выполнить pending tool (legacy implementation)."""
        from codelab.server.protocol.state import ToolResult
        from codelab.server.tools.executors.mcp_executor import MCPToolExecutor
        from typing import Literal, cast

        tool_call_state = session.tool_calls.get(tool_call_id)
        if tool_call_state is None:
            return None

        tool_name = tool_call_state.tool_name
        tool_arguments = tool_call_state.tool_arguments
        tool_call_id_from_llm = tool_call_state.tool_call_id_from_llm

        if tool_name is None:
            return None

        try:
            if MCPToolExecutor.is_mcp_tool(tool_name):
                if mcp_manager is None:
                    raise RuntimeError("MCP manager not available for session")
                mcp_executor = MCPToolExecutor(mcp_manager)
                result = await mcp_executor.execute_tool(
                    session_id, tool_name, tool_arguments, session=session
                )
            else:
                result = await self._tool_registry.execute_tool(
                    session_id, tool_name, tool_arguments, session=session
                )

            extracted_content = await self._content_extractor.extract_from_result(tool_call_id, result)
            tool_call_state.result_content = extracted_content.content_items

            provider_raw = session.config_values.get("llm_provider", "openai")
            provider = cast(Literal["openai", "anthropic"], provider_raw)
            self._content_formatter.format_for_llm(extracted_content, provider=provider)

            if result.success:
                completed_content = [{"type": "content", "content": {"type": "text", "text": result.output or "Tool executed successfully"}}]
                self._tool_call_handler.update_tool_call_status(session, tool_call_id, "completed", content=completed_content)
                notifications = [self._tool_call_handler.build_tool_update_notification(
                    session_id=session_id, tool_call_id=tool_call_id, status="completed", content=completed_content
                )]
                self._replay_manager.save_tool_call_update(
                    session=session, tool_call_id=tool_call_id, status="completed", content=completed_content
                )
                return ToolResult(
                    tool_call_id=tool_call_id_from_llm or tool_call_id,
                    tool_name=tool_name,
                    success=True,
                    output=result.output,
                )
            else:
                error_content = [{"type": "content", "content": {"type": "text", "text": result.error or "Tool execution failed"}}]
                self._tool_call_handler.update_tool_call_status(session, tool_call_id, "failed", content=error_content)
                notifications = [self._tool_call_handler.build_tool_update_notification(
                    session_id=session_id, tool_call_id=tool_call_id, status="failed", content=error_content
                )]
                self._replay_manager.save_tool_call_update(
                    session=session, tool_call_id=tool_call_id, status="failed", content=error_content
                )
                return ToolResult(
                    tool_call_id=tool_call_id_from_llm or tool_call_id,
                    tool_name=tool_name,
                    success=False,
                    error=result.error,
                )

        except Exception as exc:
            error_content = [{"type": "content", "content": {"type": "text", "text": f"Tool execution error: {exc}"}}]
            self._tool_call_handler.update_tool_call_status(session, tool_call_id, "failed", content=error_content)
            notifications = [self._tool_call_handler.build_tool_update_notification(
                session_id=session_id, tool_call_id=tool_call_id, status="failed", content=error_content
            )]
            self._replay_manager.save_tool_call_update(
                session=session, tool_call_id=tool_call_id, status="failed", content=error_content
            )
            return ToolResult(
                tool_call_id=tool_call_id_from_llm or tool_call_id,
                tool_name=tool_name,
                success=False,
                error=str(exc),
            )

    def _get_mcp_manager(self, context: PromptContext):
        """Получить MCP manager из PromptContext.meta."""
        return context.meta.get("mcp_manager")

    # =========================================================================
    # Legacy methods for backward compatibility with tests
    # Эти методы делегируют в AgentLoop для обратной совместимости с тестами
    # =========================================================================

    async def _process_tool_calls_for_llm_loop(
        self,
        session: SessionState,
        session_id: str,
        tool_calls: list,
        notifications: list,
        mcp_manager: Any | None = None,
    ) -> LLMLoopResult:
        """Обработать tool calls (legacy interface для тестов).

        Эта реализация использует self._decide_tool_execution для обратной
        совместимости с тестами которые патчат этот метод.
        """
        from codelab.server.protocol.state import LLMLoopResult, ToolResult
        from codelab.server.tools.executors.mcp_executor import MCPToolExecutor
        from codelab.server.tools.mapping import llm_name_to_acp_name
        from typing import Literal, cast

        tool_results: list[ToolResult] = []

        for tool_call in tool_calls:
            tool_name = getattr(tool_call, "name", None)
            tool_arguments = getattr(tool_call, "arguments", {})
            tool_call_id_from_llm = getattr(tool_call, "id", None)

            if not tool_name:
                continue

            acp_tool_name = llm_name_to_acp_name(tool_name)
            tool_kind = "other"
            is_mcp = MCPToolExecutor.is_mcp_tool(acp_tool_name)

            tool_definition = self._tool_registry.get(acp_tool_name)
            if tool_definition is not None:
                tool_kind = tool_definition.kind

            tool_call_id = self._tool_call_handler.create_tool_call(
                session=session,
                title=acp_tool_name,
                kind=tool_kind,
                tool_name=acp_tool_name,
                tool_arguments=tool_arguments,
                tool_call_id_from_llm=tool_call_id_from_llm,
            )

            notifications.append(
                self._tool_call_handler.build_tool_call_notification(
                    session_id=session_id,
                    tool_call_id=tool_call_id,
                    title=acp_tool_name,
                    kind=tool_kind,
                )
            )

            self._replay_manager.save_tool_call(
                session=session,
                tool_call_id=tool_call_id,
                title=acp_tool_name,
                kind=tool_kind,
                status="pending",
            )

            # Используем self._decide_tool_execution для обратной совместимости с тестами
            if is_mcp:
                decision = await self._decide_tool_execution(session, tool_kind)
            elif tool_definition is not None and not tool_definition.requires_permission:
                decision = "allow"
            else:
                decision = await self._decide_tool_execution(session, tool_kind)

            if decision == "ask":
                tool_call_state = session.tool_calls.get(tool_call_id)
                if tool_call_state is not None:
                    permission_msg = self._permission_manager.build_permission_request(
                        session, session_id, tool_call_state.tool_call_id, tool_call_state.title, tool_kind
                    )
                    notifications.append(permission_msg)
                    if session.active_turn:
                        session.active_turn.phase = "awaiting_permission"
                        session.active_turn.permission_tool_call_id = tool_call_id

                return LLMLoopResult(
                    notifications=notifications,
                    tool_results=tool_results,
                    pending_permission=True,
                )

            if decision == "reject":
                self._tool_call_handler.update_tool_call_status(session, tool_call_id, "failed")
                rejection_msg = f"Tool execution rejected by policy for {tool_kind}"
                rejection_content = [{"type": "content", "content": {"type": "text", "text": rejection_msg}}]
                notifications.append(
                    self._tool_call_handler.build_tool_update_notification(
                        session_id=session_id, tool_call_id=tool_call_id, status="failed", content=rejection_content
                    )
                )
                self._replay_manager.save_tool_call_update(
                    session=session, tool_call_id=tool_call_id, status="failed", content=rejection_content
                )
                tool_results.append(ToolResult(
                    tool_call_id=tool_call_id_from_llm or tool_call_id,
                    tool_name=acp_tool_name,
                    success=False,
                    error=rejection_msg,
                ))
                continue

            # decision == "allow"
            try:
                self._tool_call_handler.update_tool_call_status(session, tool_call_id, "in_progress")
                notifications.append(
                    self._tool_call_handler.build_tool_update_notification(
                        session_id=session_id, tool_call_id=tool_call_id, status="in_progress"
                    )
                )
                self._replay_manager.save_tool_call_update(
                    session=session, tool_call_id=tool_call_id, status="in_progress"
                )

                if is_mcp:
                    if mcp_manager is None:
                        raise RuntimeError("MCP manager not available for session")
                    mcp_executor = MCPToolExecutor(mcp_manager)
                    result = await mcp_executor.execute_tool(
                        session_id, acp_tool_name, tool_arguments, session=session
                    )
                else:
                    result = await self._tool_registry.execute_tool(
                        session_id, acp_tool_name, tool_arguments, session=session
                    )

                extracted_content = await self._content_extractor.extract_from_result(tool_call_id, result)
                is_valid, errors = self._content_validator.validate_content_list(extracted_content.content_items)

                tool_call_state = session.tool_calls.get(tool_call_id)
                if tool_call_state:
                    tool_call_state.result_content = extracted_content.content_items

                provider_raw = session.config_values.get("llm_provider", "openai")
                provider = cast(Literal["openai", "anthropic"], provider_raw)
                self._content_formatter.format_for_llm(extracted_content, provider=provider)

                if result.success:
                    success_text = result.output or "Success"
                    success_content = [{"type": "content", "content": {"type": "text", "text": success_text}}]
                    self._tool_call_handler.update_tool_call_status(
                        session, tool_call_id, "completed", content=success_content
                    )
                    status = "completed"
                else:
                    success_content = None
                    self._tool_call_handler.update_tool_call_status(session, tool_call_id, "failed")
                    status = "failed"

                notification_content = None
                if result.success and result.output:
                    notification_content = [{"type": "content", "content": {"type": "text", "text": result.output}}]

                notifications.append(
                    self._tool_call_handler.build_tool_update_notification(
                        session_id=session_id, tool_call_id=tool_call_id, status=status, content=notification_content
                    )
                )
                self._replay_manager.save_tool_call_update(
                    session=session, tool_call_id=tool_call_id, status=status, content=notification_content
                )

                tool_results.append(ToolResult(
                    tool_call_id=tool_call_id_from_llm or tool_call_id,
                    tool_name=acp_tool_name,
                    success=result.success,
                    output=result.output,
                    content=extracted_content.content_items,
                    error=result.error,
                ))

            except Exception as e:
                self._tool_call_handler.update_tool_call_status(session, tool_call_id, "failed")
                notifications.append(
                    self._tool_call_handler.build_tool_update_notification(
                        session_id=session_id, tool_call_id=tool_call_id, status="failed"
                    )
                )
                self._replay_manager.save_tool_call_update(
                    session=session, tool_call_id=tool_call_id, status="failed"
                )
                tool_results.append(ToolResult(
                    tool_call_id=tool_call_id_from_llm or tool_call_id,
                    tool_name=acp_tool_name,
                    success=False,
                    error=str(e),
                ))

        return LLMLoopResult(notifications=notifications, tool_results=tool_results)

    async def run_loop(
        self,
        session: SessionState,
        session_id: str,
        agent_orchestrator: Any,
        initial_prompt_text: str | None = None,
        tool_results: list | None = None,
        mcp_manager: Any | None = None,
    ) -> LLMLoopResult:
        """Запустить LLM loop (legacy interface для тестов).

        Делегирует в AgentLoop.run().
        """
        from ..context import PromptContext
        
        # Создать LegacyCallStrategy из agent_orchestrator
        strategy = LegacyCallStrategy(agent_orchestrator)
        
        # Создать AgentLoop с этой стратегией
        agent_loop = AgentLoop(
            strategy=strategy,
            tool_registry=self._tool_registry,
            tool_call_handler=self._tool_call_handler,
            permission_manager=self._permission_manager,
            state_manager=self._state_manager,
            content_extractor=self._content_extractor,
            content_validator=self._content_validator,
            content_formatter=self._content_formatter,
            replay_manager=self._replay_manager,
            plan_builder=self._plan_builder,
            global_policy_manager=self._global_policy_manager,
        )

        result = await agent_loop.run(
            session=session,
            session_id=session_id,
            initial_prompt=initial_prompt_text,
            mcp_manager=mcp_manager,
        )

        from codelab.server.protocol.state import LLMLoopResult
        return LLMLoopResult(
            notifications=result.notifications,
            stop_reason=result.stop_reason.value if isinstance(result.stop_reason, StopReason) else result.stop_reason,
            final_text=result.text,
            pending_permission=result.pending_permission,
            tool_results=result.tool_results,
        )

    async def _run_llm_loop(
        self,
        session: SessionState,
        session_id: str,
        agent_orchestrator: Any,
        initial_prompt_text: str | None = None,
        tool_results: list | None = None,
        mcp_manager: Any | None = None,
    ) -> LLMLoopResult:
        """Legacy LLM loop (legacy interface для тестов).

        Делегирует в run_loop().
        """
        return await self.run_loop(
            session=session,
            session_id=session_id,
            agent_orchestrator=agent_orchestrator,
            initial_prompt_text=initial_prompt_text,
            tool_results=tool_results,
            mcp_manager=mcp_manager,
        )

    def _get_agent_loop_for_legacy(self) -> AgentLoop:
        """Получить AgentLoop для legacy методов (без context).

        Создаёт AgentLoop с LegacyCallStrategy используя mock orchestrator.
        """
        if self._agent_loop is not None:
            return self._agent_loop

        # Для legacy методов создаём AgentLoop с mock стратегией
        # Это нужно только для тестов которые вызывают внутренние методы напрямую
        from unittest.mock import MagicMock
        mock_strategy = MagicMock()
        self._agent_loop = AgentLoop(
            strategy=mock_strategy,
            tool_registry=self._tool_registry,
            tool_call_handler=self._tool_call_handler,
            permission_manager=self._permission_manager,
            state_manager=self._state_manager,
            content_extractor=self._content_extractor,
            content_validator=self._content_validator,
            content_formatter=self._content_formatter,
            replay_manager=self._replay_manager,
            plan_builder=self._plan_builder,
            global_policy_manager=self._global_policy_manager,
        )
        return self._agent_loop

    def _is_cancel_requested(self, session: SessionState) -> bool:
        """Проверить флаг отмены (legacy interface для тестов)."""
        return session.active_turn is not None and session.active_turn.cancel_requested

    async def _decide_tool_execution(self, session: SessionState, tool_kind: str) -> str:
        """Определить решение о выполнении tool (legacy interface для тестов)."""
        agent_loop = self._get_agent_loop_for_legacy()
        return await agent_loop._decide_tool_execution(session, tool_kind)

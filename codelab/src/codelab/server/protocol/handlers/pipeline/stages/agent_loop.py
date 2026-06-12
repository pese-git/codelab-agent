"""AgentLoop — унифицированный цикл итераций LLM tool-calling.

Соответствует ACP 05-Prompt Turn.md:
- loop Until completion (строка 30)
- max_turn_requests stop reason (строка 277-279)
- Tool results back to LLM (строки 261-263)

Архитектурное решение:
- AgentLoop отвечает за цикл итераций, tool-calling, permission
- LLMCallStrategy отвечает за вызов LLM
- Разделение ответственности (SRP)
- Strategy Pattern для разных способов вызова LLM (OCP)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, cast

import structlog

from codelab.server.messages import ACPMessage
from codelab.server.protocol.content.extractor import ContentExtractor
from codelab.server.protocol.content.formatter import ContentFormatter
from codelab.server.protocol.content.validator import ContentValidator
from codelab.server.protocol.handlers.permission_manager import PermissionManager
from codelab.server.protocol.handlers.plan_builder import PlanBuilder
from codelab.server.protocol.handlers.replay_manager import ReplayManager
from codelab.server.protocol.handlers.state_manager import StateManager
from codelab.server.protocol.handlers.tool_call_handler import ToolCallHandler
from codelab.server.protocol.state import SessionState, ToolResult
from codelab.server.protocol.stop_reasons import StopReason
from codelab.server.tools.base import ToolRegistry
from codelab.server.tools.executors.mcp_executor import MCPToolExecutor
from codelab.server.tools.mapping import llm_name_to_acp_name

if TYPE_CHECKING:
    from codelab.server.agent.base import AgentResponse
    from codelab.server.agent.strategies.base import LLMCallStrategy
    from codelab.server.agent.system_prompt_builder import SystemPromptBuilder
    from codelab.server.protocol.handlers.global_policy_manager import GlobalPolicyManager

logger = structlog.get_logger()


@dataclass
class AgentLoopResult:
    """Результат выполнения AgentLoop.

    Attributes:
        text: Текст ответа агента.
        stop_reason: Причина остановки (ACP stop reason).
        notifications: Список notifications для клиента.
        pending_permission: True если требуется permission.
        pending_tool_calls: Список tool_call_id ожидающих permission.
        tool_results: Список результатов выполнения tools.
    """

    text: str | None = None
    stop_reason: StopReason = StopReason.END_TURN
    notifications: list[ACPMessage] = field(default_factory=list)
    pending_permission: bool = False
    pending_tool_calls: list[str] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)


@dataclass
class ToolProcessingResult:
    """Результат обработки tool calls.

    Внутренний результат для передачи между методами AgentLoop.

    Attributes:
        tool_results: Список результатов выполнения tools.
        pending_permission: True если требуется permission.
        pending_tool_calls: Список tool_call_id ожидающих permission.
    """

    tool_results: list[ToolResult] = field(default_factory=list)
    pending_permission: bool = False
    pending_tool_calls: list[str] = field(default_factory=list)


class AgentLoop:
    """Универсальный цикл итераций LLM tool-calling.

    Соответствует ACP 05-Prompt Turn.md:
    - loop Until completion (строка 30)
    - max_turn_requests stop reason (строка 277-279)
    - Tool results back to LLM (строки 261-263)

    Responsibilities:
    - Цикл итераций (max_turn_requests)
    - Вызов LLM через LLMCallStrategy
    - Обработка tool_calls
    - Permission pause/resume
    - Cancellation handling

    НЕ отвечает за:
    - Вызов LLM (делает LLMCallStrategy)
    - Выполнение tools (делает ToolRegistry)
    - Pipeline integration (делает LLMLoopStage)

    Example:
        loop = AgentLoop(
            strategy=strategy_dispatcher,
            tool_registry=tool_registry,
            ...
        )
        result = await loop.run(session, session_id, "Hello")
        if result.pending_permission:
            # ...等待 permission ...
            result = await loop.resume_after_permission(session, tool_call_id)
    """

    def __init__(
        self,
        strategy: LLMCallStrategy,
        tool_registry: ToolRegistry,
        tool_call_handler: ToolCallHandler,
        permission_manager: PermissionManager,
        state_manager: StateManager,
        content_extractor: ContentExtractor,
        content_validator: ContentValidator,
        content_formatter: ContentFormatter,
        replay_manager: ReplayManager,
        plan_builder: PlanBuilder,
        system_prompt_builder: SystemPromptBuilder,
        global_policy_manager: GlobalPolicyManager | None = None,
        max_turn_requests: int = 10,
    ) -> None:
        """Инициализация AgentLoop.

        Args:
            strategy: Стратегия вызова LLM (StrategyDispatcher).
            tool_registry: Реестр инструментов для выполнения.
            tool_call_handler: Обработчик tool calls для управления состоянием.
            permission_manager: Менеджер разрешений для permission requests.
            state_manager: Менеджер состояния сессии.
            content_extractor: Извлекатель контента из результатов tools.
            content_validator: Валидатор контента.
            content_formatter: Форматировщик контента для LLM.
            replay_manager: Менеджер replay для сохранения событий.
            plan_builder: Построитель планов выполнения.
            system_prompt_builder: Билдер system prompt (config + MCP info).
            global_policy_manager: Менеджер глобальных политик (опционально).
            max_turn_requests: Максимальное количество запросов к LLM в turn.
        """
        self._strategy = strategy
        self._tool_registry = tool_registry
        self._tool_call_handler = tool_call_handler
        self._permission_manager = permission_manager
        self._state_manager = state_manager
        self._content_extractor = content_extractor
        self._content_validator = content_validator
        self._content_formatter = content_formatter
        self._replay_manager = replay_manager
        self._plan_builder = plan_builder
        self._system_prompt_builder = system_prompt_builder
        self._global_policy_manager = global_policy_manager
        self._max_turn_requests = max_turn_requests

    async def run(
        self,
        session: SessionState,
        session_id: str,
        initial_prompt: str | None = None,
        mcp_manager: Any | None = None,
    ) -> AgentLoopResult:
        """Запустить цикл итераций.

        Flow:
        1. Вызов LLM (execute или continue_execution)
        2. Обработка ответа (text, tool_calls, plan)
        3. Если нет tool_calls → завершить
        4. Обработка tool_calls
        5. Если permission required → приостановить
        6. Продолжить цикл

        Args:
            session: Состояние сессии.
            session_id: ID сессии для логирования.
            initial_prompt: Текст начального промпта (None для продолжения).
            mcp_manager: MCP manager для tool execution.

        Returns:
            AgentLoopResult с результатом выполнения.
        """
        notifications: list[ACPMessage] = []
        iteration = 0
        final_text: str | None = None

        while iteration < self._max_turn_requests:
            iteration += 1

            # Проверка отмены
            if self._is_cancel_requested(session):
                logger.debug(
                    "agent_loop cancelled before LLM call",
                    session_id=session_id,
                    iteration=iteration,
                )
                return AgentLoopResult(
                    notifications=notifications,
                    stop_reason=StopReason.CANCELLED,
                )

            # Вызов LLM
            try:
                response = await self._call_llm(session, initial_prompt, mcp_manager, iteration)
            except Exception as e:
                logger.error(
                    "LLM call failed",
                    session_id=session_id,
                    iteration=iteration,
                    error=str(e),
                )
                notifications.append(self._build_error_notification(session_id, str(e)))
                return AgentLoopResult(
                    notifications=notifications,
                    stop_reason=StopReason.END_TURN,
                )

            # Проверка отмены после LLM
            if self._is_cancel_requested(session):
                logger.debug(
                    "agent_loop cancelled after LLM call",
                    session_id=session_id,
                    iteration=iteration,
                )
                return AgentLoopResult(
                    notifications=notifications,
                    stop_reason=StopReason.CANCELLED,
                )

            # Обработка ответа
            agent_text = response.text if response else ""
            has_tool_calls = bool(response and response.tool_calls)

            logger.debug(
                "llm_response_received",
                session_id=session_id,
                iteration=iteration,
                has_text=bool(agent_text),
                has_tool_calls=has_tool_calls,
                tool_call_count=len(response.tool_calls) if response else 0,
                stop_reason=getattr(response, "stop_reason", None),
            )

            if agent_text:
                final_text = agent_text
                self._state_manager.add_assistant_message(session, agent_text)
                notification = self._build_agent_response_notification(session_id, agent_text)
                notifications.append(notification)
                # Сохранить в events_history для replay при session/load
                self._replay_manager.save_agent_message_chunk(
                    session,
                    {"type": "text", "text": agent_text},
                )

            # Обработка plan
            plan = getattr(response, "plan", None)
            if plan:
                validated_plan = self._plan_builder.validate_plan_entries(plan)
                if validated_plan:
                    session.latest_plan = list(validated_plan)
                    notifications.append(
                        self._plan_builder.build_plan_notification(session_id, validated_plan)
                    )
                    self._replay_manager.save_plan(session, validated_plan)

            # Нет tool_calls → завершить
            if not has_tool_calls:
                logger.debug(
                    "agent_loop completed - no tool calls",
                    session_id=session_id,
                    iteration=iteration,
                )
                return AgentLoopResult(
                    text=final_text,
                    stop_reason=StopReason.END_TURN,
                    notifications=notifications,
                )

            # Обработка tool_calls
            logger.info(
                "agent_loop processing tool calls",
                session_id=session_id,
                iteration=iteration,
                num_tool_calls=len(response.tool_calls),
            )

            # Добавляем tool_calls в историю
            tool_calls_for_history = [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in response.tool_calls
            ]
            session.history.append(
                {
                    "role": "assistant",
                    "text": agent_text or "",
                    "tool_calls": tool_calls_for_history,
                }
            )

            # Обрабатываем tool_calls
            tool_result = await self._process_tool_calls(
                session, session_id, response.tool_calls, notifications, mcp_manager
            )

            # Permission pause
            if tool_result.pending_permission:
                logger.debug(
                    "agent_loop deferred for permission",
                    session_id=session_id,
                    iteration=iteration,
                )
                return AgentLoopResult(
                    notifications=notifications,
                    pending_permission=True,
                    pending_tool_calls=tool_result.pending_tool_calls,
                    tool_results=tool_result.tool_results,
                )

            # Проверка отмены во время tool processing
            if self._is_cancel_requested(session):
                logger.debug(
                    "agent_loop cancelled during tool processing",
                    session_id=session_id,
                    iteration=iteration,
                )
                return AgentLoopResult(
                    notifications=notifications,
                    stop_reason=StopReason.CANCELLED,
                )

            # Продолжить цикл — prompt=None для continue_execution
            initial_prompt = None

        # Max iterations reached
        logger.warning(
            "agent_loop max_turn_requests reached",
            session_id=session_id,
            max_turn_requests=self._max_turn_requests,
        )
        return AgentLoopResult(
            text=final_text,
            stop_reason=StopReason.MAX_TURN_REQUESTS,
            notifications=notifications,
        )

    async def resume_after_permission(
        self,
        session: SessionState,
        session_id: str,
        tool_call_id: str,
        mcp_manager: Any | None = None,
    ) -> AgentLoopResult:
        """Продолжить цикл после permission approval.

        Flow:
        1. Выполнить pending tool
        2. Продолжить цикл через run()

        Args:
            session: Состояние сессии.
            session_id: ID сессии для логирования.
            tool_call_id: ID tool call для выполнения.
            mcp_manager: MCP manager для tool execution.

        Returns:
            AgentLoopResult с результатом выполнения.
        """
        notifications: list[ACPMessage] = []

        # Убедиться что стратегия инициализирована для continue_execution.
        # StrategyDispatcher имеет _current_strategy_name и select_strategy,
        # но LLMCallStrategy Protocol их не определяет — проверяем динамически.
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

        # Выполнить pending tool
        tool_result = await self._execute_pending_tool(
            session, session_id, tool_call_id, mcp_manager
        )

        if tool_result is None:
            return AgentLoopResult(
                notifications=notifications,
                stop_reason=StopReason.END_TURN,
            )

        # Продолжить цикл (tool_results уже в session.history)
        loop_result = await self.run(
            session=session,
            session_id=session_id,
            initial_prompt=None,
            mcp_manager=mcp_manager,
        )

        # Объединяем notifications
        return AgentLoopResult(
            text=loop_result.text,
            stop_reason=loop_result.stop_reason,
            notifications=notifications + loop_result.notifications,
            pending_permission=loop_result.pending_permission,
            pending_tool_calls=loop_result.pending_tool_calls,
            tool_results=loop_result.tool_results,
        )

    async def _call_llm(
        self,
        session: SessionState,
        prompt: str | None,
        mcp_manager: Any | None,
        iteration: int,
    ) -> AgentResponse:
        """Вызвать LLM через стратегию.

        Args:
            session: Состояние сессии.
            prompt: Текст промпта (None для продолжения).
            mcp_manager: MCP manager.
            iteration: Номер итерации.

        Returns:
            AgentResponse с ответом LLM.
        """
        # Формируем system prompt (agent + config + MCP info)
        system_prompt = self._system_prompt_builder.build(session, mcp_manager)

        if iteration == 1 and prompt:
            return await self._strategy.execute(
                session, prompt, mcp_manager, system_prompt=system_prompt
            )
        else:
            return await self._strategy.continue_execution(session, mcp_manager)

    async def _process_tool_calls(
        self,
        session: SessionState,
        session_id: str,
        tool_calls: list,
        notifications: list[ACPMessage],
        mcp_manager: Any | None,
    ) -> ToolProcessingResult:
        """Обработать tool calls из ответа LLM.

        Перенесено из LLMLoopStage._process_tool_calls_for_llm_loop.

        Args:
            session: Состояние сессии.
            session_id: ID сессии.
            tool_calls: Список tool calls из ответа LLM.
            notifications: Список notifications (добавляются на месте).
            mcp_manager: MCP manager.

        Returns:
            ToolProcessingResult с результатами обработки.
        """
        tool_results: list[ToolResult] = []

        for tool_call in tool_calls:
            # Проверка отмены
            if self._is_cancel_requested(session):
                logger.debug("tool processing cancelled", session_id=session_id)
                return ToolProcessingResult(
                    tool_results=tool_results,
                    pending_permission=False,
                )

            tool_name = getattr(tool_call, "name", None)
            tool_arguments = getattr(tool_call, "arguments", {})
            tool_call_id_from_llm = getattr(tool_call, "id", None)

            if not tool_name:
                logger.warning("tool_call has no name", session_id=session_id)
                continue

            # Конвертируем LLM имя обратно в ACP формат
            acp_tool_name = llm_name_to_acp_name(tool_name)

            # Определяем тип инструмента
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

            # MCP инструменты всегда требуют разрешения (по умолчанию)
            if is_mcp:
                decision = await self._decide_tool_execution(session, tool_kind)
            elif tool_definition is not None and not tool_definition.requires_permission:
                decision = "allow"
            else:
                decision = await self._decide_tool_execution(session, tool_kind)

            logger.debug(
                "tool_execution_decision",
                session_id=session_id,
                tool_name=acp_tool_name,
                tool_kind=tool_kind,
                is_mcp=is_mcp,
                requires_permission=(
                    tool_definition.requires_permission if tool_definition else None
                ),
                mode=session.config_values.get("mode", "standard"),
                decision=decision,
            )

            if decision == "ask":
                tool_call_state = session.tool_calls.get(tool_call_id)
                if tool_call_state is not None:
                    permission_msg = self._permission_manager.build_permission_request(
                        session,
                        session_id,
                        tool_call_state.tool_call_id,
                        tool_call_state.title,
                        tool_kind,
                    )
                    notifications.append(permission_msg)

                    if session.active_turn:
                        session.active_turn.phase = "awaiting_permission"
                        session.active_turn.permission_tool_call_id = tool_call_id

                logger.debug(
                    "permission request sent, pausing agent loop",
                    session_id=session_id,
                    tool_call_id=tool_call_id,
                )
                return ToolProcessingResult(
                    tool_results=tool_results,
                    pending_permission=True,
                    pending_tool_calls=[tool_call_id],
                )

            if decision == "reject":
                self._tool_call_handler.update_tool_call_status(session, tool_call_id, "failed")
                rejection_msg = f"Tool execution rejected by policy for {tool_kind}"
                rejection_content = [
                    {"type": "content", "content": {"type": "text", "text": rejection_msg}}
                ]
                notifications.append(
                    self._tool_call_handler.build_tool_update_notification(
                        session_id=session_id,
                        tool_call_id=tool_call_id,
                        status="failed",
                        content=rejection_content,
                    )
                )
                self._replay_manager.save_tool_call_update(
                    session=session,
                    tool_call_id=tool_call_id,
                    status="failed",
                    content=rejection_content,
                )
                tool_results.append(
                    ToolResult(
                        tool_call_id=tool_call_id_from_llm or tool_call_id,
                        tool_name=acp_tool_name,
                        success=False,
                        error=rejection_msg,
                    )
                )
                continue

            # decision == "allow"
            try:
                self._tool_call_handler.update_tool_call_status(
                    session, tool_call_id, "in_progress"
                )
                notifications.append(
                    self._tool_call_handler.build_tool_update_notification(
                        session_id=session_id,
                        tool_call_id=tool_call_id,
                        status="in_progress",
                    )
                )
                self._replay_manager.save_tool_call_update(
                    session=session,
                    tool_call_id=tool_call_id,
                    status="in_progress",
                )

                # MCP инструменты выполняются через MCPExecutor
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

                extracted_content = await self._content_extractor.extract_from_result(
                    tool_call_id, result
                )

                is_valid, errors = self._content_validator.validate_content_list(
                    extracted_content.content_items
                )
                if not is_valid:
                    logger.warning(
                        "tool_result_content_validation_failed",
                        tool_call_id=tool_call_id,
                        errors=errors,
                    )

                tool_call_state = session.tool_calls.get(tool_call_id)
                if tool_call_state:
                    tool_call_state.result_content = extracted_content.content_items

                provider_raw = session.config_values.get("llm_provider", "openai")
                provider = cast(Literal["openai", "anthropic"], provider_raw)
                self._content_formatter.format_for_llm(extracted_content, provider=provider)

                if result.success:
                    success_text = result.output or "Success"
                    success_content = [
                        {"type": "content", "content": {"type": "text", "text": success_text}}
                    ]
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
                    notification_content = [
                        {"type": "content", "content": {"type": "text", "text": result.output}}
                    ]

                notifications.append(
                    self._tool_call_handler.build_tool_update_notification(
                        session_id=session_id,
                        tool_call_id=tool_call_id,
                        status=status,
                        content=notification_content,
                    )
                )
                self._replay_manager.save_tool_call_update(
                    session=session,
                    tool_call_id=tool_call_id,
                    status=status,
                    content=notification_content,
                )

                tool_results.append(
                    ToolResult(
                        tool_call_id=tool_call_id_from_llm or tool_call_id,
                        tool_name=acp_tool_name,
                        success=result.success,
                        output=result.output,
                        content=extracted_content.content_items,
                        error=result.error,
                    )
                )

                # Добавляем tool result в историю для LLM
                self._add_tool_result_to_history(
                    session,
                    tool_call_id_from_llm or tool_call_id,
                    result.success,
                    result.output,
                    result.error,
                )

                # Plan tool: отправить plan notification клиенту согласно ACP spec
                # (protocol/11-Agent Plan.md)
                if acp_tool_name == "update_plan" and result.success:
                    plan_entries = (
                        result.metadata.get("validated_entries")
                        if result.metadata
                        else None
                    )
                    if plan_entries:
                        session.latest_plan = list(plan_entries)
                        notifications.append(
                            self._plan_builder.build_plan_notification(
                                session_id, plan_entries
                            )
                        )
                        self._replay_manager.save_plan(session, plan_entries)
                        logger.debug(
                            "plan notification sent from update_plan tool",
                            session_id=session_id,
                            entries_count=len(plan_entries),
                        )

            except Exception as e:
                logger.error(
                    "tool execution failed",
                    session_id=session_id,
                    tool_name=tool_name,
                    error=str(e),
                )
                self._tool_call_handler.update_tool_call_status(session, tool_call_id, "failed")
                notifications.append(
                    self._tool_call_handler.build_tool_update_notification(
                        session_id=session_id,
                        tool_call_id=tool_call_id,
                        status="failed",
                    )
                )
                self._replay_manager.save_tool_call_update(
                    session=session,
                    tool_call_id=tool_call_id,
                    status="failed",
                )
                tool_results.append(
                    ToolResult(
                        tool_call_id=tool_call_id_from_llm or tool_call_id,
                        tool_name=acp_tool_name,
                        success=False,
                        error=str(e),
                    )
                )

                # Добавляем tool result в историю для LLM
                self._add_tool_result_to_history(
                    session,
                    tool_call_id_from_llm or tool_call_id,
                    False,
                    None,
                    str(e),
                )

        return ToolProcessingResult(tool_results=tool_results)

    async def _execute_pending_tool(
        self,
        session: SessionState,
        session_id: str,
        tool_call_id: str,
        mcp_manager: Any | None,
    ) -> ToolResult | None:
        """Выполнить pending tool после permission approval.

        Перенесено из LLMLoopStage.execute_pending_tool.

        Args:
            session: Состояние сессии.
            session_id: ID сессии.
            tool_call_id: ID tool call для выполнения.
            mcp_manager: MCP manager.

        Returns:
            ToolResult или None если tool не найден.
        """
        tool_call_state = session.tool_calls.get(tool_call_id)
        if tool_call_state is None:
            logger.error(
                "tool_call_state not found for pending execution",
                session_id=session_id,
                tool_call_id=tool_call_id,
            )
            return None

        tool_name = tool_call_state.tool_name
        tool_arguments = tool_call_state.tool_arguments
        tool_call_id_from_llm = tool_call_state.tool_call_id_from_llm

        if tool_name is None:
            logger.error(
                "tool_name not found in tool_call_state",
                session_id=session_id,
                tool_call_id=tool_call_id,
            )
            return None

        logger.info(
            "executing pending tool after permission approval",
            session_id=session_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
        )

        try:
            # MCP инструменты выполняются через MCPExecutor
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

            extracted_content = await self._content_extractor.extract_from_result(
                tool_call_id, result
            )
            tool_call_state.result_content = extracted_content.content_items

            provider_raw = session.config_values.get("llm_provider", "openai")
            provider = cast(Literal["openai", "anthropic"], provider_raw)
            self._content_formatter.format_for_llm(extracted_content, provider=provider)

            if result.success:
                completed_content = [
                    {
                        "type": "content",
                        "content": {
                            "type": "text",
                            "text": result.output or "Tool executed successfully",
                        },
                    }
                ]
                self._tool_call_handler.update_tool_call_status(
                    session, tool_call_id, "completed", content=completed_content
                )
                # Добавляем tool result в историю для LLM
                self._add_tool_result_to_history(
                    session, tool_call_id_from_llm or tool_call_id, True, result.output, None
                )
                return ToolResult(
                    tool_call_id=tool_call_id_from_llm or tool_call_id,
                    tool_name=tool_name,
                    success=True,
                    output=result.output,
                )
            else:
                error_content = [
                    {
                        "type": "content",
                        "content": {
                            "type": "text",
                            "text": result.error or "Tool execution failed",
                        },
                    }
                ]
                self._tool_call_handler.update_tool_call_status(
                    session, tool_call_id, "failed", content=error_content
                )
                # Добавляем tool result в историю для LLM
                self._add_tool_result_to_history(
                    session, tool_call_id_from_llm or tool_call_id, False, None, result.error
                )
                return ToolResult(
                    tool_call_id=tool_call_id_from_llm or tool_call_id,
                    tool_name=tool_name,
                    success=False,
                    error=result.error,
                )

        except Exception as exc:
            logger.error(
                "tool execution failed with exception",
                session_id=session_id,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                error=str(exc),
                exc_info=True,
            )
            error_content = [
                {
                    "type": "content",
                    "content": {"type": "text", "text": f"Tool execution error: {exc}"},
                }
            ]
            self._tool_call_handler.update_tool_call_status(
                session, tool_call_id, "failed", content=error_content
            )
            # Добавляем tool result в историю для LLM
            self._add_tool_result_to_history(
                session, tool_call_id_from_llm or tool_call_id, False, None, str(exc)
            )
            return ToolResult(
                tool_call_id=tool_call_id_from_llm or tool_call_id,
                tool_name=tool_name,
                success=False,
                error=str(exc),
            )

    def _add_tool_result_to_history(
        self,
        session: SessionState,
        tool_call_id: str,
        success: bool,
        output: str | None,
        error: str | None,
    ) -> None:
        """Добавить результат выполнения tool в историю сессии.

        Формат соответствует OpenAI API для tool response messages:
          {"role": "tool", "tool_call_id": "...", "content": "..."}

        Args:
            session: Состояние сессии (мутируется).
            tool_call_id: ID tool call.
            success: Успешно ли выполнен tool.
            output: Выход tool (если успешен).
            error: Ошибка (если не успешен).
        """
        content = output if success else (error or "Tool execution failed")

        session.history.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": content or "",
            }
        )

        logger.debug(
            "tool_result_added_to_history",
            session_id=session.session_id,
            tool_call_id=tool_call_id,
            success=success,
        )

    async def _decide_tool_execution(self, session: SessionState, tool_kind: str) -> str:
        """Определить решение о выполнении tool.

        Цепочка решений:
        1. mode=plan → reject для write/execute, allow для read
        2. mode=bypass → allow все инструменты
        3. mode=standard → session policy → global policy → ask

        Args:
            session: Состояние сессии.
            tool_kind: Тип инструмента.

        Returns:
            "allow", "reject" или "ask".
        """
        from ....mode import MODE_BYPASS, MODE_PLAN, is_tool_blocked_in_plan_mode

        mode = session.config_values.get("mode", "standard")

        # 1. Plan mode: блокируем write/execute инструменты
        if mode == MODE_PLAN:
            if is_tool_blocked_in_plan_mode(tool_kind):
                return "reject"
            return "allow"

        # 2. Bypass mode: auto-execute все инструменты
        if mode == MODE_BYPASS:
            return "allow"

        # 3. Standard mode: policy chain
        session_policy = session.permission_policy.get(tool_kind)
        if session_policy == "allow_always":
            return "allow"
        if session_policy == "reject_always":
            return "reject"

        if self._global_policy_manager is not None:
            global_policy = await self._global_policy_manager.get_global_policy(tool_kind)
            if global_policy == "allow_always":
                return "allow"
            if global_policy == "reject_always":
                return "reject"

        return "ask"

    def _is_cancel_requested(self, session: SessionState) -> bool:
        """Проверить флаг отмены."""
        return session.active_turn is not None and session.active_turn.cancel_requested

    def _build_error_notification(self, session_id: str, error_message: str) -> ACPMessage:
        """Построить notification об ошибке."""
        return ACPMessage.notification(
            "session/update",
            {
                "sessionId": session_id,
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": error_message},
                },
            },
        )

    def _build_agent_response_notification(self, session_id: str, text: str) -> ACPMessage:
        """Построить notification с ответом агента."""
        return ACPMessage.notification(
            "session/update",
            {
                "sessionId": session_id,
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": text},
                },
            },
        )

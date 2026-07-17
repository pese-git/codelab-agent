"""ToolCallProcessor — обработка tool calls в рамках prompt-turn.

Отвечает за весь путь tool call:
- создание tool call + notification (через SessionUpdateSink);
- решение о выполнении (allow/reject/ask) через policy;
- пауза для permission / отклонение / исполнение;
- извлечение, валидация и форматирование content;
- добавление результата в историю для LLM;
- исполнение отложенного tool после permission approval.

Эмит notifications и запись в replay делегированы SessionUpdateSink.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, cast

import structlog

from codelab.server.protocol.handlers.pipeline.stages.agent_loop.loop_detector import (
    ToolLoopDetector,
)
from codelab.server.protocol.handlers.tool_policy import decide_tool_policy_async
from codelab.server.protocol.state import ToolResult
from codelab.server.tools.executors.mcp_executor import MCPToolExecutor
from codelab.server.tools.mapping import llm_name_to_acp_name

if TYPE_CHECKING:
    from codelab.server.mcp.manager import MCPManager
    from codelab.server.protocol.content.extractor import ContentExtractor, ExtractedContent
    from codelab.server.protocol.content.formatter import ContentFormatter
    from codelab.server.protocol.content.validator import ContentValidator
    from codelab.server.protocol.handlers.global_policy_manager import GlobalPolicyManager
    from codelab.server.protocol.handlers.permission_manager import PermissionManager
    from codelab.server.protocol.handlers.pipeline.stages.agent_loop.updates import (
        SessionUpdateSink,
    )
    from codelab.server.protocol.handlers.plan_builder import PlanBuilder
    from codelab.server.protocol.handlers.tool_call_handler import ToolCallHandler
    from codelab.server.protocol.state import SessionState
    from codelab.server.tools.base import ToolRegistry

logger = structlog.get_logger()


@dataclass
class ToolProcessingResult:
    """Результат обработки tool calls.

    Attributes:
        tool_results: Список результатов выполнения tools.
        pending_permission: True если требуется permission.
        pending_tool_calls: Список tool_call_id ожидающих permission.
    """

    tool_results: list[ToolResult] = field(default_factory=list)
    pending_permission: bool = False
    pending_tool_calls: list[str] = field(default_factory=list)


@dataclass
class _ToolCallStep:
    """Результат обработки одного tool call внутри цикла.

    Attributes:
        tool_result: Результат исполнения (добавляется в общий список); None,
            если tool_call пропущен (без имени).
        pause_tool_call_id: Если задан — цикл ставится на паузу для permission
            по этому tool_call_id.
    """

    tool_result: ToolResult | None = None
    pause_tool_call_id: str | None = None


class ToolCallProcessor:
    """Обработчик tool calls: policy → исполнение → content → история."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        tool_call_handler: ToolCallHandler,
        permission_manager: PermissionManager,
        content_extractor: ContentExtractor,
        content_validator: ContentValidator,
        content_formatter: ContentFormatter,
        plan_builder: PlanBuilder,
        global_policy_manager: GlobalPolicyManager | None = None,
        loop_guard_limit: int = 3,
    ) -> None:
        self._tool_registry = tool_registry
        self._tool_call_handler = tool_call_handler
        self._permission_manager = permission_manager
        self._content_extractor = content_extractor
        self._content_validator = content_validator
        self._content_formatter = content_formatter
        self._plan_builder = plan_builder
        self._global_policy_manager = global_policy_manager

        # Детектор зацикливания агента (tech-debt #22). Экземпляр процессора живёт
        # один prompt-turn, поэтому детектор создаётся здесь и его состояние
        # автоматически сбрасывается сменой turn. `loop_guard_limit=0` отключает.
        self._loop_detector = ToolLoopDetector(loop_guard_limit)

    async def process_batch(
        self,
        session: SessionState,
        session_id: str,
        tool_calls: list,
        sink: SessionUpdateSink,
        mcp_manager: MCPManager | None,
    ) -> ToolProcessingResult:
        """Обработать tool calls из ответа LLM.

        Итерирует по tool calls, делегируя обработку каждого в
        `_process_single_tool_call`. Прерывается на отмене или при запросе
        permission (agent loop ставится на паузу до ответа клиента).

        Args:
            session: Состояние сессии.
            session_id: ID сессии.
            tool_calls: Список tool calls из ответа LLM.
            sink: Канал доставки notifications (+ replay).
            mcp_manager: MCP manager.

        Returns:
            ToolProcessingResult с результатами обработки.
        """
        tool_results: list[ToolResult] = []

        for tool_call in tool_calls:
            if self._is_cancel_requested(session):
                logger.debug("tool processing cancelled", session_id=session_id)
                return ToolProcessingResult(
                    tool_results=tool_results,
                    pending_permission=False,
                )

            step = await self._process_single_tool_call(
                session, session_id, tool_call, sink, mcp_manager
            )
            if step.pause_tool_call_id is not None:
                return ToolProcessingResult(
                    tool_results=tool_results,
                    pending_permission=True,
                    pending_tool_calls=[step.pause_tool_call_id],
                )
            if step.tool_result is not None:
                tool_results.append(step.tool_result)

        return ToolProcessingResult(tool_results=tool_results)

    async def _process_single_tool_call(
        self,
        session: SessionState,
        session_id: str,
        tool_call: object,
        sink: SessionUpdateSink,
        mcp_manager: MCPManager | None,
    ) -> _ToolCallStep:
        """Обработать один tool call: создать, принять решение, исполнить.

        Возвращает `_ToolCallStep`, сигнализирующий вызывающему циклу: либо
        готовый `ToolResult` (продолжить), либо паузу для permission.
        """
        tool_name = getattr(tool_call, "name", None)
        tool_arguments = getattr(tool_call, "arguments", {})
        tool_call_id_from_llm = getattr(tool_call, "id", None)

        if not tool_name:
            logger.warning("tool_call has no name", session_id=session_id)
            return _ToolCallStep()

        # Конвертируем LLM имя обратно в ACP формат
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

        logger.info(
            "tool_call_created",
            session_id=session_id,
            tool_call_id=tool_call_id,
            tool_name=acp_tool_name,
            tool_kind=tool_kind,
            is_mcp=is_mcp,
        )

        tool_call_notification = self._tool_call_handler.build_tool_call_notification(
            session_id=session_id,
            tool_call_id=tool_call_id,
            title=acp_tool_name,
            kind=tool_kind,
        )
        await sink.emit_and_save_tool_call(
            tool_call_notification,
            session=session,
            tool_call_id=tool_call_id,
            title=acp_tool_name,
            kind=tool_kind,
            status="pending",
        )

        logger.info(
            "tool_call_deciding_execution",
            session_id=session_id,
            tool_call_id=tool_call_id,
            tool_name=acp_tool_name,
            tool_kind=tool_kind,
            is_mcp=is_mcp,
        )

        # Неизвестный (галлюцинированный) tool отклоняем ДО permission (#21):
        # иначе промах реестра всплывал бы только в _run_tool после одобрения.
        if tool_definition is None and not is_mcp:
            return _ToolCallStep(
                tool_result=await self._reject_unknown_tool(
                    session,
                    session_id,
                    tool_call_id,
                    acp_tool_name,
                    tool_call_id_from_llm,
                    sink,
                )
            )

        # Детектор зацикливания (#22): считаем попытку; если одна и та же команда
        # (tool+args) запрошена > лимита раз за turn — отклоняем ДО permission/исполнения
        # с подсказкой, вместо очередного холостого повтора.
        if self._loop_detector.register_attempt(acp_tool_name, tool_arguments):
            return _ToolCallStep(
                tool_result=await self._reject_looping_tool(
                    session,
                    session_id,
                    tool_call_id,
                    acp_tool_name,
                    tool_arguments,
                    tool_call_id_from_llm,
                    sink,
                )
            )

        # MCP инструменты всегда требуют разрешения (по умолчанию)
        if is_mcp:
            decision = await self._decide_tool_execution(session, tool_kind)
        elif tool_definition is not None and not tool_definition.requires_permission:
            decision = "allow"
        else:
            decision = await self._decide_tool_execution(session, tool_kind)

        logger.info(
            "tool_execution_decision",
            session_id=session_id,
            tool_call_id=tool_call_id,
            tool_name=acp_tool_name,
            tool_kind=tool_kind,
            is_mcp=is_mcp,
            requires_permission=(tool_definition.requires_permission if tool_definition else None),
            mode=session.config_values.get("mode", "standard"),
            decision=decision,
        )

        if decision == "ask":
            self._pause_for_permission(
                session, session_id, tool_call_id, acp_tool_name, tool_kind, sink
            )
            return _ToolCallStep(pause_tool_call_id=tool_call_id)

        if decision == "reject":
            return _ToolCallStep(
                tool_result=await self._reject_tool_call(
                    session,
                    session_id,
                    tool_call_id,
                    acp_tool_name,
                    tool_kind,
                    tool_call_id_from_llm,
                    sink,
                )
            )

        # decision == "allow"
        return _ToolCallStep(
            tool_result=await self._execute_allowed_tool_call(
                session,
                session_id,
                tool_call_id,
                tool_name,
                acp_tool_name,
                tool_arguments,
                tool_call_id_from_llm,
                is_mcp,
                mcp_manager,
                sink,
            )
        )

    def _pause_for_permission(
        self,
        session: SessionState,
        session_id: str,
        tool_call_id: str,
        acp_tool_name: str,
        tool_kind: str,
        sink: SessionUpdateSink,
    ) -> None:
        """Сформировать permission request и перевести turn в awaiting_permission."""
        tool_call_state = session.tool_calls.get(tool_call_id)
        if tool_call_state is not None:
            permission_msg = self._permission_manager.build_permission_request(
                session,
                session_id,
                tool_call_state.tool_call_id,
                tool_call_state.title,
                tool_kind,
            )
            sink.buffer_only(permission_msg)
            # НЕ отправляем permission request через immediate callback.
            # Он будет отправлен через стандартный механизм outcome.notifications
            # чтобы избежать дублирования и корректной обработки ответа.

            if session.active_turn:
                session.active_turn.phase = "awaiting_permission"
                session.active_turn.permission_tool_call_id = tool_call_id

        logger.info(
            "permission_request_sent_pausing_agent_loop",
            session_id=session_id,
            tool_call_id=tool_call_id,
            tool_name=acp_tool_name,
        )

    async def _reject_tool_call(
        self,
        session: SessionState,
        session_id: str,
        tool_call_id: str,
        acp_tool_name: str,
        tool_kind: str,
        tool_call_id_from_llm: str | None,
        sink: SessionUpdateSink,
    ) -> ToolResult:
        """Отклонить tool call по policy: пометить failed и вернуть ToolResult."""
        logger.info(
            "tool_call_rejected",
            session_id=session_id,
            tool_call_id=tool_call_id,
            tool_name=acp_tool_name,
            tool_kind=tool_kind,
        )
        self._tool_call_handler.update_tool_call_status(session, tool_call_id, "failed")
        rejection_msg = f"Tool execution rejected by policy for {tool_kind}"
        rejection_content = [
            {"type": "content", "content": {"type": "text", "text": rejection_msg}}
        ]
        rejection_notification = self._tool_call_handler.build_tool_update_notification(
            session_id=session_id,
            tool_call_id=tool_call_id,
            status="failed",
            content=rejection_content,
        )
        await sink.emit_and_save_tool_update(
            rejection_notification,
            session=session,
            tool_call_id=tool_call_id,
            status="failed",
            content=rejection_content,
        )
        return ToolResult(
            tool_call_id=tool_call_id_from_llm or tool_call_id,
            tool_name=acp_tool_name,
            success=False,
            error=rejection_msg,
        )

    async def _reject_unknown_tool(
        self,
        session: SessionState,
        session_id: str,
        tool_call_id: str,
        acp_tool_name: str,
        tool_call_id_from_llm: str | None,
        sink: SessionUpdateSink,
    ) -> ToolResult:
        """Отклонить неизвестный (галлюцинированный) tool ДО permission (#21).

        Инструмент отсутствует в реестре и не является MCP-инструментом. Возвращаем
        LLM явный failed со списком доступных инструментов, чтобы модель могла
        скорректировать вызов, — без холостого permission-запроса на несуществующий tool.
        """
        available = sorted(tool.name for tool in self._tool_registry.list_tools())
        logger.error(
            "tool not found in registry",
            session_id=session_id,
            tool_call_id=tool_call_id,
            acp_tool_name=acp_tool_name,
            registered_tools=available,
        )
        error_msg = (
            f"Неизвестный инструмент '{acp_tool_name}'. "
            f"Доступные инструменты: {', '.join(available) if available else 'нет'}."
        )
        error_content = [{"type": "content", "content": {"type": "text", "text": error_msg}}]
        self._tool_call_handler.update_tool_call_status(session, tool_call_id, "failed")
        notification = self._tool_call_handler.build_tool_update_notification(
            session_id=session_id,
            tool_call_id=tool_call_id,
            status="failed",
            content=error_content,
        )
        await sink.emit_and_save_tool_update(
            notification,
            session=session,
            tool_call_id=tool_call_id,
            status="failed",
            content=error_content,
        )
        return ToolResult(
            tool_call_id=tool_call_id_from_llm or tool_call_id,
            tool_name=acp_tool_name,
            success=False,
            error=error_msg,
        )

    async def _reject_looping_tool(
        self,
        session: SessionState,
        session_id: str,
        tool_call_id: str,
        acp_tool_name: str,
        tool_arguments: dict,
        tool_call_id_from_llm: str | None,
        sink: SessionUpdateSink,
    ) -> ToolResult:
        """Отклонить зациклившийся tool-call с подсказкой LLM (#22).

        Не исполняет tool повторно и не запрашивает permission; возвращает
        предыдущий результат и просит изменить подход или завершить.
        """
        repeat_count = self._loop_detector.repeat_count(acp_tool_name, tool_arguments)
        logger.warning(
            "tool_call_loop_detected",
            session_id=session_id,
            tool_call_id=tool_call_id,
            acp_tool_name=acp_tool_name,
            repeat_count=repeat_count,
            limit=self._loop_detector.limit,
        )
        preview = self._loop_detector.last_output(acp_tool_name, tool_arguments).strip()
        if len(preview) > 500:
            preview = preview[:500] + "…"
        error_msg = (
            f"Инструмент '{acp_tool_name}' вызван {repeat_count} раз(а) с теми же аргументами "
            f"за один ответ — повтор не продвигает задачу. "
            f"Предыдущий результат: {preview or '(пусто)'}. "
            f"Измени подход (другой инструмент/аргументы) или заверши ответ, не повторяя вызов."
        )
        error_content = [{"type": "content", "content": {"type": "text", "text": error_msg}}]
        self._tool_call_handler.update_tool_call_status(session, tool_call_id, "failed")
        notification = self._tool_call_handler.build_tool_update_notification(
            session_id=session_id,
            tool_call_id=tool_call_id,
            status="failed",
            content=error_content,
        )
        await sink.emit_and_save_tool_update(
            notification,
            session=session,
            tool_call_id=tool_call_id,
            status="failed",
            content=error_content,
        )
        return ToolResult(
            tool_call_id=tool_call_id_from_llm or tool_call_id,
            tool_name=acp_tool_name,
            success=False,
            error=error_msg,
        )

    async def _execute_allowed_tool_call(
        self,
        session: SessionState,
        session_id: str,
        tool_call_id: str,
        tool_name: str,
        acp_tool_name: str,
        tool_arguments: dict,
        tool_call_id_from_llm: str | None,
        is_mcp: bool,
        mcp_manager: MCPManager | None,
        sink: SessionUpdateSink,
    ) -> ToolResult:
        """Исполнить разрешённый tool call и сформировать ToolResult."""
        logger.info(
            "tool_call_executing",
            session_id=session_id,
            tool_call_id=tool_call_id,
            tool_name=acp_tool_name,
            is_mcp=is_mcp,
        )
        effective_id = tool_call_id_from_llm or tool_call_id
        try:
            self._tool_call_handler.update_tool_call_status(session, tool_call_id, "in_progress")
            in_progress_notification = self._tool_call_handler.build_tool_update_notification(
                session_id=session_id,
                tool_call_id=tool_call_id,
                status="in_progress",
            )
            await sink.emit_and_save_tool_update(
                in_progress_notification,
                session=session,
                tool_call_id=tool_call_id,
                status="in_progress",
            )

            result = await self._run_tool(
                session, session_id, acp_tool_name, tool_arguments, is_mcp, mcp_manager
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

            self._store_and_format(session, tool_call_id, extracted_content)

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
                self._tool_call_handler.update_tool_call_status(session, tool_call_id, "failed")
                status = "failed"

            notification_content = self._build_notification_content(extracted_content, result)

            tool_update_notification = self._tool_call_handler.build_tool_update_notification(
                session_id=session_id,
                tool_call_id=tool_call_id,
                status=status,
                content=notification_content,
            )
            await sink.emit_and_save_tool_update(
                tool_update_notification,
                session=session,
                tool_call_id=tool_call_id,
                status=status,
                content=notification_content,
            )

            # Добавляем tool result в историю для LLM
            self._add_tool_result_to_history(
                session,
                effective_id,
                result.success,
                result.output,
                result.error,
            )

            await self._emit_plan_notification_if_needed(
                session, session_id, acp_tool_name, result, sink
            )

            return ToolResult(
                tool_call_id=effective_id,
                tool_name=acp_tool_name,
                success=result.success,
                output=result.output,
                content=extracted_content.content_items,
                error=result.error,
            )

        except Exception as e:
            logger.error(
                "tool execution failed",
                session_id=session_id,
                tool_name=tool_name,
                error=str(e),
            )
            self._tool_call_handler.update_tool_call_status(session, tool_call_id, "failed")
            # P2-25: доставляем failed-статус немедленно (как success-ветка выше), а не
            # только в буфер. Иначе в стриминге карточка tool'а висит «в процессе» до
            # конца turn'а и порядок живых событий может нарушиться. emit() безопасен в
            # except: _send_immediately сам ловит свои ошибки и падает в буфер.
            await sink.emit_and_save_tool_update(
                self._tool_call_handler.build_tool_update_notification(
                    session_id=session_id,
                    tool_call_id=tool_call_id,
                    status="failed",
                ),
                session=session,
                tool_call_id=tool_call_id,
                status="failed",
            )
            self._add_tool_result_to_history(
                session,
                effective_id,
                False,
                None,
                str(e),
            )
            return ToolResult(
                tool_call_id=effective_id,
                tool_name=acp_tool_name,
                success=False,
                error=str(e),
            )

    async def execute_pending(
        self,
        session: SessionState,
        session_id: str,
        tool_call_id: str,
        mcp_manager: MCPManager | None,
    ) -> ToolResult | None:
        """Выполнить pending tool после permission approval.

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

        effective_id = tool_call_id_from_llm or tool_call_id
        try:
            result = await self._run_tool(
                session,
                session_id,
                tool_name,
                tool_arguments,
                MCPToolExecutor.is_mcp_tool(tool_name),
                mcp_manager,
            )

            extracted_content = await self._content_extractor.extract_from_result(
                tool_call_id, result
            )
            self._store_and_format(session, tool_call_id, extracted_content)

            notification_content = self._build_notification_content(extracted_content, result)

            if result.success:
                self._tool_call_handler.update_tool_call_status(
                    session, tool_call_id, "completed", content=notification_content
                )
                # Добавляем tool result в историю для LLM
                self._add_tool_result_to_history(
                    session, effective_id, True, result.output, None
                )
                return ToolResult(
                    tool_call_id=effective_id,
                    tool_name=tool_name,
                    success=True,
                    output=result.output,
                    content=extracted_content.content_items,
                )
            else:
                # Неуспех (напр. ненулевой exit code команды) НЕ должен терять output:
                # для `flutter analyze` именно output содержит список проблем (#terminal-result).
                failure_content = notification_content or [
                    {
                        "type": "content",
                        "content": {
                            "type": "text",
                            "text": result.output or result.error or "Tool execution failed",
                        },
                    }
                ]
                self._tool_call_handler.update_tool_call_status(
                    session, tool_call_id, "failed", content=failure_content
                )
                # Добавляем tool result в историю для LLM (с сохранением output).
                self._add_tool_result_to_history(
                    session, effective_id, False, result.output, result.error
                )
                return ToolResult(
                    tool_call_id=effective_id,
                    tool_name=tool_name,
                    success=False,
                    output=result.output,
                    error=result.error,
                    content=extracted_content.content_items,
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
            self._add_tool_result_to_history(session, effective_id, False, None, str(exc))
            return ToolResult(
                tool_call_id=effective_id,
                tool_name=tool_name,
                success=False,
                error=str(exc),
            )

    async def _run_tool(
        self,
        session: SessionState,
        session_id: str,
        acp_tool_name: str,
        tool_arguments: dict,
        is_mcp: bool,
        mcp_manager: MCPManager | None,
    ):
        """Исполнить tool через MCP executor или локальный registry."""
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
        # Запоминаем последний вывод команды — для подсказки при блокировке (#22).
        self._loop_detector.record_output(acp_tool_name, tool_arguments, result)
        return result

    def _store_and_format(
        self,
        session: SessionState,
        tool_call_id: str,
        extracted_content: ExtractedContent,
    ) -> None:
        """Сохранить extracted content в tool_call_state и отформатировать для LLM."""
        tool_call_state = session.tool_calls.get(tool_call_id)
        if tool_call_state:
            tool_call_state.result_content = extracted_content.content_items
        provider_raw = session.config_values.get("llm_provider", "openai")
        provider = cast(Literal["openai", "anthropic"], provider_raw)
        self._content_formatter.format_for_llm(extracted_content, provider=provider)

    @staticmethod
    def _build_notification_content(extracted_content, result) -> list | None:
        """Контент для tool_call_update: extracted content с fallback на текст output.

        output отдаём и при неуспехе (ненулевой exit code команды): его текст —
        полезный результат, а не признак сбоя.
        """
        if extracted_content.content_items:
            return extracted_content.content_items
        if result.output:
            return [{"type": "content", "content": {"type": "text", "text": result.output}}]
        return None

    async def _emit_plan_notification_if_needed(
        self,
        session: SessionState,
        session_id: str,
        acp_tool_name: str,
        result,
        sink: SessionUpdateSink,
    ) -> None:
        """Отправить plan notification, если tool update_plan успешно вернул план.

        Соответствует ACP spec (protocol/11-Agent Plan.md).
        """
        if acp_tool_name != "update_plan" or not result.success:
            return
        plan_entries = result.metadata.get("validated_entries") if result.metadata else None
        if not plan_entries:
            return
        session.latest_plan = list(plan_entries)
        plan_notification = self._plan_builder.build_plan_notification(session_id, plan_entries)
        await sink.emit_and_save_plan(plan_notification, session=session, entries=plan_entries)
        logger.debug(
            "plan notification sent from update_plan tool",
            session_id=session_id,
            entries_count=len(plan_entries),
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
            output: Выход tool (в т.ч. при неуспехе — напр. вывод команды с
                ненулевым exit code).
            error: Ошибка (если есть).
        """
        if success:
            content = output or "Success"
        else:
            # Ненулевой exit code — нормальный результат с данными, а не сбой:
            # напр. `flutter analyze` возвращает список проблем в output. LLM обязан
            # его видеть, иначе не сможет исправить и будет повторять вызов.
            parts = [p for p in (output, error) if p]
            content = "\n".join(parts) if parts else "Tool execution failed"

        final_content = content or ""
        session.history.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": final_content,
            }
        )

        preview = final_content[:200].replace("\n", " ⏎ ")
        logger.info(
            "tool_result_to_history",
            session_id=session.session_id,
            tool_call_id=tool_call_id,
            success=success,
            content_len=len(final_content),
            content_preview=preview,
        )

    async def _decide_tool_execution(self, session: SessionState, tool_kind: str) -> str:
        """Определить решение о выполнении tool.

        Делегирует единой логике в ToolPolicyDecider.

        Args:
            session: Состояние сессии.
            tool_kind: Тип инструмента.

        Returns:
            "allow", "reject" или "ask".
        """
        return await decide_tool_policy_async(session, tool_kind, self._global_policy_manager)

    @staticmethod
    def _is_cancel_requested(session: SessionState) -> bool:
        """Проверить флаг отмены."""
        return session.active_turn is not None and session.active_turn.cancel_requested

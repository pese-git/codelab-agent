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
from typing import TYPE_CHECKING, Any

import structlog

from codelab.server.domain.tool_call import answer_tool_call_id
from codelab.server.protocol.handlers.pipeline.stages.agent_loop.loop_detector import (
    ToolLoopDetector,
)
from codelab.server.protocol.handlers.tool_policy import (
    decide_tool_policy_async,
    describe_rejection,
)
from codelab.server.protocol.session_commands import SessionCommands
from codelab.server.protocol.state import ToolResult
from codelab.server.protocol.turn_cancellation import TurnCancellationRegistry
from codelab.server.tools.executors.mcp_executor import MCPToolExecutor
from codelab.server.tools.mapping import llm_name_to_acp_name
from codelab.shared.content.description import describe_acp_content

if TYPE_CHECKING:
    from codelab.server.domain.session import Session
    from codelab.server.mcp.manager import MCPManager
    from codelab.server.protocol.content.extractor import ContentExtractor, ExtractedContent
    from codelab.server.protocol.content.validator import ContentValidator
    from codelab.server.protocol.handlers.global_policy_manager import GlobalPolicyManager
    from codelab.server.protocol.handlers.permission_manager import PermissionManager
    from codelab.server.protocol.handlers.pipeline.stages.agent_loop.updates import (
        SessionUpdateSink,
    )
    from codelab.server.protocol.handlers.plan_builder import PlanBuilder
    from codelab.server.protocol.handlers.tool_call_handler import ToolCallHandler
    from codelab.server.tools.base import ToolRegistry

logger = structlog.get_logger()


def _carry_executor_changes(*, source: Session, target: Session) -> None:
    """Перенести в команду изменения, сделанные исполнителями инструментов.

    ВРЕМЕННЫЙ ШОВ (ADR-006, фаза D шаг 4). Исполнители пишут состояние прямо в
    рабочую копию: счётчик alias'ов терминалов и `set_config_value` из декоратора
    структуры проекта. Своего шва команд у цепочки `tools/` пока нет — её зовут два
    вызывающих (turn и Context Manager, см. шаг 3), и порт исполнителя пришлось бы
    менять для обоих. Пока их решения переносятся сюда явно: перечень конечный и
    виден целиком.

    Связка alias → client terminalId здесь больше не переносится: она уехала в
    процессный `TerminalAliasRegistry` (ADR-007, шаг A) и от копий сессии не
    зависит. Остался счётчик — он персистится, поэтому шов ему всё ещё нужен.

    Уходит, когда исполнители получат собственные команды; до тех пор новая
    мутация в исполнителе, не перечисленная здесь, до диска не доедет.
    """
    target.runtime.terminal_counter = max(
        target.runtime.terminal_counter, source.runtime.terminal_counter
    )
    target.config.config_values.update(source.config.config_values)


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
        plan_builder: PlanBuilder,
        global_policy_manager: GlobalPolicyManager | None = None,
        loop_guard_limit: int = 3,
        turn_cancellation: TurnCancellationRegistry | None = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._tool_call_handler = tool_call_handler
        self._permission_manager = permission_manager
        self._content_extractor = content_extractor
        self._content_validator = content_validator
        self._plan_builder = plan_builder
        self._global_policy_manager = global_policy_manager

        # Детектор зацикливания агента (tech-debt #22). Экземпляр процессора живёт
        # один prompt-turn, поэтому детектор создаётся здесь и его состояние
        # автоматически сбрасывается сменой turn. `loop_guard_limit=0` отключает.
        self._loop_detector = ToolLoopDetector(loop_guard_limit)
        self._turn_cancellation = turn_cancellation

    async def process_batch(
        self,
        commands: SessionCommands,
        session_id: str,
        tool_calls: list,
        sink: SessionUpdateSink,
        mcp_manager: MCPManager | None,
        started_epoch: int | None = None,
    ) -> ToolProcessingResult:
        """Обработать tool calls из ответа LLM.

        Итерирует по tool calls, делегируя обработку каждого в
        `_process_single_tool_call`. Прерывается на отмене или при запросе
        permission (agent loop ставится на паузу до ответа клиента).

        Args:
            commands: Шов команд над сессией — единственный путь записи состояния.
            session_id: ID сессии.
            tool_calls: Список tool calls из ответа LLM.
            sink: Канал доставки notifications (+ replay).
            mcp_manager: MCP manager.
            started_epoch: Поколение отмены, с которым стартовал цикл (P0-39). `None`
                — взять текущее на входе: одиночный вызов вне цикла отменяется только
                тем, что произошло во время самого батча.

        Returns:
            ToolProcessingResult с результатами обработки.
        """
        session = commands.session
        epoch = (
            self._cancellation_generation(session_id) if started_epoch is None else started_epoch
        )
        tool_results: list[ToolResult] = []

        for index, tool_call in enumerate(tool_calls):
            if self._is_cancel_requested(session, epoch, session_id):
                logger.debug("tool processing cancelled", session_id=session_id)
                # Прерывание батча оставляло остаток вызовов без ответа: их id уже
                # лежат в assistant-сообщении истории (`loop.py`), и модель получала
                # неконсистентную историю (tech-debt P2-38).
                await self._answer_unprocessed_tool_calls(
                    commands,
                    session_id,
                    tool_calls[index:],
                    reason="turn отменён пользователем",
                )
                return ToolProcessingResult(
                    tool_results=tool_results,
                    pending_permission=False,
                )

            step = await self._process_single_tool_call(
                commands, session_id, tool_call, sink, mcp_manager
            )
            if step.pause_tool_call_id is not None:
                # Остаток батча возобновляется после разрешения, а не выбрасывается:
                # раньше модель получала «вызов не выполнялся» и перезапрашивала те
                # же файлы по кругу (P2-40). Если сохранить хвост некуда (turn'а нет),
                # честно отвечаем модели — иначе вызовы остались бы без `role: tool`.
                remaining = list(tool_calls[index + 1 :])
                if remaining and session.active_turn is not None:
                    deferred = [self._tool_call_to_dict(call) for call in remaining]

                    # Отложенный хвост обязан попасть на диск до паузы: ответ на
                    # разрешение придёт отдельным запросом и загрузит сессию заново.
                    def _defer(target: Session, tail: list = deferred) -> None:
                        if target.active_turn is not None:
                            target.active_turn.pending_batch = tail

                    await commands.require_active_turn(_defer, name="batch_deferred")
                    logger.info(
                        "tool_calls_deferred_to_resume",
                        session_id=session_id,
                        count=len(remaining),
                        paused_tool_call_id=step.pause_tool_call_id,
                    )
                else:
                    await self._answer_unprocessed_tool_calls(
                        commands,
                        session_id,
                        remaining,
                        reason="turn приостановлен на запросе разрешения, "
                        "а состояние turn'а недоступно",
                    )
                return ToolProcessingResult(
                    tool_results=tool_results,
                    pending_permission=True,
                    pending_tool_calls=[step.pause_tool_call_id],
                )
            if step.tool_result is not None:
                tool_results.append(step.tool_result)

        return ToolProcessingResult(tool_results=tool_results)

    @staticmethod
    def _tool_call_to_dict(tool_call: Any) -> dict[str, Any]:
        """Свести tool call к сериализуемой форме для `pending_batch`.

        `pending_batch` уезжает на диск вместе с сессией, поэтому объект
        LLM-адаптера туда положить нельзя.
        """
        return {
            "id": getattr(tool_call, "id", None),
            "name": getattr(tool_call, "name", None),
            "arguments": getattr(tool_call, "arguments", None) or {},
        }

    async def _answer_unprocessed_tool_calls(
        self,
        commands: SessionCommands,
        session_id: str,
        tool_calls: list,
        *,
        reason: str,
    ) -> None:
        """Ответить модели на вызовы батча, которые выполнены не будут.

        `loop.py` кладёт в историю assistant-сообщение со ВСЕМИ вызовами батча до
        их обработки, а обработка прерывается на паузе permission и на отмене.
        Без этих ответов история нарушала контракт LLM-API (`role: tool` на каждый
        `tool_call_id`), и модель повторяла вызовы — тот же дефект, что P2-36, но по
        другому каналу.

        Ответ правдивый: вызов НЕ выполнялся, и если он всё ещё нужен, модель должна
        запросить его снова. Переписывать assistant-сообщение задним числом нельзя —
        модель действительно эти вызовы запрашивала.
        """
        if not tool_calls:
            return

        answers: list[str] = [
            str(tool_call_id)
            for tool_call_id in (getattr(tool_call, "id", None) for tool_call in tool_calls)
            if tool_call_id
        ]
        if not answers:
            return

        # Ответы на неисполненные вызовы — одна команда: они описывают одно решение
        # («батч дальше не идёт»), и частично записанный набор оставил бы часть
        # вызовов без `role: tool` — ровно то, что здесь и лечится (P2-38).
        def _answer(target: Session) -> None:
            for tool_call_id_from_llm in answers:
                self._add_tool_result_to_history(
                    target,
                    tool_call_id_from_llm,
                    False,
                    None,
                    f"Вызов не выполнялся: {reason}. Запроси его снова, если он всё ещё нужен.",
                )

        await commands.apply(_answer, name="unprocessed_tool_calls_answered")
        answered = len(answers)

        logger.info(
            "tool_calls_left_unprocessed",
            session_id=session_id,
            count=answered,
            reason=reason,
        )

    async def _answer_nameless_tool_call(
        self,
        commands: SessionCommands,
        session_id: str,
        tool_call_id_from_llm: str | None,
    ) -> None:
        """Ответить модели на вызов без имени инструмента.

        Ответ обязателен и здесь: иначе вызов остаётся без `role: tool` (P2-38).
        """
        logger.warning("tool_call has no name", session_id=session_id)
        if not tool_call_id_from_llm:
            return
        await commands.apply(
            lambda target: self._add_tool_result_to_history(
                target,
                tool_call_id_from_llm,
                False,
                None,
                "Вызов не выполнялся: в запросе не указано имя инструмента.",
            ),
            name="nameless_tool_call_answered",
        )

    async def _process_single_tool_call(
        self,
        commands: SessionCommands,
        session_id: str,
        tool_call: object,
        sink: SessionUpdateSink,
        mcp_manager: MCPManager | None,
    ) -> _ToolCallStep:
        """Обработать один tool call: создать, принять решение, исполнить.

        Возвращает `_ToolCallStep`, сигнализирующий вызывающему циклу: либо
        готовый `ToolResult` (продолжить), либо паузу для permission.
        """
        session = commands.session
        tool_name = getattr(tool_call, "name", None)
        tool_arguments = getattr(tool_call, "arguments", {})
        tool_call_id_from_llm = getattr(tool_call, "id", None)

        if not tool_name:
            await self._answer_nameless_tool_call(commands, session_id, tool_call_id_from_llm)
            return _ToolCallStep()

        # Конвертируем LLM имя обратно в ACP формат
        acp_tool_name = llm_name_to_acp_name(tool_name)

        tool_kind = "other"
        is_mcp = MCPToolExecutor.is_mcp_tool(acp_tool_name)
        tool_definition = self._tool_registry.get(acp_tool_name)
        if tool_definition is not None:
            tool_kind = tool_definition.kind

        tool_call_id = await commands.apply(
            lambda target: self._tool_call_handler.create_tool_call(
                session=target,
                title=acp_tool_name,
                kind=tool_kind,
                tool_name=acp_tool_name,
                tool_arguments=tool_arguments,
                tool_call_id_from_llm=tool_call_id_from_llm,
            ),
            name="tool_call_created",
        )
        if tool_call_id is None:
            # Сессии больше нет — исполнять вызов некуда и некому отвечать.
            logger.warning(
                "tool_call_not_created_session_gone",
                session_id=session_id,
                tool_name=acp_tool_name,
            )
            return _ToolCallStep()

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
                    commands,
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
                    commands,
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
            mode=session.config.config_values.get("mode", "standard"),
            decision=decision,
        )

        if decision == "ask":
            await self._pause_for_permission(
                commands, session_id, tool_call_id, acp_tool_name, tool_kind, sink
            )
            return _ToolCallStep(pause_tool_call_id=tool_call_id)

        if decision == "reject":
            return _ToolCallStep(
                tool_result=await self._reject_tool_call(
                    commands,
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
                commands,
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

    async def _pause_for_permission(
        self,
        commands: SessionCommands,
        session_id: str,
        tool_call_id: str,
        acp_tool_name: str,
        tool_kind: str,
        sink: SessionUpdateSink,
    ) -> None:
        """Сформировать permission request и перевести turn в awaiting_permission."""
        session = commands.session
        tool_call_state = session.tool_calls.get(tool_call_id)
        if tool_call_state is not None:
            # Заведение запроса разрешения и пауза turn'а — одна команда: ответ на
            # разрешение придёт отдельным запросом и найдёт сессию по
            # `permission_request_id`, поэтому оба поля обязаны лечь на диск вместе.
            def _pause(target: Session) -> None:
                permission_msg = self._permission_manager.build_permission_request(
                    target,
                    session_id,
                    tool_call_state.id,
                    tool_call_state.title or "",
                    tool_kind,
                )
                sink.buffer_only(permission_msg)
                # НЕ отправляем permission request через immediate callback.
                # Он будет отправлен через стандартный механизм outcome.notifications
                # чтобы избежать дублирования и корректной обработки ответа.
                if target.active_turn:
                    target.active_turn.phase = "awaiting_permission"
                    target.active_turn.permission_tool_call_id = tool_call_id

            await commands.require_active_turn(_pause, name="permission_requested")

        logger.info(
            "permission_request_sent_pausing_agent_loop",
            session_id=session_id,
            tool_call_id=tool_call_id,
            tool_name=acp_tool_name,
            # Без id запроса лог не сшивается: `permission_response_applied` и
            # `session_loaded_with_orphaned_permission_request` называют запрос
            # идентификатором, а пауза — только вызовом. Из-за этого различить
            # «процесс умер на реальной паузе» от «идентификатор не сняли»
            # приходилось покадровым снимком файла сессии (P2-46).
            permission_request_id=(
                session.active_turn.permission_request_id if session.active_turn else None
            ),
        )

    async def _reject_tool_call(
        self,
        commands: SessionCommands,
        session_id: str,
        tool_call_id: str,
        acp_tool_name: str,
        tool_kind: str,
        tool_call_id_from_llm: str | None,
        sink: SessionUpdateSink,
    ) -> ToolResult:
        """Отклонить tool call по policy: пометить failed и вернуть ToolResult."""
        session = commands.session
        rejection_reason = describe_rejection(session, tool_kind)
        logger.info(
            "tool_call_rejected",
            session_id=session_id,
            tool_call_id=tool_call_id,
            tool_name=acp_tool_name,
            tool_kind=tool_kind,
            mode=session.get_config_value("mode", "standard"),
            reason=rejection_reason,
        )
        rejection_msg = f"Инструмент '{acp_tool_name}' не выполнен. {rejection_reason}"
        rejection_content = [
            {"type": "content", "content": {"type": "text", "text": rejection_msg}}
        ]

        await self._fail_tool_call(
            commands,
            tool_call_id=tool_call_id,
            answer_tool_call_id=answer_tool_call_id(tool_call_id_from_llm, tool_call_id),
            message=rejection_msg,
        )

        rejection_notification = self._tool_call_handler.build_tool_update_notification(
            session_id=session_id,
            tool_call_id=tool_call_id,
            status="failed",
            content=rejection_content,
        )
        await sink.emit_and_save_tool_update(
            rejection_notification,
            tool_call_id=tool_call_id,
            status="failed",
            content=rejection_content,
        )
        return ToolResult(
            tool_call_id=answer_tool_call_id(tool_call_id_from_llm, tool_call_id),
            tool_name=acp_tool_name,
            success=False,
            error=rejection_msg,
        )

    async def _fail_tool_call(
        self,
        commands: SessionCommands,
        *,
        tool_call_id: str,
        answer_tool_call_id: str,
        message: str,
    ) -> None:
        """Пометить вызов failed и ответить модели — одной командой.

        Статус вызова и ответ модели описывают одно решение: ACP `05-Prompt Turn`
        шаг 6 требует отдать результат модели, а контракт LLM-API — `role: tool` на
        каждый `tool_call_id`. Разрыв по транзакциям дал бы вызов без ответа, и
        модель повторяла бы его до упора в `max_turn_requests` (P2-36).
        """

        def _fail(target: Session) -> None:
            self._tool_call_handler.update_tool_call_status(target, tool_call_id, "failed")
            self._add_tool_result_to_history(target, answer_tool_call_id, False, None, message)

        await commands.apply(_fail, name="tool_call_failed")

    async def _reject_unknown_tool(
        self,
        commands: SessionCommands,
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
        # warning: несуществующий инструмент — галлюцинация модели, а не сбой сервера;
        # список доступных уходит модели в ответе (tech-debt P2-37).
        logger.warning(
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
        # Список доступных инструментов нужен модели, а не только клиенту.
        await self._fail_tool_call(
            commands,
            tool_call_id=tool_call_id,
            answer_tool_call_id=answer_tool_call_id(tool_call_id_from_llm, tool_call_id),
            message=error_msg,
        )
        notification = self._tool_call_handler.build_tool_update_notification(
            session_id=session_id,
            tool_call_id=tool_call_id,
            status="failed",
            content=error_content,
        )
        await sink.emit_and_save_tool_update(
            notification,
            tool_call_id=tool_call_id,
            status="failed",
            content=error_content,
        )
        return ToolResult(
            tool_call_id=answer_tool_call_id(tool_call_id_from_llm, tool_call_id),
            tool_name=acp_tool_name,
            success=False,
            error=error_msg,
        )

    async def _reject_looping_tool(
        self,
        commands: SessionCommands,
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
        # Подсказка про повтор бесполезна, если не доходит до модели.
        await self._fail_tool_call(
            commands,
            tool_call_id=tool_call_id,
            answer_tool_call_id=answer_tool_call_id(tool_call_id_from_llm, tool_call_id),
            message=error_msg,
        )
        notification = self._tool_call_handler.build_tool_update_notification(
            session_id=session_id,
            tool_call_id=tool_call_id,
            status="failed",
            content=error_content,
        )
        await sink.emit_and_save_tool_update(
            notification,
            tool_call_id=tool_call_id,
            status="failed",
            content=error_content,
        )
        return ToolResult(
            tool_call_id=answer_tool_call_id(tool_call_id_from_llm, tool_call_id),
            tool_name=acp_tool_name,
            success=False,
            error=error_msg,
        )

    async def _execute_allowed_tool_call(
        self,
        commands: SessionCommands,
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
        session = commands.session
        logger.info(
            "tool_call_executing",
            session_id=session_id,
            tool_call_id=tool_call_id,
            tool_name=acp_tool_name,
            is_mcp=is_mcp,
        )
        effective_id = answer_tool_call_id(tool_call_id_from_llm, tool_call_id)
        try:
            await commands.apply(
                lambda target: self._tool_call_handler.update_tool_call_status(
                    target, tool_call_id, "in_progress"
                ),
                name="tool_call_in_progress",
            )
            in_progress_notification = self._tool_call_handler.build_tool_update_notification(
                session_id=session_id,
                tool_call_id=tool_call_id,
                status="in_progress",
            )
            await sink.emit_and_save_tool_update(
                in_progress_notification,
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

            if result.success:
                success_text = result.output or "Success"
                success_content: list[dict[str, Any]] | None = [
                    {"type": "content", "content": {"type": "text", "text": success_text}}
                ]
                status = "completed"
            else:
                # Отмена пользователем — не сбой инструмента (P2-50)
                success_content = None
                status = "cancelled" if result.cancelled else "failed"

            # Итог вызова — одна команда: содержимое, статус и ответ модели
            # описывают один результат.
            def _commit_result(target: Session) -> None:
                _carry_executor_changes(source=session, target=target)
                self._tool_call_handler.update_tool_call_status(
                    target, tool_call_id, status, content=success_content
                )
                self._add_tool_result_to_history(
                    target,
                    effective_id,
                    result.success,
                    result.output,
                    result.error,
                    extracted_content=extracted_content,
                )

            await commands.apply(_commit_result, name="tool_call_result")

            notification_content = self._build_notification_content(extracted_content, result)

            tool_update_notification = self._tool_call_handler.build_tool_update_notification(
                session_id=session_id,
                tool_call_id=tool_call_id,
                status=status,
                content=notification_content,
            )
            await sink.emit_and_save_tool_update(
                tool_update_notification,
                tool_call_id=tool_call_id,
                status=status,
                content=notification_content,
            )

            await self._emit_plan_notification_if_needed(session_id, acp_tool_name, result, sink)

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
            await self._fail_tool_call(
                commands,
                tool_call_id=tool_call_id,
                answer_tool_call_id=effective_id,
                message=str(e),
            )
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
                tool_call_id=tool_call_id,
                status="failed",
            )
            return ToolResult(
                tool_call_id=effective_id,
                tool_name=acp_tool_name,
                success=False,
                error=str(e),
            )

    async def execute_pending(
        self,
        commands: SessionCommands,
        session_id: str,
        tool_call_id: str,
        mcp_manager: MCPManager | None,
    ) -> ToolResult | None:
        """Выполнить pending tool после permission approval.

        Args:
            commands: Шов команд над сессией — единственный путь записи состояния.
            session_id: ID сессии.
            tool_call_id: ID tool call для выполнения.
            mcp_manager: MCP manager.

        Returns:
            ToolResult или None если tool не найден.
        """
        session = commands.session
        tool_call_state = session.tool_calls.get(tool_call_id)
        if tool_call_state is None:
            logger.error(
                "tool_call_state not found for pending execution",
                session_id=session_id,
                tool_call_id=tool_call_id,
            )
            return None

        tool_name = tool_call_state.tool_name
        tool_arguments = tool_call_state.arguments
        tool_call_id_from_llm = tool_call_state.tool_call_id_from_llm

        if not tool_name:
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

        effective_id = answer_tool_call_id(tool_call_id_from_llm, tool_call_id)
        # Матрица переходов допускает completed только из in_progress, поэтому
        # resume-путь обязан отметить запуск так же, как обычный (_execute_allowed_tool).
        # Без этого completed молча отбрасывается и состояние застревает в pending.
        await commands.apply(
            lambda target: self._tool_call_handler.update_tool_call_status(
                target, tool_call_id, "in_progress"
            ),
            name="pending_tool_in_progress",
        )
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
            notification_content = self._build_notification_content(extracted_content, result)

            if result.success:
                await self._commit_pending_result(
                    commands,
                    session=session,
                    tool_call_id=tool_call_id,
                    extracted_content=extracted_content,
                    status="completed",
                    content=notification_content,
                    answer_tool_call_id=effective_id,
                    success=True,
                    output=result.output,
                    error=None,
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
                await self._commit_pending_result(
                    commands,
                    session=session,
                    tool_call_id=tool_call_id,
                    extracted_content=extracted_content,
                    # Отмена пользователем — не сбой инструмента (P2-50)
                    status="cancelled" if result.cancelled else "failed",
                    content=failure_content,
                    answer_tool_call_id=effective_id,
                    success=False,
                    output=result.output,
                    error=result.error,
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
            error_text = str(exc)
            error_content = [
                {
                    "type": "content",
                    "content": {"type": "text", "text": f"Tool execution error: {error_text}"},
                }
            ]

            def _fail(target: Session) -> None:
                _carry_executor_changes(source=session, target=target)
                self._tool_call_handler.update_tool_call_status(
                    target, tool_call_id, "failed", content=error_content
                )
                self._add_tool_result_to_history(target, effective_id, False, None, error_text)

            await commands.apply(_fail, name="pending_tool_failed")
            return ToolResult(
                tool_call_id=effective_id,
                tool_name=tool_name,
                success=False,
                error=str(exc),
            )

    async def _commit_pending_result(
        self,
        commands: SessionCommands,
        *,
        session: Session,
        tool_call_id: str,
        extracted_content: ExtractedContent,
        status: str,
        content: list | None,
        answer_tool_call_id: str,
        success: bool,
        output: str | None,
        error: str | None,
    ) -> None:
        """Итог приостановленного вызова — одной командой (см. `_fail_tool_call`)."""

        def _commit(target: Session) -> None:
            _carry_executor_changes(source=session, target=target)
            self._tool_call_handler.update_tool_call_status(
                target, tool_call_id, status, content=content
            )
            self._add_tool_result_to_history(
                target,
                answer_tool_call_id,
                success,
                output,
                error,
                extracted_content=extracted_content,
            )

        await commands.apply(_commit, name="pending_tool_result")

    async def _run_tool(
        self,
        session: Session,
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

    # Типы ACP-блоков, чьё содержимое **невозможно** передать текстом `output` исполнителя,
    # поэтому о них модели надо сказать отдельно. Остальные исключены осознанно:
    #   * `text` и ACP-конверт `content` — их текст уже в `output`;
    #   * `terminal` — клиентский дескриптор, а alias для модели уже назван в `output`;
    #   * `diff` — на путь `extracted_content` не приходит (его производит завершение
    #     клиентского RPC), а дописывание полного diff'а раздуло бы payload.
    _BLOCKS_ABSENT_FROM_OUTPUT = frozenset({"image", "audio", "embedded", "resource_link"})

    def _describe_blocks_absent_from_output(
        self,
        extracted_content: ExtractedContent | None,
    ) -> str | None:
        """Описание блоков, которых нет в текстовом `output` (`None` — таких блоков нет).

        Закрывает тихую потерю: нетекстовый результат исчезал бесследно, и модель получала
        `"Success"` (change `multimodal-tool-results`, такт 1). Описание — не данные;
        доставка данных идёт за шагом C расщепления.

        Порядок блоков сохраняется: он часть содержимого.
        """
        if extracted_content is None:
            return None

        untold = [
            item
            for item in extracted_content.content_items
            if isinstance(item, dict) and item.get("type") in self._BLOCKS_ABSENT_FROM_OUTPUT
        ]
        if not untold:
            return None

        described = describe_acp_content(untold)
        return described or None

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
        # latest_plan пишет sink.emit_and_save_plan (единый писатель, dual-carry — D4-b/b1).
        plan_notification = self._plan_builder.build_plan_notification(session_id, plan_entries)
        await sink.emit_and_save_plan(plan_notification, entries=plan_entries)
        logger.debug(
            "plan notification sent from update_plan tool",
            session_id=session_id,
            entries_count=len(plan_entries),
        )

    def _add_tool_result_to_history(
        self,
        session: Session,
        tool_call_id: str,
        success: bool,
        output: str | None,
        error: str | None,
        extracted_content: ExtractedContent | None = None,
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

        # Блоки, которых нет в текстовом `output`, дописываются описанием: иначе нетекстовый
        # результат исчезает бесследно и модель получает `"Success"` (такт 1
        # `multimodal-tool-results`). Текстовый результат этой ветки не касается — payload
        # остаётся байт-идентичным (гейт `test_tool_result_payload_golden`).
        untold = self._describe_blocks_absent_from_output(extracted_content)
        if untold:
            content = f"{content}\n\n{untold}" if content else untold

        final_content = content or ""
        # Форма записи принадлежит носителю состояния (history-seam, фаза B ADR-006):
        # тот же сейм зовут пути отмены, поэтому она одна для всех писателей.
        session.add_tool_result(tool_call_id, final_content)

        preview = final_content[:200].replace("\n", " ⏎ ")
        logger.info(
            "tool_result_to_history",
            session_id=str(session.id),
            tool_call_id=tool_call_id,
            success=success,
            content_len=len(final_content),
            content_preview=preview,
        )

    async def _decide_tool_execution(self, session: Session, tool_kind: str) -> str:
        """Определить решение о выполнении tool.

        Делегирует единой логике в ToolPolicyDecider.

        Args:
            session: Состояние сессии.
            tool_kind: Тип инструмента.

        Returns:
            "allow", "reject" или "ask".
        """
        return await decide_tool_policy_async(session, tool_kind, self._global_policy_manager)

    def _cancellation_generation(self, session_id: str) -> int:
        """Текущее поколение отмены сессии (0, если реестр не подключён)."""
        if self._turn_cancellation is None:
            return 0
        return self._turn_cancellation.generation(session_id)

    def _is_cancel_requested(
        self, session: Session, started_epoch: int, session_id: str | None = None
    ) -> bool:
        """Проверить отмену: поколение в реестре либо флаг в живом `active_turn`."""
        if session_id is not None and self._cancellation_generation(session_id) != started_epoch:
            return True
        return session.active_turn is not None and session.active_turn.cancel_requested

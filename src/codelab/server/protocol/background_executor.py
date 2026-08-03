"""BackgroundExecutor — фоновое выполнение tools и завершение turns.

Инкапсулирует логику:
- Фонового выполнения tools после permission approval
- Завершения активных turns
- Проверки возможности автозавершения turn
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import structlog

from ..mapping.session_mapper import SessionMapper
from ..messages import ACPMessage
from .handlers import prompt
from .session_commands import SessionCommands
from .state import LLMLoopResult

if TYPE_CHECKING:
    from ..mcp import MCPManager
    from ..protocol.session_runtime import SessionRuntimeRegistry
    from ..protocol.state import SessionState
    from ..storage import SessionRepository, SessionStorage
    from .handlers.prompt_orchestrator import PromptOrchestrator

logger = structlog.get_logger()


class BackgroundExecutor:
    """Управляет фоновым выполнением tools и завершением turns.

    Отвечает за:
    - Фоновое выполнение tools после permission approval
    - Завершение активных turns
    - Проверку возможности автозавершения turn

    Notifications публикуются в SessionNotificationBus, транспорт подписывается
    на bus и доставляет сообщения клиенту.

    Attributes:
        storage: Хранилище сессий.
        orchestrator_provider: Функция для получения PromptOrchestrator.
        mcp_provider: Функция для получения MCP manager для сессии.
        runtime_registry: Реестр runtime-состояний сессий.
    """

    def __init__(
        self,
        storage: SessionStorage,
        repository: SessionRepository,
        orchestrator_provider: Callable[[], Awaitable[PromptOrchestrator]],
        mcp_provider: Callable[[SessionState], Awaitable[MCPManager | None]],
        runtime_registry: SessionRuntimeRegistry,
    ) -> None:
        """Инициализирует BackgroundExecutor.

        Args:
            storage: Хранилище сессий.
            repository: Доменный порт над тем же backend — путь записи turn'а.
            orchestrator_provider: Функция для получения PromptOrchestrator.
            mcp_provider: Функция для получения MCP manager для сессии.
            runtime_registry: Реестр runtime-состояний сессий.
        """
        self._storage = storage
        self._repository = repository
        self._orchestrator_provider = orchestrator_provider
        self._mcp_provider = mcp_provider
        self._runtime_registry = runtime_registry

    async def execute_tool_in_background(
        self,
        *,
        session_id: str,
        tool_call_id: str,
    ) -> None:
        """Фоновая задача для выполнения tool после permission approval.

        Выполняет инструмент через LLMLoopStage, отправляет notifications
        и завершает turn. Вызывается из handle_and_process().

        Args:
            session_id: ID сессии.
            tool_call_id: ID tool call для выполнения.
        """
        try:
            llm_result: LLMLoopResult = await self.execute_pending_tool(
                session_id=session_id,
                tool_call_id=tool_call_id,
            )

            # Notifications уже отправлены через callback в AgentLoop
            logger.info(
                "notifications_sent_via_immediate_delivery_callback",
                session_id=session_id,
                tool_call_id=tool_call_id,
                notifications_count=len(llm_result.notifications),
            )

            # Если LLM loop снова ожидает permission — отправляем notifications и выходим
            if llm_result.pending_permission:
                # Отправить notifications (включая permission request) перед выходом
                for notification in llm_result.notifications:
                    await self._send_message(notification, session_id)
                logger.debug(
                    "llm_loop_deferred_for_permission",
                    session_id=session_id,
                    notifications_sent=len(llm_result.notifications),
                )
                return

            # Завершаем turn и отправляем финальный response
            stop_reason = llm_result.stop_reason or "end_turn"
            turn_completion = await self.complete_active_turn(session_id, stop_reason=stop_reason)
            if turn_completion is not None:
                await self._send_message(turn_completion, session_id)
                logger.debug(
                    "turn_completion_sent_after_llm_loop",
                    session_id=session_id,
                    stop_reason=stop_reason,
                )
        except Exception as exc:
            logger.error(
                "background_tool_execution_failed",
                session_id=session_id,
                tool_call_id=tool_call_id,
                error=str(exc),
                exc_info=True,
            )

    async def execute_pending_tool(
        self,
        session_id: str,
        tool_call_id: str,
    ) -> LLMLoopResult:
        """Выполняет pending tool после permission approval и продолжает LLM loop.

        Создаёт PromptOrchestrator и делегирует ему выполнение.
        Согласно ACP протоколу, после выполнения инструмента
        результат передаётся LLM для продолжения диалога.

        Args:
            session_id: ID сессии.
            tool_call_id: ID tool call для выполнения.

        Returns:
            LLMLoopResult с notifications, stop_reason и pending_permission флагом.
        """
        # Носитель состояния resume-пути — доменный агрегат (ADR-006, фаза D шаг 3),
        # а запись идёт командами: каждое изменение коммитится своей короткой
        # транзакцией, и копия, пережившая ожидание, на диск не уезжает (шаг 4).
        domain_session = await self._repository.load_session(session_id)
        if domain_session is None:
            logger.error(
                "session_not_found_for_pending_tool_execution",
                session_id=session_id,
                tool_call_id=tool_call_id,
            )
            return LLMLoopResult(notifications=[], stop_reason="end_turn")

        # MCP-менеджер читает wire-конфигурацию: проекция строится на месте и
        # никуда не сохраняется.
        mcp_manager = await self._mcp_provider(SessionMapper.to_protocol(domain_session))

        # Получить или создать PromptOrchestrator (переиспользуется)
        orchestrator = await self._orchestrator_provider()
        if orchestrator is None:
            logger.error(
                "orchestrator_not_configured_for_pending_tool_execution",
                session_id=session_id,
                tool_call_id=tool_call_id,
            )
            return LLMLoopResult(notifications=[], stop_reason="end_turn")

        # Создаём closure для notification_callback с session_id
        async def notification_callback(message: ACPMessage) -> None:
            await self._send_message(message, session_id)

        return await orchestrator.execute_pending_tool(
            commands=SessionCommands(self._repository, domain_session),
            session_id=session_id,
            tool_call_id=tool_call_id,
            mcp_manager=mcp_manager,
            notification_callback=notification_callback,
        )

    async def complete_active_turn(
        self, session_id: str, *, stop_reason: str = "end_turn"
    ) -> ACPMessage | None:
        """Завершает активный prompt-turn и возвращает финальный response.

        Используется транспортом WS для отложенного ответа на `session/prompt`.

        Args:
            session_id: ID сессии.
            stop_reason: Причина остановки.

        Returns:
            ACPMessage с финальным response или None.
        """
        session = await self._storage.load_session(session_id)
        if session is None:
            return None
        return prompt.complete_active_turn(
            session,
            stop_reason=stop_reason,
        )

    async def should_auto_complete_active_turn(self, session_id: str) -> bool:
        """Возвращает `True`, если active turn можно безопасно автозавершить.

        Если turn ожидает permission-response, автозавершение запрещено.

        Args:
            session_id: ID сессии.

        Returns:
            True если можно автозавершить.
        """
        session = await self._storage.load_session(session_id)
        if session is None or session.active_turn is None:
            return False
        return prompt.should_auto_complete_active_turn(session)

    async def _send_message(
        self,
        message: ACPMessage,
        session_id: str,
    ) -> None:
        """Публикует сообщение в notification bus.

        Args:
            message: Сообщение для публикации.
            session_id: ID сессии для получения bus.
        """
        bus = await self._runtime_registry.get_notification_bus(session_id)
        await bus.publish(message)

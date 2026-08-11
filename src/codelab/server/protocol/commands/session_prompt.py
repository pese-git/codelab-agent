"""SessionPromptCommandHandler - обработчик метода session/prompt.

Обрабатывает пользовательский промпт в контексте сессии,
включая полный жизненный цикл prompt turn.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from ...messages import ACPMessage
from ...storage import SessionRepository
from ..handlers.prompt_orchestrator import PromptOrchestrator
from ..session_commands import SessionCommands
from ..session_runtime import SessionRuntimeRegistry
from ..state import ProtocolOutcome
from ..turn_runtime import TurnEndCause, finish_turn

logger = structlog.get_logger()


class SessionPromptCommandHandler:
    """Обработчик метода session/prompt.

    Отвечает за:
    - Валидацию sessionId
    - Загрузку сессии из storage
    - Очистку stale active_turn
    - Делегирование обработки PromptOrchestrator
    - Сохранение сессии после обработки

    Attributes:
        method_name: Имя обрабатываемого метода.
    """

    method_name = "session/prompt"

    def __init__(
        self,
        repository: SessionRepository,
        orchestrator_provider: Callable[[], Awaitable[PromptOrchestrator]],
        runtime_registry: SessionRuntimeRegistry,
        mcp_provider: Callable[[Any], Awaitable[Any]],
        notification_callback: Callable[[ACPMessage], Awaitable[None]] | None = None,
    ) -> None:
        """Инициализирует обработчик.

        Args:
            repository: Доменный порт хранилища сессий.
            orchestrator_provider: Функция для получения PromptOrchestrator.
            runtime_registry: Реестр runtime-состояний сессий.
            mcp_provider: Функция для получения MCP manager для сессии.
            notification_callback: Callback для отправки notifications.
        """
        self._repository = repository
        self._orchestrator_provider = orchestrator_provider
        self._runtime_registry = runtime_registry
        self._mcp_provider = mcp_provider
        self._notification_callback = notification_callback

    async def handle(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает метод session/prompt.

        Args:
            message: Входящее JSON-RPC сообщение.

        Returns:
            ProtocolOutcome с результатом обработки промпта.
        """
        params = message.params or {}

        orchestrator = await self._orchestrator_provider()
        session_id = params.get("sessionId")
        if not isinstance(session_id, str):
            return ProtocolOutcome(
                response=ACPMessage.error_response(
                    message.id,
                    code=-32602,
                    message="Invalid params: sessionId is required",
                )
            )

        domain_session = await self._repository.load_session(session_id)
        if domain_session is None:
            return ProtocolOutcome(
                response=ACPMessage.error_response(
                    message.id,
                    code=-32001,
                    message=f"Session not found: {session_id}",
                )
            )

        # Валидация ContentBlock-массива по ACP (06-Content): неподдерживаемый
        # тип или битые поля должны отклоняться с -32602, а не молча теряться
        # в acp_mapper.
        from ..handlers.prompt import validate_prompt_content

        prompt_blocks = params.get("prompt")
        if not isinstance(prompt_blocks, list):
            return ProtocolOutcome(
                response=ACPMessage.error_response(
                    message.id,
                    code=-32602,
                    message="Invalid params: prompt must be an array",
                )
            )
        content_error = validate_prompt_content(message.id, prompt_blocks)
        if content_error is not None:
            return ProtocolOutcome(response=content_error)

        commands = SessionCommands(self._repository, domain_session)

        # MCP-менеджер работает доменным агрегатом (ADR-006, фаза D шаг 5). Он не
        # read-only: восстановление prompt'ов правит `available_commands`, и это
        # решение уходит на диск командой — иначе клиент получил бы список команд,
        # которого на диске нет.
        commands_before = list(domain_session.available_commands)
        mcp_manager = await self._mcp_provider(domain_session)
        if domain_session.available_commands != commands_before:
            mcp_commands = list(domain_session.available_commands)
            await commands.apply(
                lambda target: target.set_available_commands(mcp_commands),
                name="mcp_commands_synced",
            )

        # Stale active_turn снимается командой: это изменение состояния, и оно
        # обязано быть на диске до того, как turn начнёт писать своё.
        await commands.apply(
            lambda s: finish_turn(s, cause=TurnEndCause.STALE),
            name="clear_stale_active_turn",
        )

        # Получить MCP prompt handlers из runtime registry
        runtime = await self._runtime_registry.get(session_id)
        mcp_prompt_handlers = runtime.mcp_prompt_handlers if runtime else {}

        # Живая доставка turn-нотификаций через per-session NotificationBus:
        # AgentLoop публикует update'ы по ходу turn'а (транспорт уже подписан),
        # а не батчит их в outcome.notifications. Это выравнивает синхронный
        # prompt-путь с deferred-путём (BackgroundExecutor уже публикует в шину).
        # Явный notification_callback имеет приоритет (используется в тестах).
        notification_callback = self._notification_callback
        if notification_callback is None:
            bus = await self._runtime_registry.get_notification_bus(session_id)
            notification_callback = bus.publish

        return await orchestrator.handle_prompt(
            request_id=message.id,
            params=params,
            commands=commands,
            mcp_manager=mcp_manager,
            mcp_prompt_handlers=mcp_prompt_handlers,
            notification_callback=notification_callback,
        )

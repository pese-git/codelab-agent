"""SessionPromptCommandHandler - обработчик метода session/prompt.

Обрабатывает пользовательский промпт в контексте сессии,
включая полный жизненный цикл prompt turn.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from ...messages import ACPMessage
from ...storage import SessionStorage
from ..handlers.prompt_orchestrator import PromptOrchestrator
from ..session_runtime import SessionRuntimeRegistry
from ..state import ProtocolOutcome

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
        storage: SessionStorage,
        orchestrator_provider: Callable[[], Awaitable[PromptOrchestrator]],
        runtime_registry: SessionRuntimeRegistry,
        mcp_provider: Callable[[Any], Awaitable[Any]],
        notification_callback: Callable[[ACPMessage], Awaitable[None]] | None = None,
    ) -> None:
        """Инициализирует обработчик.

        Args:
            storage: Хранилище сессий.
            orchestrator_provider: Функция для получения PromptOrchestrator.
            runtime_registry: Реестр runtime-состояний сессий.
            mcp_provider: Функция для получения MCP manager для сессии.
            notification_callback: Callback для отправки notifications.
        """
        self._storage = storage
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

        session = await self._storage.load_session(session_id)
        if session is None:
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

        # Очищаем stale active_turn
        session.active_turn = None

        # Получить MCP manager
        mcp_manager = await self._mcp_provider(session)

        # Получить MCP prompt handlers из runtime registry
        runtime = await self._runtime_registry.get(session_id)
        mcp_prompt_handlers = runtime.mcp_prompt_handlers if runtime else {}

        outcome = await orchestrator.handle_prompt(
            request_id=message.id,
            params=params,
            session=session,
            storage=self._storage,
            mcp_manager=mcp_manager,
            mcp_prompt_handlers=mcp_prompt_handlers,
            notification_callback=self._notification_callback,
        )

        # Сохраняем сессию
        try:
            await self._storage.save_session(session)
            logger.debug(
                "session_saved_after_prompt",
                session_id=session_id,
                active_turn_exists=session.active_turn is not None,
            )
        except Exception as e:
            logger.error(
                "failed_to_save_session_after_prompt",
                session_id=session_id,
                error=str(e),
            )

        return outcome

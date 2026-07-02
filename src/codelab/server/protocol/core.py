"""Основной класс протокола ACP.

Содержит реализацию класса ACPProtocol — Facade для обработки
ACP-протокола. Делегирует обработку команд CommandHandler-ам,
responses — ResponseRouter, фоновые задачи — BackgroundExecutor.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Protocol

import structlog

from ..messages import ACPMessage
from ..storage import SessionStorage
from .pending_registry import PendingRequestRegistry
from .state import (
    ProtocolOutcome,
)

if TYPE_CHECKING:
    from ..agent.llm_adapter import LLMAdapter
    from .background_executor import BackgroundExecutor
    from .commands.base import CommandRegistry
    from .handlers.prompt_orchestrator import PromptOrchestrator
    from .response_router import ResponseRouter
    from .session_runtime import SessionRuntimeRegistry

logger = structlog.get_logger()


# Тип обработчика метода: async-функция, принимающая сообщение и возвращающая outcome
MethodHandler = Callable[[ACPMessage], Awaitable[ProtocolOutcome]]


class MiddlewareFn(Protocol):
    """Протокол middleware для сквозной логики (логирование, метрики, auth-check).

    Middleware применяется в порядке onion pattern: первое в списке — внешнее,
    последнее — ближе к обработчику.
    """

    async def __call__(
        self,
        message: ACPMessage,
        next_handler: Callable[[ACPMessage], Awaitable[ProtocolOutcome]],
    ) -> ProtocolOutcome: ...


class ACPProtocol:
    """Facade для ACP-протокола.

    Делегирует обработку команд зарегистрированным CommandHandler-ам,
    responses — ResponseRouter, фоновые задачи — BackgroundExecutor.

    Отвечает только за:
    - Маршрутизацию сообщений через CommandRegistry
    - Применение middleware (Chain of Responsibility)
    - Lifecycle management (cancel, cleanup)

    Пример использования:
        protocol = ACPProtocol(
            method_registry=registry,
            response_router=router,
            background_executor=executor,
        )
        outcome = await protocol.handle(ACPMessage.request("session/list", {}))
    """

    def __init__(
        self,
        *,
        method_registry: CommandRegistry,
        response_router: ResponseRouter,
        background_executor: BackgroundExecutor,
        storage: SessionStorage | None = None,
        pending_registry: PendingRequestRegistry | None = None,
        runtime_registry: SessionRuntimeRegistry | None = None,
        middleware: list[MiddlewareFn] | None = None,
        send_callback: Callable[[ACPMessage], Awaitable[None]] | None = None,
        llm_adapter: LLMAdapter | None = None,
        orchestrator_provider: Callable[[], Awaitable[PromptOrchestrator]] | None = None,
    ) -> None:
        """Инициализирует ACPProtocol (Facade).

        Все зависимости передаются извне (через DI-контейнер, см.
        codelab.server.di.make_container). Фасад ничего не собирает сам.

        Args:
            method_registry: Реестр обработчиков команд (Command Pattern).
            response_router: Маршрутизатор ответов от клиента.
            background_executor: Исполнитель фоновых задач.
            storage: Хранилище сессий (по умолчанию InMemoryStorage).
            pending_registry: Реестр pending permission requests.
            runtime_registry: Реестр runtime-состояний сессий.
            middleware: Список middleware функций для сквозной логики.
            send_callback: Callback для отправки сообщений транспортом.
            llm_adapter: Адаптер LLM для cancellation.
            orchestrator_provider: Функция для получения PromptOrchestrator.
        """
        if storage is None:
            from ..storage import InMemoryStorage
            storage = InMemoryStorage()
        self._storage = storage
        self._method_registry = method_registry
        self._response_router = response_router
        self._background_executor = background_executor
        self._pending_registry = pending_registry or PendingRequestRegistry()
        self._runtime_registry = runtime_registry
        self._middleware = middleware or []
        self._send_callback = send_callback
        self._llm_adapter = llm_adapter
        self._orchestrator_provider = orchestrator_provider

    @property
    def storage(self) -> SessionStorage:
        """Хранилище сессий (для обратной совместимости)."""
        return self._storage

    @property
    def _handlers(self) -> dict[str, Any]:
        """Legacy dict обработчиков методов (для обратной совместимости)."""
        methods = (
            self._method_registry.list_methods()
            if hasattr(self._method_registry, "list_methods")
            else []
        )
        return {
            method: handler.handle
            for method, handler in [
                (m, self._method_registry.get(m))
                for m in methods
            ]
            if handler is not None
        }

    async def handle(self, message: ACPMessage) -> ProtocolOutcome:
        """Маршрутизирует входящее сообщение по методу через реестр обработчиков.

        Метод является основной точкой входа для HTTP/WS транспорта.
        Использует CommandRegistry для поиска обработчиков (Command Pattern).

        Args:
            message: Входящее JSON-RPC сообщение.

        Returns:
            ProtocolOutcome с результатом обработки.
        """
        # Если method=None, это response (JSON-RPC 2.0)
        if message.method is None:
            logger.debug(
                "response_received_routing_to_handle_client_response",
                request_id=message.id,
            )
            return await self._response_router.handle_client_response(message)

        method = message.method

        # Используем CommandRegistry для поиска обработчика
        command_handler = self._method_registry.get(method)

        if command_handler is None:
            # Уведомления — игнорируем без ошибки
            if message.is_notification:
                return ProtocolOutcome()
            return ProtocolOutcome(
                response=ACPMessage.error_response(
                    message.id, code=-32601, message=f"Method not found: {method}"
                )
            )

        # Применяем middleware в обратном порядке (onion pattern)
        wrapped: Callable[[ACPMessage], Awaitable[ProtocolOutcome]] = command_handler.handle
        for mw in reversed(self._middleware):
            next_handler = wrapped

            async def wrapped_with_middleware(
                msg: ACPMessage,
                _mw: MiddlewareFn = mw,
                _next: Callable[[ACPMessage], Awaitable[ProtocolOutcome]] = next_handler,
            ) -> ProtocolOutcome:
                return await _mw(msg, _next)

            wrapped = wrapped_with_middleware

        return await wrapped(message)

    async def handle_and_process(
        self, message: ACPMessage
    ) -> ProtocolOutcome:
        """Обрабатывает сообщение и запускает фоновые задачи если нужно.

        Расширяет handle() логикой постобработки outcome:
        - Если outcome содержит pending_tool_execution, запускает фоновую задачу
        - Транспорт получает чистый outcome и только отправляет его

        Это основной entry point для транспорта — вместо прямого вызова handle().

        Args:
            message: Входящее ACPMessage.

        Returns:
            ProtocolOutcome для отправки транспортом.
        """
        outcome = await self.handle(message)

        if outcome.pending_tool_execution is not None:
            pending = outcome.pending_tool_execution
            logger.info(
                "scheduling_pending_tool_execution_in_background",
                session_id=pending.session_id,
                tool_call_id=pending.tool_call_id,
            )
            asyncio.create_task(
                self._background_executor.execute_tool_in_background(
                    session_id=pending.session_id,
                    tool_call_id=pending.tool_call_id,
                )
            )

        return outcome

    async def handle_client_response(self, message: ACPMessage) -> ProtocolOutcome:
        """Обрабатывает входящий response от клиента (legacy proxy).

        Делегирует ResponseRouter.

        Args:
            message: Входящее JSON-RPC сообщение (response).

        Returns:
            ProtocolOutcome с результатом обработки.
        """
        return await self._response_router.handle_client_response(message)

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
        return await self._background_executor.complete_active_turn(
            session_id, stop_reason=stop_reason
        )

    async def should_auto_complete_active_turn(self, session_id: str) -> bool:
        """Возвращает `True`, если active turn можно безопасно автозавершить.

        Если turn ожидает permission-response, автозавершение запрещено.

        Args:
            session_id: ID сессии.

        Returns:
            True если можно автозавершить.
        """
        return await self._background_executor.should_auto_complete_active_turn(session_id)

    async def execute_pending_tool(
        self,
        session_id: str,
        tool_call_id: str,
    ) -> Any:
        """Выполняет pending tool после permission approval и продолжает LLM loop.

        Args:
            session_id: ID сессии.
            tool_call_id: ID tool call для выполнения.

        Returns:
            LLMLoopResult с notifications, stop_reason и pending_permission флагом.
        """
        return await self._background_executor.execute_pending_tool(
            session_id=session_id,
            tool_call_id=tool_call_id,
        )

    async def cancel_active_turns_on_disconnect(self) -> int:
        """Отменяет все активные turn в рамках текущего протокольного инстанса.

        Используется транспортом при разрыве соединения клиента. Метод
        обеспечивает ACP-инвариант остановки in-flight turn и освобождение
        внутренних ожиданий без отправки сетевых сообщений.

        Returns:
            Количество сессий, в которых активный turn был отменен.
        """
        if self._orchestrator_provider is None:
            return 0

        cancelled_count = 0
        cursor = None
        while True:
            sessions, cursor = await self._storage.list_sessions(cursor=cursor, limit=100)
            for session_state in sessions:
                if session_state.active_turn is None:
                    continue

                orchestrator = await self._orchestrator_provider()
                orchestrator.handle_cancel(
                    request_id=None,
                    params={"sessionId": session_state.session_id},
                    session=session_state,
                )
                cancelled_count += 1

                try:
                    await self._storage.save_session(session_state)
                except Exception:
                    continue

            if cursor is None:
                break

        return cancelled_count

    async def _send_message(self, message: ACPMessage) -> None:
        """Отправляет сообщение через transport callback."""
        if self._send_callback is not None:
            await self._send_callback(message)
        else:
            logger.warning(
                "no send callback configured, message not sent",
                method=message.method,
            )

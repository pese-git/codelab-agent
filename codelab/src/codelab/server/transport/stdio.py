"""Stdio транспорт ACP-сервера.

Модуль содержит реализацию AcpServerTransport поверх stdin/stdout.
Сервер читает JSON-RPC сообщения из stdin, обрабатывает через callback
и записывает ответы в stdout. Каждое сообщение отделено символом новой строки.

Логирование направляется ТОЛЬКО в stderr — stdout содержит исключительно
JSON-RPC сообщения.

Обработка `session/prompt` выполняется в отдельной фоновой задаче (через
``asyncio.create_task``), чтобы receive-loop мог продолжать читать stdin и
маршрутизировать client RPC responses (например, ответы клиента на
``fs/read_text_file``). Это устраняет deadlock в bypass mode, когда tool
execute синхронно ожидает client RPC response внутри обработки prompt.

Пример использования:
    transport = StdioServerTransport(
        schedule_pending_tool=protocol._execute_tool_in_background,
        should_auto_complete=protocol.should_auto_complete_active_turn,
        complete_active_turn=protocol.complete_active_turn,
        load_pending_prompt_response=load_pending_prompt_response,
    )
    await transport.run(on_message=protocol.handle_and_process)
"""

from __future__ import annotations

import asyncio
import signal
import sys
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from codelab.server.messages import ACPMessage
from codelab.server.protocol.state import ProtocolOutcome

logger = structlog.get_logger()

# Небольшая задержка для окна между outcome без response и возможным session/cancel
_DEFERRED_PROMPT_GUARD_DELAY = 0.05


# Типы callbacks для интеграции с протоколом (без прямой зависимости от ACPProtocol)
SchedulePendingToolCallback = Callable[[str, str], Awaitable[None]]
ShouldAutoCompleteCallback = Callable[[str], Awaitable[bool]]
CompleteActiveTurnCallback = Callable[[str, str], Awaitable[ACPMessage | None]]
LoadPendingPromptResponseCallback = Callable[[str], Awaitable[ACPMessage | None]]


class StdioServerTransport:
    """Stdio реализация AcpServerTransport.

    Читает JSON-RPC сообщения из stdin (newline-delimited), передаёт
    их в callback on_message и записывает responses/notifications в stdout.

    Все логи направляются в stderr — stdout содержит ТОЛЬКО JSON-RPC.

    `session/prompt` обрабатывается в фоне, чтобы не блокировать receive-loop.
    Это позволяет одновременно читать stdin для маршрутизации client RPC
    responses (ответы клиента на server-originated requests типа
    ``fs/read_text_file``).

    Атрибуты:
        _stdin_reader: asyncio.StreamReader для чтения из stdin.
        _send_lock: asyncio.Lock для защиты записи в stdout.
        _closed: Флаг завершения работы.
        _schedule_pending_tool: Callback для фонового запуска
            pending tool execution (после permission approval).
        _should_auto_complete: Callback для проверки, нужно ли автозавершать
            active turn после возврата outcome без response.
        _complete_active_turn: Callback для завершения active turn и получения
            финального prompt response.
        _load_pending_prompt_response: Callback для построения финального
            ACPMessage из ``session.pending_prompt_response`` (используется
            при отмене deferred prompt task через ``session/cancel``).
        _prompt_tasks: Множество фоновых задач обработки ``session/prompt``.
        _deferred_prompt_tasks: Map ``session_id -> Task`` для отложенного
            завершения prompt-turn.
    """

    def __init__(
        self,
        *,
        schedule_pending_tool: SchedulePendingToolCallback | None = None,
        should_auto_complete: ShouldAutoCompleteCallback | None = None,
        complete_active_turn: CompleteActiveTurnCallback | None = None,
        load_pending_prompt_response: LoadPendingPromptResponseCallback | None = None,
    ) -> None:
        """Инициализирует stdio транспорт.

        Args:
            schedule_pending_tool: Callback для фонового запуска
                pending tool execution. Без него ``pending_tool_execution`` в
                outcome будет проигнорирован (с warning).
            should_auto_complete: Callback для проверки, нужно ли автозавершать
                active turn. Если None — deferred completion отключено.
            complete_active_turn: Callback для завершения active turn. Если
                None — deferred completion отключено.
            load_pending_prompt_response: Callback для построения финального
                response при отмене deferred prompt task. Если None — на
                ``session/cancel`` финальный response не отправляется через
                этот путь (полагаемся на основной handler).
        """
        self._stdin_reader: asyncio.StreamReader | None = None
        self._send_lock = asyncio.Lock()
        self._closed = False
        self._on_message: Callable[[ACPMessage], Awaitable[ProtocolOutcome]] | None = None

        # Callbacks для интеграции с ACPProtocol (опциональные)
        self._schedule_pending_tool = schedule_pending_tool
        self._should_auto_complete = should_auto_complete
        self._complete_active_turn = complete_active_turn
        self._load_pending_prompt_response = load_pending_prompt_response

        # Трекинг фоновых задач
        self._prompt_tasks: set[asyncio.Task[None]] = set()
        self._deferred_prompt_tasks: dict[str, asyncio.Task[None]] = {}

    async def run(
        self,
        on_message: Callable[[ACPMessage], Awaitable[ProtocolOutcome]],
    ) -> None:
        """Основной цикл чтения сообщений из stdin.

        Читает строки из stdin, парсит JSON-RPC, вызывает on_message
        и отправляет результаты в stdout.

        Завершается при:
        - EOF (stdin закрыт)
        - Вызове close()
        - Ошибке парсинга (продолжает работу, логирует ошибку)

        Args:
            on_message: Callback для обработки входящих сообщений.
        """
        self._on_message = on_message

        # Настраиваем line buffering для stdout
        sys.stdout.reconfigure(line_buffering=True)

        # Создаём StreamReader для stdin
        self._stdin_reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(self._stdin_reader)
        await asyncio.get_running_loop().connect_read_pipe(lambda: protocol, sys.stdin.buffer)

        # Register signal handlers для graceful shutdown
        self._setup_signal_handlers()

        logger.info("stdio transport started")

        try:
            while not self._closed:
                line = await self._stdin_reader.readline()

                if not line:
                    # EOF — stdin закрыт
                    logger.info("stdin EOF, shutting down")
                    break

                # Декодируем и парсим JSON-RPC сообщение
                try:
                    text = line.decode("utf-8").strip()
                    if not text:
                        # Пустая строка — пропускаем
                        continue

                    acp_request = ACPMessage.from_json(text)
                except Exception as exc:
                    # Parse error — отправляем error response
                    logger.warning("parse error", error=str(exc))
                    error_response = ACPMessage.error_response(
                        None,
                        code=-32700,
                        message="Parse error",
                        data=str(exc),
                    )
                    await self.send(error_response)
                    continue

                # Извлекаем метаданные для маршрутизации/логирования
                method_name = acp_request.method
                request_id = (
                    str(acp_request.id) if acp_request.id is not None else None
                )
                session_id: str | None = None
                if isinstance(acp_request.params, dict):
                    raw_session_id = acp_request.params.get("sessionId")
                    if isinstance(raw_session_id, str):
                        session_id = raw_session_id

                # session/prompt выполняем в фоне, чтобы receive-loop мог
                # продолжать читать stdin и маршрутизировать client RPC
                # responses (ответы клиента на fs/*, terminal/* и т.д.).
                if method_name == "session/prompt":
                    prompt_task = asyncio.create_task(
                        self._process_prompt_request_in_background(
                            acp_request=acp_request,
                            on_message=on_message,
                            method_name=method_name,
                            session_id=session_id,
                            request_id=request_id,
                        )
                    )
                    self._prompt_tasks.add(prompt_task)
                    prompt_task.add_done_callback(
                        lambda finished_task: self._prompt_tasks.discard(finished_task)
                    )
                    logger.debug(
                        "prompt request scheduled in background",
                        request_id=request_id,
                        session_id=session_id,
                    )
                    continue

                # Все остальные сообщения (включая response от клиента
                # с method=None) обрабатываются синхронно — они быстрые и
                # не делают исходящих RPC, ожидающих stdin.
                try:
                    outcome = await on_message(acp_request)
                    await self._finalize_outcome_and_send(
                        method_name=method_name,
                        session_id=session_id,
                        outcome=outcome,
                    )
                except Exception as exc:
                    logger.error(
                        "message handling error",
                        method=method_name,
                        error=str(exc),
                        exc_info=True,
                    )
                    error_response = ACPMessage.error_response(
                        acp_request.id,
                        code=-32603,
                        message="Internal error",
                        data=str(exc),
                    )
                    await self.send(error_response)

        except asyncio.CancelledError:
            logger.info("stdio transport cancelled")
        finally:
            await self._cleanup_background_tasks()
            self._restore_signal_handlers()
            logger.info("stdio transport stopped")

    async def send(self, message: ACPMessage) -> None:
        """Отправить сообщение в stdout.

        Записывает JSON-RPC сообщение в stdout, завершённое newline.
        Защищено asyncio.Lock для предотвращения interleaving.

        Args:
            message: ACPMessage для отправки.
        """
        async with self._send_lock:
            if self._closed:
                return

            try:
                data = message.to_json().encode("utf-8") + b"\n"
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            except BrokenPipeError:
                logger.warning("stdout pipe broken, closing transport")
                self._closed = True
            except Exception as exc:
                logger.error("send error", error=str(exc))

    async def close(self) -> None:
        """Graceful shutdown транспорта.

        Устанавливает флаг _closed, отменяет pending operations.
        Метод идемпотентен.
        """
        self._closed = True
        await self._cleanup_background_tasks()
        logger.info("stdio transport closing")

    # =========================================================================
    # Internal helpers
    # =========================================================================

    async def _send_outcome(self, outcome: ProtocolOutcome) -> None:
        """Отправляет notifications, response и followups из outcome."""
        # Сначала notifications
        for notification in outcome.notifications:
            await self.send(notification)

        # Затем response
        if outcome.response is not None:
            await self.send(outcome.response)

        # Затем followup responses
        for followup in outcome.followup_responses:
            await self.send(followup)

    async def _finalize_outcome_and_send(
        self,
        *,
        method_name: str | None,
        session_id: str | None,
        outcome: ProtocolOutcome,
    ) -> None:
        """Применяет post-processing outcome и отправляет его в stdout.

        Логика зеркалит WebSocketTransport._finalize_outcome_and_send:
        - session/cancel — отменяет deferred prompt task для session.
        - session/prompt без response — создаёт deferred completion task,
          если callbacks доступны и должен быть auto-complete.
        - pending_tool_execution — запускает schedule_pending_tool в фоне.
        """
        # session/cancel — отменяем deferred prompt
        if method_name == "session/cancel" and session_id is not None:
            task = self._deferred_prompt_tasks.pop(session_id, None)
            if task is not None and not task.done():
                task.cancel()

        # session/prompt без response — создаём deferred task для авто-завершения
        if (
            method_name == "session/prompt"
            and session_id is not None
            and outcome.response is None
            and self._should_auto_complete is not None
            and self._complete_active_turn is not None
        ):
            try:
                should_complete = await self._should_auto_complete(session_id)
            except Exception as exc:
                logger.error(
                    "should_auto_complete callback error",
                    session_id=session_id,
                    error=str(exc),
                    exc_info=True,
                )
                should_complete = False

            if should_complete:
                # Отменяем предыдущий deferred task для этой session, если был
                existing = self._deferred_prompt_tasks.pop(session_id, None)
                if existing is not None and not existing.done():
                    existing.cancel()

                self._deferred_prompt_tasks[session_id] = asyncio.create_task(
                    self._complete_deferred_prompt(session_id=session_id)
                )

        # Обработка pending_tool_execution для permission response
        if outcome.pending_tool_execution is not None:
            pending = outcome.pending_tool_execution
            if self._schedule_pending_tool is not None:
                logger.info(
                    "scheduling pending tool execution in background",
                    session_id=pending.session_id,
                    tool_call_id=pending.tool_call_id,
                )
                # Оборачиваем callback в локальную coroutine: это даёт
                # `create_task` корректный Coroutine[Any, Any, None] вместо
                # широкого Awaitable[None] и упрощает обработку ошибок.
                scheduled_session_id = pending.session_id
                scheduled_tool_call_id = pending.tool_call_id
                scheduled_callback = self._schedule_pending_tool

                async def _run_scheduled_tool() -> None:
                    try:
                        await scheduled_callback(
                            scheduled_session_id,
                            scheduled_tool_call_id,
                        )
                    except Exception as exc:
                        logger.error(
                            "scheduled pending tool execution failed",
                            session_id=scheduled_session_id,
                            tool_call_id=scheduled_tool_call_id,
                            error=str(exc),
                            exc_info=True,
                        )

                asyncio.create_task(_run_scheduled_tool())
            else:
                logger.warning(
                    "pending_tool_execution requested but no callback configured",
                    session_id=pending.session_id,
                    tool_call_id=pending.tool_call_id,
                )

        await self._send_outcome(outcome)

    async def _process_prompt_request_in_background(
        self,
        *,
        acp_request: ACPMessage,
        on_message: Callable[[ACPMessage], Awaitable[ProtocolOutcome]],
        method_name: str | None,
        session_id: str | None,
        request_id: str | None,
    ) -> None:
        """Выполняет `session/prompt` в фоне, не блокируя receive-loop.

        Это позволяет receive-loop продолжать читать stdin и маршрутизировать
        client RPC responses (например, ответы клиента на ``fs/read_text_file``,
        которые tool ожидает в bypass mode).
        """
        try:
            outcome = await on_message(acp_request)
            logger.debug(
                "background prompt request processed",
                method=method_name,
                request_id=request_id,
                session_id=session_id,
            )
            await self._finalize_outcome_and_send(
                method_name=method_name,
                session_id=session_id,
                outcome=outcome,
            )
        except asyncio.CancelledError:
            logger.info(
                "background prompt request cancelled",
                request_id=request_id,
                session_id=session_id,
            )
            raise
        except Exception as exc:
            logger.error(
                "background prompt request error",
                request_id=request_id,
                session_id=session_id,
                error=str(exc),
                exc_info=True,
            )
            error_response = ACPMessage.error_response(
                acp_request.id,
                code=-32603,
                message="Internal error",
                data=str(exc),
            )
            await self.send(error_response)

    async def _complete_deferred_prompt(self, *, session_id: str) -> None:
        """Завершает отложенный `session/prompt` и отправляет финальный response.

        Зеркалит логику WebSocketTransport._complete_deferred_prompt:
        - Короткая задержка оставляет окно для входящего ``session/cancel``.
        - На отмену пытается достать ``pending_prompt_response`` и отправить его.
        """
        sess_logger = logger.bind(session_id=session_id)

        try:
            # Небольшая задержка — окно для входящего session/cancel
            await asyncio.sleep(_DEFERRED_PROMPT_GUARD_DELAY)

            response: ACPMessage | None = None
            try:
                if self._complete_active_turn is not None:
                    response = await self._complete_active_turn(session_id, "end_turn")
            except Exception as exc:
                sess_logger.error(
                    "deferred prompt completion error",
                    error=str(exc),
                    exc_info=True,
                )
                response = None

            if response is not None and not self._closed:
                try:
                    await self.send(response)
                    sess_logger.info("deferred prompt completed successfully")
                except Exception as exc:
                    sess_logger.error(
                        "deferred prompt send error",
                        error=str(exc),
                        exc_info=True,
                    )
            elif self._closed:
                sess_logger.debug("deferred prompt skipped (transport closed)")
            else:
                sess_logger.debug("deferred prompt skipped (no response)")

        except asyncio.CancelledError:
            sess_logger.info("deferred prompt cancelled by client")
            try:
                if self._load_pending_prompt_response is not None:
                    response = await self._load_pending_prompt_response(session_id)
                    if response is not None and not self._closed:
                        await self.send(response)
                        sess_logger.info("deferred prompt cancelled response sent")
            except Exception as exc:
                sess_logger.debug(
                    "deferred prompt cancelled response error",
                    error=str(exc),
                )
            return
        except Exception as exc:
            sess_logger.error(
                "deferred prompt unexpected error",
                error=str(exc),
                exc_info=True,
            )
        finally:
            removed = self._deferred_prompt_tasks.pop(session_id, None)
            if removed is not None:
                sess_logger.debug("deferred prompt task removed from tracking")

    async def _cleanup_background_tasks(self) -> None:
        """Отменяет и ждёт завершения всех фоновых задач.

        Идемпотентно — повторный вызов безопасен.
        """
        # Cleanup: prompt tasks
        if self._prompt_tasks:
            logger.info(
                "cleaning up prompt request tasks",
                pending_tasks_count=len(self._prompt_tasks),
            )
            for prompt_task in list(self._prompt_tasks):
                if not prompt_task.done():
                    prompt_task.cancel()
            await asyncio.gather(*self._prompt_tasks, return_exceptions=True)
            self._prompt_tasks.clear()

        # Cleanup: deferred prompt tasks
        if self._deferred_prompt_tasks:
            logger.info(
                "cleaning up deferred prompt tasks",
                pending_tasks_count=len(self._deferred_prompt_tasks),
            )
            tasks = list(self._deferred_prompt_tasks.values())
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self._deferred_prompt_tasks.clear()

    def _setup_signal_handlers(self) -> None:
        """Register signal handlers для graceful shutdown."""

        def _signal_handler(signum: int, frame: Any) -> None:
            logger.info("signal received", signal=signum)
            self._closed = True

        try:
            signal.signal(signal.SIGTERM, _signal_handler)
            signal.signal(signal.SIGINT, _signal_handler)
        except (ValueError, OSError):
            # Signal handlers can only be set from main thread
            logger.debug("signal handlers not set (not main thread)")

    def _restore_signal_handlers(self) -> None:
        """Restore default signal handlers."""
        try:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            signal.signal(signal.SIGINT, signal.SIG_DFL)
        except (ValueError, OSError):
            pass

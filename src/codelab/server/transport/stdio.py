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
        should_auto_complete=protocol.should_auto_complete_active_turn,
        complete_active_turn=protocol.complete_active_turn,
        load_pending_prompt_response=load_pending_prompt_response,
    )
    await transport.run(on_message=protocol.handle_and_process)
"""

from __future__ import annotations

import asyncio
import contextlib
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

# Максимальный размер сообщения для stdio транспорта (25 MB).
# Покрывает максимальный размер image (20 MB base64) + JSON overhead.
MAX_STDIO_MESSAGE_SIZE = 25 * 1024 * 1024


# Типы callbacks для интеграции с протоколом (без прямой зависимости от ACPProtocol)
ShouldAutoCompleteCallback = Callable[[str], Awaitable[bool]]
CompleteActiveTurnCallback = Callable[[str, str], Awaitable[ACPMessage | None]]
LoadPendingPromptResponseCallback = Callable[[str], Awaitable[ACPMessage | None]]
# Регистрация исходящего запроса к клиенту: синхронная, потому что вызывается под
# `_send_lock` прямо перед записью в stdout — await там задержал бы отправку.
RecordOutgoingRequestCallback = Callable[[ACPMessage], None]


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
        should_auto_complete: ShouldAutoCompleteCallback | None = None,
        complete_active_turn: CompleteActiveTurnCallback | None = None,
        load_pending_prompt_response: LoadPendingPromptResponseCallback | None = None,
        record_outgoing_request: RecordOutgoingRequestCallback | None = None,
    ) -> None:
        """Инициализирует stdio транспорт.

        Args:
            should_auto_complete: Callback для проверки, нужно ли автозавершать
                active turn. Если None — deferred completion отключено.
            complete_active_turn: Callback для завершения active turn. Если
                None — deferred completion отключено.
            load_pending_prompt_response: Callback для построения финального
                response при отмене deferred prompt task. Если None — на
                ``session/cancel`` финальный response не отправляется через
                этот путь (полагаемся на основной handler).
            record_outgoing_request: Callback регистрации исходящего запроса к
                клиенту. Транспорт — единственная точка, мимо которой не проходит
                ни один путь отправки, поэтому корреляция «запрос → сессия»
                заводится здесь (ADR-008, раздел 7).
        """
        self._stdin_reader: asyncio.StreamReader | None = None
        self._send_lock = asyncio.Lock()
        self._closed = False
        self._on_message: Callable[[ACPMessage], Awaitable[ProtocolOutcome]] | None = None

        # Callbacks для интеграции с ACPProtocol (опциональные)
        self._should_auto_complete = should_auto_complete
        self._complete_active_turn = complete_active_turn
        self._load_pending_prompt_response = load_pending_prompt_response
        self._record_outgoing_request = record_outgoing_request

        # Трекинг фоновых задач
        self._prompt_tasks: set[asyncio.Task[None]] = set()
        self._deferred_prompt_tasks: dict[str, asyncio.Task[None]] = {}

        # Текущее чтение stdin. Сигнал завершения обязан его отменить: цикл
        # проверяет `_closed` только после возврата из readline(), а при
        # молчащем клиенте возврата не происходит никогда.
        self._read_task: asyncio.Task[bytes] | None = None

    async def _decode_request(self, line: bytes) -> ACPMessage | None:
        """Декодирует строку stdin в ACPMessage.

        Возвращает `None` на пустой строке или при parse error (в последнем случае
        клиенту отправляется error response) — вызывающий цикл делает `continue`.
        """
        try:
            text = line.decode("utf-8").strip()
            if not text:
                return None
            return ACPMessage.from_json(text)
        except Exception as exc:
            logger.warning("parse error", error=str(exc))
            await self.send(
                ACPMessage.error_response(
                    None,
                    code=-32700,
                    message="Parse error",
                    data=str(exc),
                )
            )
            return None

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
        self._stdin_reader = asyncio.StreamReader(limit=MAX_STDIO_MESSAGE_SIZE)
        protocol = asyncio.StreamReaderProtocol(self._stdin_reader)
        await asyncio.get_running_loop().connect_read_pipe(lambda: protocol, sys.stdin.buffer)

        # Register signal handlers для graceful shutdown
        self._setup_signal_handlers()

        logger.info("stdio transport started")

        try:
            while not self._closed:
                line = await self._next_line()
                if line is None:
                    break

                # Декодируем и парсим JSON-RPC сообщение (None — пустая строка/parse error)
                acp_request = await self._decode_request(line)
                if acp_request is None:
                    continue

                # Извлекаем метаданные для маршрутизации/логирования
                method_name = acp_request.method
                request_id = str(acp_request.id) if acp_request.id is not None else None
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

            if self._record_outgoing_request is not None:
                self._record_outgoing_request(message)

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
            await self._emit_deferred_completion(session_id, sess_logger)
        except asyncio.CancelledError:
            sess_logger.info("deferred prompt cancelled by client")
            await self._emit_deferred_cancel_response(session_id, sess_logger)
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

    async def _emit_deferred_completion(self, session_id: str, sess_logger: Any) -> None:
        """Штатное завершение turn: вычислить финальный response и отправить его."""
        response: ACPMessage | None = None
        try:
            if self._complete_active_turn is not None:
                response = await self._complete_active_turn(session_id, "end_turn")
        except Exception as exc:
            sess_logger.error("deferred prompt completion error", error=str(exc), exc_info=True)
            response = None

        if response is not None and not self._closed:
            try:
                await self.send(response)
                sess_logger.info("deferred prompt completed successfully")
            except Exception as exc:
                sess_logger.error("deferred prompt send error", error=str(exc), exc_info=True)
        elif self._closed:
            sess_logger.debug("deferred prompt skipped (transport closed)")
        else:
            sess_logger.debug("deferred prompt skipped (no response)")

    async def _emit_deferred_cancel_response(self, session_id: str, sess_logger: Any) -> None:
        """Путь отмены: достать pending_prompt_response и отправить, если возможно."""
        try:
            if self._load_pending_prompt_response is not None:
                response = await self._load_pending_prompt_response(session_id)
                if response is not None and not self._closed:
                    await self.send(response)
                    sess_logger.info("deferred prompt cancelled response sent")
        except Exception as exc:
            sess_logger.debug("deferred prompt cancelled response error", error=str(exc))

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

    async def _next_line(self) -> bytes | None:
        """Прочитать следующую строку stdin или вернуть None, если пора остановиться.

        None означает исчерпание входа в любой форме: EOF, отмена чтения
        сигналом завершения, слишком большое сообщение (после ответа клиенту).
        """
        try:
            line = await self._read_line()
        except asyncio.CancelledError:
            # Отмена чтения — это сигнал завершения (см. _request_stop). Внешняя
            # отмена цикла приходит с ещё не выставленным `_closed`, и её нужно
            # пробросить как отмену задачи, а не гасить.
            if not self._closed:
                raise
            logger.info("stdin read cancelled by shutdown signal")
            return None
        except ValueError as exc:
            # StreamReader.readline() raises ValueError when the line
            # exceeds the buffer limit (MAX_STDIO_MESSAGE_SIZE).
            logger.error(
                "stdin message too large",
                max_size_bytes=MAX_STDIO_MESSAGE_SIZE,
                error=str(exc),
            )
            await self.send(
                ACPMessage.error_response(
                    None,
                    code=-32700,
                    message="Message too large",
                    data=f"Message exceeds maximum size of {MAX_STDIO_MESSAGE_SIZE} bytes",
                )
            )
            return None

        if not line:
            logger.info("stdin EOF, shutting down")
            return None

        return line

    async def _read_line(self) -> bytes:
        """Прочитать строку из stdin отменяемым образом.

        Чтение живёт в отдельной задаче, чтобы обработчик сигнала мог его
        отменить. Без этого `_closed = True` не наблюдается: цикл сверяет флаг
        только после возврата из чтения, а молчащий клиент возврата не даёт.
        """
        assert self._stdin_reader is not None

        self._read_task = asyncio.ensure_future(self._stdin_reader.readline())
        try:
            return await self._read_task
        finally:
            self._read_task = None

    def _request_stop(self, signum: int) -> None:
        """Пометить завершение и разбудить цикл чтения."""
        logger.info("signal received", signal=signum)
        self._closed = True
        if self._read_task is not None and not self._read_task.done():
            self._read_task.cancel()

    def _setup_signal_handlers(self) -> None:
        """Register signal handlers для graceful shutdown.

        Обработчики ставятся через event loop: только так они исполняются в
        контексте loop'а и могут отменить текущее чтение. Синхронный
        `signal.signal` этого не умеет — он выставлял флаг, который цикл,
        припаркованный в чтении stdin, никогда не проверял, и процесс
        игнорировал SIGTERM (подтверждено живьём: `signal received signal=15`
        в логе процесса, прожившего после этого 17 минут).
        """
        try:
            loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        for sig in (signal.SIGTERM, signal.SIGINT):
            if loop is not None:
                try:
                    loop.add_signal_handler(sig, self._request_stop, sig)
                    continue
                except (NotImplementedError, RuntimeError, ValueError, OSError) as exc:
                    logger.debug("loop signal handler unavailable", signal=sig, error=str(exc))

            # Откат на синхронный обработчик (нет loop'а, не главный поток, не
            # Unix). Он хуже: разбудить чтение из него нельзя, но флаг выставит.
            try:
                signal.signal(sig, lambda signum, _frame: self._request_stop(signum))
            except (ValueError, OSError) as exc:
                logger.debug("signal handler not set", signal=sig, error=str(exc))

    def _restore_signal_handlers(self) -> None:
        """Restore default signal handlers.

        Снимаются оба вида обработчиков: поставленный на loop'е и синхронный
        откат — какой именно сработал при установке, здесь уже неизвестно.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        for sig in (signal.SIGTERM, signal.SIGINT):
            if loop is not None:
                with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
                    loop.remove_signal_handler(sig)
            try:
                signal.signal(sig, signal.SIG_DFL)
            except (ValueError, OSError) as exc:
                logger.debug("signal handler not restored", signal=sig, error=str(exc))

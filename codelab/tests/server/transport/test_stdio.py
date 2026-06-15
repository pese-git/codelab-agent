"""Тесты для StdioServerTransport."""

import asyncio
import signal
import sys
from unittest.mock import AsyncMock, patch

import pytest

from codelab.server.messages import ACPMessage
from codelab.server.protocol.state import (
    PendingToolExecution,
    ProtocolOutcome,
)
from codelab.server.transport.stdio import StdioServerTransport


class TestStdioServerTransportInit:
    """Тесты для инициализации StdioServerTransport."""

    def test_initial_state(self) -> None:
        """Начальное состояние корректное."""
        transport = StdioServerTransport()
        assert transport._stdin_reader is None
        assert transport._closed is False
        assert transport._on_message is None
        # Новые поля для background-режима
        assert transport._prompt_tasks == set()
        assert transport._deferred_prompt_tasks == {}
        assert transport._should_auto_complete is None
        assert transport._complete_active_turn is None
        assert transport._load_pending_prompt_response is None

    def test_init_with_callbacks(self) -> None:
        """Все callbacks сохраняются."""
        cb1 = AsyncMock()
        cb2 = AsyncMock()
        cb3 = AsyncMock()

        transport = StdioServerTransport(
            should_auto_complete=cb1,
            complete_active_turn=cb2,
            load_pending_prompt_response=cb3,
        )
        assert transport._should_auto_complete is cb1
        assert transport._complete_active_turn is cb2
        assert transport._load_pending_prompt_response is cb3


class TestStdioServerTransportSend:
    """Тесты для send()."""

    @pytest.mark.asyncio
    async def test_send_writes_to_stdout(self) -> None:
        """send() записывает JSON в stdout."""
        transport = StdioServerTransport()

        message = ACPMessage(
            jsonrpc="2.0",
            id="test-1",
            method="test",
            params={},
        )

        with patch.object(sys.stdout.buffer, "write") as mock_write, \
             patch.object(sys.stdout.buffer, "flush") as mock_flush:
            await transport.send(message)

            mock_write.assert_called_once()
            mock_flush.assert_called_once()

            written_data = mock_write.call_args[0][0]
            assert b'"jsonrpc":"2.0"' in written_data
            assert b'"id":"test-1"' in written_data
            assert written_data.endswith(b"\n")

    @pytest.mark.asyncio
    async def test_send_does_nothing_when_closed(self) -> None:
        """send() не пишет когда транспорт закрыт."""
        transport = StdioServerTransport()
        await transport.close()

        with patch.object(sys.stdout.buffer, "write") as mock_write:
            await transport.send(ACPMessage(jsonrpc="2.0", id="1", method="test"))
            mock_write.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_handles_broken_pipe(self) -> None:
        """send() обрабатывает BrokenPipeError."""
        transport = StdioServerTransport()

        message = ACPMessage(jsonrpc="2.0", id="1", method="test")

        with patch.object(sys.stdout.buffer, "write", side_effect=BrokenPipeError), \
             patch("codelab.server.transport.stdio.logger"):
            await transport.send(message)

        assert transport._closed is True

    @pytest.mark.asyncio
    async def test_send_is_thread_safe(self) -> None:
        """send() защищён lock для concurrent вызовов."""
        transport = StdioServerTransport()
        message = ACPMessage(jsonrpc="2.0", id="1", method="test")

        with patch.object(sys.stdout.buffer, "write"), \
             patch.object(sys.stdout.buffer, "flush"):
            await asyncio.gather(
                transport.send(message),
                transport.send(message),
                transport.send(message),
            )

        assert transport._closed is False


class TestStdioServerTransportClose:
    """Тесты для close()."""

    @pytest.mark.asyncio
    async def test_close_sets_flag(self) -> None:
        """close() устанавливает _closed=True."""
        transport = StdioServerTransport()
        await transport.close()
        assert transport._closed is True

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self) -> None:
        """close() идемпотентен."""
        transport = StdioServerTransport()
        await transport.close()
        await transport.close()
        assert transport._closed is True


class TestStdioServerTransportSendOutcome:
    """Тесты для _send_outcome()."""

    @pytest.mark.asyncio
    async def test_send_notifications_first(self) -> None:
        """Notifications отправляются перед response."""
        transport = StdioServerTransport()

        notification = ACPMessage(jsonrpc="2.0", method="notify", params={})
        response = ACPMessage(jsonrpc="2.0", id="1", result={"ok": True})

        outcome = ProtocolOutcome(
            response=response,
            notifications=[notification],
            followup_responses=[],
        )

        sent = []
        with patch.object(transport, "send", side_effect=lambda m: sent.append(m)):
            await transport._send_outcome(outcome)

        assert len(sent) == 2
        assert sent[0] == notification
        assert sent[1] == response

    @pytest.mark.asyncio
    async def test_send_followup_responses(self) -> None:
        """Followup responses отправляются после основного response."""
        transport = StdioServerTransport()

        response = ACPMessage(jsonrpc="2.0", id="1", result={"ok": True})
        followup1 = ACPMessage(jsonrpc="2.0", id="2", result={"followup": 1})
        followup2 = ACPMessage(jsonrpc="2.0", id="3", result={"followup": 2})

        outcome = ProtocolOutcome(
            response=response,
            notifications=[],
            followup_responses=[followup1, followup2],
        )

        sent = []
        with patch.object(transport, "send", side_effect=lambda m: sent.append(m)):
            await transport._send_outcome(outcome)

        assert len(sent) == 3
        assert sent[0] == response
        assert sent[1] == followup1
        assert sent[2] == followup2

    @pytest.mark.asyncio
    async def test_send_only_notifications(self) -> None:
        """Отправляются только notifications когда нет response."""
        transport = StdioServerTransport()

        notification = ACPMessage(jsonrpc="2.0", method="notify")

        outcome = ProtocolOutcome(
            response=None,
            notifications=[notification],
            followup_responses=[],
        )

        sent = []
        with patch.object(transport, "send", side_effect=lambda m: sent.append(m)):
            await transport._send_outcome(outcome)

        assert len(sent) == 1
        assert sent[0] == notification


class TestStdioServerTransportSignalHandlers:
    """Тесты для signal handlers."""

    def test_setup_signal_handlers(self) -> None:
        """Signal handlers устанавливаются."""
        transport = StdioServerTransport()

        with patch("codelab.server.transport.stdio.signal.signal") as mock_signal:
            transport._setup_signal_handlers()

            assert mock_signal.call_count == 2

    def test_setup_signal_handlers_not_main_thread(self) -> None:
        """Signal handlers не устанавливаются не в main thread."""
        transport = StdioServerTransport()

        with patch("codelab.server.transport.stdio.signal.signal", side_effect=ValueError):
            transport._setup_signal_handlers()

    def test_signal_handler_sets_closed(self) -> None:
        """Signal handler устанавливает _closed=True."""
        transport = StdioServerTransport()

        captured_handlers = {}

        def capture_signal(sig, handler):
            captured_handlers[sig] = handler

        with patch("codelab.server.transport.stdio.signal.signal", side_effect=capture_signal):
            transport._setup_signal_handlers()

        assert transport._closed is False

        handler = captured_handlers[signal.SIGTERM]
        handler(15, None)

        assert transport._closed is True

    def test_restore_signal_handlers(self) -> None:
        """Signal handlers восстанавливаются."""
        transport = StdioServerTransport()

        with patch("codelab.server.transport.stdio.signal.signal") as mock_signal:
            transport._restore_signal_handlers()

            assert mock_signal.call_count == 2


# =============================================================================
# Новые тесты: background-режим session/prompt, deferred completion, callbacks
# =============================================================================


class TestStdioFinalizeOutcomeAndSend:
    """Тесты _finalize_outcome_and_send: deferred completion, cancel.

    pending_tool_execution обрабатывается в protocol.handle_and_process(),
    а не в транспорте — транспорт только отправляет outcome.
    """

    @pytest.mark.asyncio
    async def test_finalize_does_not_schedule_pending_tool(self) -> None:
        """_finalize_outcome_and_send НЕ schedule'ит pending_tool_execution.

        Это ответственность protocol.handle_and_process(). Транспорт только
        отправляет outcome — избегаем двойного выполнения tool.
        """
        transport = StdioServerTransport()

        outcome = ProtocolOutcome(
            response=ACPMessage(jsonrpc="2.0", id="1", result={"ok": True}),
            pending_tool_execution=PendingToolExecution(
                session_id="sess_1",
                tool_call_id="call_42",
            ),
        )

        sent = []
        with patch.object(transport, "send", side_effect=lambda m: sent.append(m)):
            await transport._finalize_outcome_and_send(
                method_name="session/request_permission",
                session_id="sess_1",
                outcome=outcome,
            )

        # Только response отправлен — никакого scheduling
        assert len(sent) == 1
        assert sent[0].result == {"ok": True}

    @pytest.mark.asyncio
    async def test_deferred_prompt_completion_invoked_when_auto_complete_true(
        self,
    ) -> None:
        """session/prompt без response + should_auto_complete=True → deferred task."""
        should_auto_complete = AsyncMock(return_value=True)
        complete_active_turn = AsyncMock(
            return_value=ACPMessage(jsonrpc="2.0", id="1", result={"stopReason": "end_turn"})
        )
        transport = StdioServerTransport(
            should_auto_complete=should_auto_complete,
            complete_active_turn=complete_active_turn,
        )

        outcome = ProtocolOutcome(response=None)

        sent = []
        with patch.object(transport, "send", side_effect=lambda m: sent.append(m)):
            await transport._finalize_outcome_and_send(
                method_name="session/prompt",
                session_id="sess_1",
                outcome=outcome,
            )

            # Ждём выполнения deferred task (sleep 0.05s + complete)
            assert "sess_1" in transport._deferred_prompt_tasks
            task = transport._deferred_prompt_tasks["sess_1"]
            await task

        should_auto_complete.assert_awaited_once_with("sess_1")
        complete_active_turn.assert_awaited_once_with("sess_1", "end_turn")
        # Финальный response должен быть отправлен
        assert len(sent) == 1
        assert sent[0].result == {"stopReason": "end_turn"}

    @pytest.mark.asyncio
    async def test_deferred_prompt_not_created_when_auto_complete_false(self) -> None:
        """should_auto_complete=False — deferred task не создаётся."""
        should_auto_complete = AsyncMock(return_value=False)
        complete_active_turn = AsyncMock()
        transport = StdioServerTransport(
            should_auto_complete=should_auto_complete,
            complete_active_turn=complete_active_turn,
        )

        outcome = ProtocolOutcome(response=None)

        with patch.object(transport, "send"):
            await transport._finalize_outcome_and_send(
                method_name="session/prompt",
                session_id="sess_1",
                outcome=outcome,
            )

        assert "sess_1" not in transport._deferred_prompt_tasks
        complete_active_turn.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_session_cancel_cancels_deferred_prompt_task(self) -> None:
        """session/cancel отменяет deferred prompt task для session."""
        transport = StdioServerTransport()

        # Готовим долгоживущий "deferred" task
        async def long_running() -> None:
            await asyncio.sleep(60)

        deferred = asyncio.create_task(long_running())
        transport._deferred_prompt_tasks["sess_1"] = deferred

        with patch.object(transport, "send", new=AsyncMock()):
            outcome = ProtocolOutcome(
                response=ACPMessage(jsonrpc="2.0", id="99", result=None)
            )
            await transport._finalize_outcome_and_send(
                method_name="session/cancel",
                session_id="sess_1",
                outcome=outcome,
            )

        # Task получил cancel и task убран из tracking
        await asyncio.gather(deferred, return_exceptions=True)
        assert deferred.cancelled() or deferred.done()
        assert "sess_1" not in transport._deferred_prompt_tasks

    @pytest.mark.asyncio
    async def test_complete_deferred_prompt_loads_pending_on_cancel(self) -> None:
        """_complete_deferred_prompt на CancelledError достаёт pending response."""
        complete_cb = AsyncMock()  # не должен вызваться (отменён до sleep)
        load_pending = AsyncMock(
            return_value=ACPMessage(jsonrpc="2.0", id="7", result={"stopReason": "cancelled"})
        )
        transport = StdioServerTransport(
            complete_active_turn=complete_cb,
            load_pending_prompt_response=load_pending,
        )

        sent: list[ACPMessage] = []

        async def fake_send(m: ACPMessage) -> None:
            sent.append(m)

        with patch.object(transport, "send", side_effect=fake_send):
            task = asyncio.create_task(
                transport._complete_deferred_prompt(session_id="sess_x")
            )
            # Регистрируем как deferred, чтобы finalize-логика очистки сработала
            transport._deferred_prompt_tasks["sess_x"] = task

            # Даём немного выполниться (попадаем в asyncio.sleep) и отменяем
            await asyncio.sleep(0.01)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        load_pending.assert_awaited_once_with("sess_x")
        # Финальный response отправлен
        assert len(sent) == 1
        assert sent[0].result == {"stopReason": "cancelled"}


class TestStdioBackgroundPromptProcessing:
    """Тесты для фонового выполнения session/prompt."""

    @pytest.mark.asyncio
    async def test_process_prompt_in_background_sends_outcome(self) -> None:
        """_process_prompt_request_in_background отправляет outcome через finalize."""
        transport = StdioServerTransport()

        prompt_msg = ACPMessage(
            jsonrpc="2.0",
            id="p1",
            method="session/prompt",
            params={"sessionId": "sess_1"},
        )
        expected_response = ACPMessage(
            jsonrpc="2.0", id="p1", result={"stopReason": "end_turn"}
        )
        handler = AsyncMock(return_value=ProtocolOutcome(response=expected_response))

        sent = []
        with patch.object(transport, "send", side_effect=lambda m: sent.append(m)):
            await transport._process_prompt_request_in_background(
                acp_request=prompt_msg,
                on_message=handler,
                method_name="session/prompt",
                session_id="sess_1",
                request_id="p1",
            )

        handler.assert_awaited_once_with(prompt_msg)
        assert len(sent) == 1
        assert sent[0] == expected_response

    @pytest.mark.asyncio
    async def test_process_prompt_in_background_sends_error_on_exception(self) -> None:
        """Если handler бросает исключение — отправляется JSON-RPC error response."""
        transport = StdioServerTransport()

        prompt_msg = ACPMessage(
            jsonrpc="2.0",
            id="p2",
            method="session/prompt",
            params={"sessionId": "sess_1"},
        )

        async def bad_handler(_msg: ACPMessage) -> ProtocolOutcome:
            raise RuntimeError("boom")

        sent = []
        with patch.object(transport, "send", side_effect=lambda m: sent.append(m)), \
             patch("codelab.server.transport.stdio.logger"):
            await transport._process_prompt_request_in_background(
                acp_request=prompt_msg,
                on_message=bad_handler,
                method_name="session/prompt",
                session_id="sess_1",
                request_id="p2",
            )

        assert len(sent) == 1
        assert sent[0].error is not None
        assert sent[0].id == "p2"


class TestStdioCleanupBackgroundTasks:
    """Тесты для cleanup при close()."""

    @pytest.mark.asyncio
    async def test_cleanup_cancels_pending_prompt_tasks(self) -> None:
        """Pending prompt_tasks отменяются и дожидаются завершения."""
        transport = StdioServerTransport()

        async def long_running() -> None:
            await asyncio.sleep(60)

        task = asyncio.create_task(long_running())
        transport._prompt_tasks.add(task)

        await transport._cleanup_background_tasks()

        assert task.cancelled() or task.done()
        assert transport._prompt_tasks == set()

    @pytest.mark.asyncio
    async def test_cleanup_cancels_deferred_prompt_tasks(self) -> None:
        """Deferred prompt tasks отменяются и удаляются."""
        transport = StdioServerTransport()

        async def long_running() -> None:
            await asyncio.sleep(60)

        task = asyncio.create_task(long_running())
        transport._deferred_prompt_tasks["sess_1"] = task

        await transport._cleanup_background_tasks()

        assert task.cancelled() or task.done()
        assert transport._deferred_prompt_tasks == {}

    @pytest.mark.asyncio
    async def test_close_cancels_background_tasks(self) -> None:
        """close() триггерит _cleanup_background_tasks."""
        transport = StdioServerTransport()

        async def long_running() -> None:
            await asyncio.sleep(60)

        task = asyncio.create_task(long_running())
        transport._prompt_tasks.add(task)

        await transport.close()

        assert transport._closed is True
        assert transport._prompt_tasks == set()


class TestStdioReceiveLoopIntegration:
    """Интеграционный тест: receive-loop не блокируется на session/prompt."""

    @pytest.mark.asyncio
    async def test_prompt_runs_in_background_while_other_message_processed(self) -> None:
        """session/prompt не блокирует обработку последующих сообщений.

        Сценарий:
        - В stdin подаются два сообщения: session/prompt (блокируется на event)
          и обычный request, на который handler отвечает мгновенно.
        - Receive-loop должен прочитать оба и обработать обычный request,
          пока prompt task ещё висит. Это и есть фикс bypass-mode deadlock.
        """
        transport = StdioServerTransport()

        prompt_release = asyncio.Event()
        order: list[str] = []

        async def fake_handler(msg: ACPMessage) -> ProtocolOutcome:
            if msg.method == "session/prompt":
                order.append("prompt_start")
                await prompt_release.wait()
                order.append("prompt_done")
                return ProtocolOutcome(
                    response=ACPMessage(jsonrpc="2.0", id=msg.id, result={"stopReason": "end_turn"})
                )
            else:
                order.append(f"handled:{msg.method}")
                return ProtocolOutcome(
                    response=ACPMessage(jsonrpc="2.0", id=msg.id, result={"ok": True})
                )

        # Подготавливаем StreamReader с фиксированным содержимым stdin
        reader = asyncio.StreamReader()
        reader.feed_data(
            b'{"jsonrpc":"2.0","id":"p1","method":"session/prompt","params":{"sessionId":"s1"}}\n'
            b'{"jsonrpc":"2.0","id":"r1","method":"session/list","params":{}}\n'
        )
        # НЕ закрываем reader сразу — это позволит run() ждать после двух
        # сообщений; завершим его через transport._closed.
        transport._stdin_reader = reader

        sent: list[ACPMessage] = []

        async def fake_send(m: ACPMessage) -> None:
            sent.append(m)

        # Запускаем receive-loop напрямую, минуя stdin pipe
        # (имитируем тело цикла run())
        async def receive_loop() -> None:
            transport._on_message = fake_handler
            try:
                while not transport._closed:
                    line = await reader.readline()
                    if not line:
                        break
                    text = line.decode("utf-8").strip()
                    if not text:
                        continue
                    acp_request = ACPMessage.from_json(text)
                    method_name = acp_request.method
                    session_id = (
                        acp_request.params.get("sessionId")
                        if isinstance(acp_request.params, dict)
                        else None
                    )
                    if method_name == "session/prompt":
                        task = asyncio.create_task(
                            transport._process_prompt_request_in_background(
                                acp_request=acp_request,
                                on_message=fake_handler,
                                method_name=method_name,
                                session_id=session_id,
                                request_id=str(acp_request.id),
                            )
                        )
                        transport._prompt_tasks.add(task)
                        task.add_done_callback(
                            lambda t: transport._prompt_tasks.discard(t)
                        )
                        continue
                    outcome = await fake_handler(acp_request)
                    await transport._finalize_outcome_and_send(
                        method_name=method_name,
                        session_id=session_id,
                        outcome=outcome,
                    )
            finally:
                await transport._cleanup_background_tasks()

        with patch.object(transport, "send", side_effect=fake_send):
            loop_task = asyncio.create_task(receive_loop())

            # Даём receive-loop время обработать оба сообщения
            # session/list должен пройти раньше, чем prompt отпущен
            await asyncio.sleep(0.05)
            assert "handled:session/list" in order
            assert "prompt_start" in order
            assert "prompt_done" not in order  # prompt ещё ждёт

            # Отпускаем prompt
            prompt_release.set()
            await asyncio.sleep(0.05)
            assert "prompt_done" in order

            # Завершаем loop
            transport._closed = True
            # Подаём EOF чтобы readline вернул b""
            reader.feed_eof()
            await asyncio.wait_for(loop_task, timeout=1.0)

        # Должны быть отправлены оба response
        ids = sorted(str(m.id) for m in sent if m.id is not None)
        assert ids == ["p1", "r1"]

    @pytest.mark.asyncio
    async def test_bypass_mode_client_rpc_response_routes_during_prompt(self) -> None:
        """Регрессионный тест на bypass-mode deadlock.

        Точно воспроизводит сценарий, где synchronous tool execution внутри
        session/prompt отправляет RPC клиенту и ждёт ответ. Ответ приходит на
        stdin — receive-loop должен прочитать его и доставить ожидающему
        prompt-handler, иначе случится deadlock.

        До фикса: stdio receive-loop был заблокирован на ``await on_message``
        для session/prompt и не читал stdin → ответ клиента не доставлялся.

        После фикса: session/prompt запускается в фоне, receive-loop продолжает
        читать stdin и маршрутизирует client-response (``method=None,
        id=<rpc_id>``) в ``on_message`` (где `protocol.handle()` далее
        перенаправляет на ``handle_client_response``).
        """
        transport = StdioServerTransport()

        # Модель "ожидающего ClientRPCService": future, который должен быть
        # резолвнут когда придёт ответ клиента с тем же id.
        pending_rpc: dict[str, asyncio.Future[dict]] = {}
        rpc_response_id = "rpc-42"

        async def fake_handler(msg: ACPMessage) -> ProtocolOutcome:
            """Имитирует протокол:
            - session/prompt → отправляет client RPC и ждёт ответ.
            - Сообщение без method и с id → резолвит pending RPC (как
              `protocol.handle()` делает для client responses).
            """
            if msg.method is None and msg.id is not None:
                future = pending_rpc.get(str(msg.id))
                if future is not None and not future.done():
                    future.set_result(msg.result or {})
                return ProtocolOutcome()

            if msg.method == "session/prompt":
                # 1) Отправляем "fs/read_text_file" клиенту
                rpc_request = ACPMessage.request(
                    "fs/read_text_file",
                    {"path": "/tmp/foo"},
                    request_id=rpc_response_id,
                )
                await transport.send(rpc_request)

                # 2) Ждём ответ клиента — это место, где раньше был deadlock
                future: asyncio.Future[dict] = asyncio.get_event_loop().create_future()
                pending_rpc[rpc_response_id] = future

                rpc_result = await asyncio.wait_for(future, timeout=2.0)

                # 3) Завершаем prompt с полученным результатом
                return ProtocolOutcome(
                    response=ACPMessage(
                        jsonrpc="2.0",
                        id=msg.id,
                        result={
                            "stopReason": "end_turn",
                            "rpcResult": rpc_result,
                        },
                    )
                )

            return ProtocolOutcome(
                response=ACPMessage(jsonrpc="2.0", id=msg.id, result={"ok": True})
            )

        # Готовим stdin: только session/prompt — client response подадим позже
        reader = asyncio.StreamReader()
        reader.feed_data(
            b'{"jsonrpc":"2.0","id":"p1","method":"session/prompt",'
            b'"params":{"sessionId":"s1"}}\n'
        )
        transport._stdin_reader = reader

        sent: list[ACPMessage] = []

        async def fake_send(m: ACPMessage) -> None:
            sent.append(m)

        async def receive_loop() -> None:
            transport._on_message = fake_handler
            try:
                while not transport._closed:
                    line = await reader.readline()
                    if not line:
                        break
                    text = line.decode("utf-8").strip()
                    if not text:
                        continue
                    acp_request = ACPMessage.from_json(text)
                    method_name = acp_request.method
                    session_id = (
                        acp_request.params.get("sessionId")
                        if isinstance(acp_request.params, dict)
                        else None
                    )
                    if method_name == "session/prompt":
                        task = asyncio.create_task(
                            transport._process_prompt_request_in_background(
                                acp_request=acp_request,
                                on_message=fake_handler,
                                method_name=method_name,
                                session_id=session_id,
                                request_id=str(acp_request.id),
                            )
                        )
                        transport._prompt_tasks.add(task)
                        task.add_done_callback(
                            lambda t: transport._prompt_tasks.discard(t)
                        )
                        continue
                    outcome = await fake_handler(acp_request)
                    await transport._finalize_outcome_and_send(
                        method_name=method_name,
                        session_id=session_id,
                        outcome=outcome,
                    )
            finally:
                await transport._cleanup_background_tasks()

        with patch.object(transport, "send", side_effect=fake_send):
            loop_task = asyncio.create_task(receive_loop())

            # Даём prompt-task стартовать и отправить fs/read_text_file
            await asyncio.sleep(0.05)
            rpc_requests = [
                m for m in sent if m.method == "fs/read_text_file"
            ]
            assert len(rpc_requests) == 1, (
                "session/prompt должен был отправить fs/read_text_file"
            )

            # ИМИТИРУЕМ КЛИЕНТА: отправляем response на stdin
            # (этот шаг раньше приводил к deadlock — никто не читал stdin)
            client_response = (
                '{"jsonrpc":"2.0","id":"'
                + rpc_response_id
                + '","result":{"content":"file contents"}}\n'
            ).encode("utf-8")
            reader.feed_data(client_response)

            # Ждём финальный prompt response — без deadlock должен прийти быстро
            try:
                await asyncio.wait_for(
                    asyncio.shield(
                        _wait_for_response_id(sent, "p1", timeout=2.0)
                    ),
                    timeout=3.0,
                )
            finally:
                transport._closed = True
                reader.feed_eof()
                await asyncio.wait_for(loop_task, timeout=1.0)

        # Финальный response содержит результат RPC — значит весь flow прошёл
        prompt_responses = [m for m in sent if str(m.id) == "p1"]
        assert len(prompt_responses) == 1
        assert prompt_responses[0].result is not None
        assert prompt_responses[0].result["stopReason"] == "end_turn"
        assert prompt_responses[0].result["rpcResult"] == {
            "content": "file contents"
        }


async def _wait_for_response_id(
    sent: list[ACPMessage],
    target_id: str,
    *,
    timeout: float,
) -> ACPMessage:
    """Ждёт пока в списке отправленных сообщений появится сообщение с указанным id."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        for m in sent:
            if str(m.id) == target_id:
                return m
        await asyncio.sleep(0.01)
    raise TimeoutError(f"No message with id={target_id} sent within {timeout}s")

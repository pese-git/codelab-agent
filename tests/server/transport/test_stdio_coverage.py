"""Дополнительные тесты для покрытия непокрытых ветвей StdioServerTransport."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codelab.server.messages import ACPMessage
from codelab.server.protocol.state import ProtocolOutcome
from codelab.server.transport.stdio import StdioServerTransport


class TestStdioServerTransportRun:
    """Тесты для основного цикла run()."""

    async def _run_with_feed(
        self,
        transport: StdioServerTransport,
        on_message: Callable[[ACPMessage], Awaitable[ProtocolOutcome]],
        lines: list[bytes],
    ) -> list[ACPMessage]:
        """Запускает run(), подавая в stdin заданные строки и возвращая отправленные сообщения."""
        sent: list[ACPMessage] = []
        reader_ref: list[asyncio.StreamReader] = []

        async def fake_connect(factory: object, pipe: object) -> MagicMock:
            reader = transport._stdin_reader
            assert reader is not None
            reader_ref.append(reader)
            return MagicMock()

        feeder_started = asyncio.Event()

        async def feeder() -> None:
            feeder_started.set()
            for _ in range(500):
                if reader_ref:
                    break
                await asyncio.sleep(0.001)
            assert reader_ref, "StreamReader не был захвачен"
            reader = reader_ref[0]
            for line in lines:
                reader.feed_data(line)
            if lines:
                await asyncio.sleep(0.001)
            reader.feed_eof()

        with patch.object(transport, "send", side_effect=sent.append), \
             patch.object(transport, "_setup_signal_handlers"), \
             patch.object(transport, "_restore_signal_handlers"), \
             patch.object(sys.stdout, "reconfigure"), \
             patch("codelab.server.transport.stdio.asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.connect_read_pipe = AsyncMock(side_effect=fake_connect)

            feeder_task = asyncio.create_task(feeder())
            await feeder_started.wait()
            await transport.run(on_message=on_message)
            await feeder_task

        return sent

    async def test_run_exits_on_eof(self) -> None:
        """run() завершается при EOF stdin."""
        transport = StdioServerTransport()
        handler = AsyncMock(return_value=ProtocolOutcome())

        sent = await self._run_with_feed(transport, handler, [])

        assert sent == []

    async def test_run_handles_parse_error(self) -> None:
        """run() отправляет JSON-RPC error при ошибке парсинга строки."""
        transport = StdioServerTransport()
        handler = AsyncMock(return_value=ProtocolOutcome())

        sent = await self._run_with_feed(transport, handler, [b"not-json\n"])

        assert len(sent) == 1
        assert sent[0].id is None
        assert sent[0].error is not None
        assert sent[0].error.code == -32700
        assert sent[0].error.message == "Parse error"

    async def test_run_skips_empty_lines(self) -> None:
        """run() пропускает пустые строки и обрабатывает следующее сообщение."""
        transport = StdioServerTransport()
        handler = AsyncMock(
            return_value=ProtocolOutcome(
                response=ACPMessage.response("1", {"ok": True})
            )
        )

        sent = await self._run_with_feed(
            transport,
            handler,
            [b"\n", b'{"jsonrpc":"2.0","id":"1","method":"session/list","params":{}}\n'],
        )

        handler.assert_awaited_once()
        assert len(sent) == 1
        assert sent[0].id == "1"

    async def test_run_processes_normal_message(self) -> None:
        """run() обрабатывает обычное сообщение и отправляет response."""
        transport = StdioServerTransport()
        handler = AsyncMock(
            return_value=ProtocolOutcome(
                response=ACPMessage.response("r1", {"ok": True})
            )
        )

        sent = await self._run_with_feed(
            transport,
            handler,
            [b'{"jsonrpc":"2.0","id":"r1","method":"session/list","params":{}}\n'],
        )

        handler.assert_awaited_once()
        assert len(sent) == 1
        assert sent[0].id == "r1"
        assert sent[0].result == {"ok": True}

    async def test_run_sends_error_on_handler_exception(self) -> None:
        """run() отправляет JSON-RPC error если on_message бросает исключение."""
        transport = StdioServerTransport()

        async def bad_handler(_msg: ACPMessage) -> ProtocolOutcome:
            raise RuntimeError("boom")

        sent = await self._run_with_feed(
            transport,
            bad_handler,
            [b'{"jsonrpc":"2.0","id":"e1","method":"session/list","params":{}}\n'],
        )

        assert len(sent) == 1
        assert sent[0].id == "e1"
        assert sent[0].error is not None
        assert sent[0].error.code == -32603
        assert sent[0].error.message == "Internal error"

    async def test_run_schedules_prompt_in_background(self) -> None:
        """run() запускает session/prompt в фоновой задаче."""
        transport = StdioServerTransport()
        handler = AsyncMock(return_value=ProtocolOutcome(response=None))

        sent = await self._run_with_feed(
            transport,
            handler,
            [b'{"jsonrpc":"2.0","id":"p1","method":"session/prompt","params":{"sessionId":"s1"}}\n'],
        )

        handler.assert_awaited_once()
        assert transport._prompt_tasks == set()
        assert sent == []

    async def test_run_catches_cancelled_error(self) -> None:
        """run() корректно обрабатывает asyncio.CancelledError."""
        transport = StdioServerTransport()
        reader_ref: list[asyncio.StreamReader] = []

        async def fake_connect(factory: object, pipe: object) -> MagicMock:
            reader = transport._stdin_reader
            assert reader is not None
            reader_ref.append(reader)
            return MagicMock()

        with patch.object(transport, "send"), \
             patch.object(transport, "_setup_signal_handlers"), \
             patch.object(transport, "_restore_signal_handlers"), \
             patch.object(sys.stdout, "reconfigure"), \
             patch("codelab.server.transport.stdio.asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.connect_read_pipe = AsyncMock(side_effect=fake_connect)

            run_task = asyncio.create_task(transport.run(on_message=AsyncMock()))
            # Даём run() дойти до readline
            for _ in range(100):
                if reader_ref:
                    break
                await asyncio.sleep(0.001)
            assert reader_ref, "StreamReader не захвачен"
            run_task.cancel()
            await run_task

        assert run_task.done()


class TestStdioFinalizeOutcomeAndSend:
    """Тесты для _finalize_outcome_and_send и связанных ветвей."""

    async def test_should_auto_complete_exception_logs_error(self) -> None:
        """Ошибка в should_auto_complete логируется и deferred task не создаётся."""
        should_auto_complete = AsyncMock(side_effect=RuntimeError("auto-complete failed"))
        complete_active_turn = AsyncMock()
        transport = StdioServerTransport(
            should_auto_complete=should_auto_complete,
            complete_active_turn=complete_active_turn,
        )

        with patch("codelab.server.transport.stdio.logger") as mock_logger, \
             patch.object(transport, "send"):
            await transport._finalize_outcome_and_send(
                method_name="session/prompt",
                session_id="s1",
                outcome=ProtocolOutcome(response=None),
            )

        should_auto_complete.assert_awaited_once_with("s1")
        complete_active_turn.assert_not_awaited()
        assert "s1" not in transport._deferred_prompt_tasks
        mock_logger.error.assert_called_once()
        assert "should_auto_complete callback error" in mock_logger.error.call_args[0][0]

    async def test_existing_deferred_task_cancelled_before_new_one(self) -> None:
        """При создании нового deferred task предыдущий отменяется."""
        transport = StdioServerTransport(
            should_auto_complete=AsyncMock(return_value=True),
            complete_active_turn=AsyncMock(),
        )

        async def long_running() -> None:
            await asyncio.sleep(60)

        existing = asyncio.create_task(long_running())
        transport._deferred_prompt_tasks["s1"] = existing

        with patch.object(transport, "send"), \
             patch.object(transport, "_complete_deferred_prompt", new=AsyncMock()):
            await transport._finalize_outcome_and_send(
                method_name="session/prompt",
                session_id="s1",
                outcome=ProtocolOutcome(response=None),
            )

        await asyncio.gather(existing, return_exceptions=True)
        assert existing.cancelled() or existing.done()
        assert "s1" in transport._deferred_prompt_tasks
        assert transport._deferred_prompt_tasks["s1"] is not existing


class TestStdioBackgroundPromptProcessing:
    """Тесты для фоновой обработки session/prompt."""

    async def test_process_prompt_cancelled_error_logs_and_reraises(self) -> None:
        """CancelledError внутри фонового prompt обрабатывается и пробрасывается."""
        transport = StdioServerTransport()
        prompt_msg = ACPMessage(
            jsonrpc="2.0",
            id="p1",
            method="session/prompt",
            params={"sessionId": "s1"},
        )

        async def cancelled_handler(_msg: ACPMessage) -> ProtocolOutcome:
            raise asyncio.CancelledError()

        with patch("codelab.server.transport.stdio.logger") as mock_logger, \
             patch.object(transport, "send"):
            with pytest.raises(asyncio.CancelledError):
                await transport._process_prompt_request_in_background(
                    acp_request=prompt_msg,
                    on_message=cancelled_handler,
                    method_name="session/prompt",
                    session_id="s1",
                    request_id="p1",
                )

        mock_logger.info.assert_called_once()
        assert "background prompt request cancelled" in mock_logger.info.call_args[0][0]


class TestStdioCompleteDeferredPrompt:
    """Тесты для _complete_deferred_prompt."""

    async def test_complete_active_turn_exception_logs_error(self) -> None:
        """Исключение в complete_active_turn логируется, response не отправляется."""
        transport = StdioServerTransport(
            complete_active_turn=AsyncMock(side_effect=RuntimeError("completion failed")),
        )

        with patch("codelab.server.transport.stdio.asyncio.sleep", new=AsyncMock()), \
             patch("codelab.server.transport.stdio.logger") as mock_logger, \
             patch.object(transport, "send") as mock_send:
            await transport._complete_deferred_prompt(session_id="s1")

        bound_logger = mock_logger.bind.return_value
        bound_logger.error.assert_called_once()
        assert "deferred prompt completion error" in bound_logger.error.call_args[0][0]
        mock_send.assert_not_called()

    async def test_send_response_exception_logs_error(self) -> None:
        """Исключение при отправке финального response логируется."""
        response = ACPMessage.response("1", {"stopReason": "end_turn"})
        transport = StdioServerTransport(
            complete_active_turn=AsyncMock(return_value=response),
        )

        with patch("codelab.server.transport.stdio.asyncio.sleep", new=AsyncMock()), \
             patch("codelab.server.transport.stdio.logger") as mock_logger, \
             patch.object(transport, "send", side_effect=RuntimeError("send failed")):
            await transport._complete_deferred_prompt(session_id="s1")

        bound_logger = mock_logger.bind.return_value
        bound_logger.error.assert_called_once()
        assert "deferred prompt send error" in bound_logger.error.call_args[0][0]

    async def test_skips_send_when_transport_closed(self) -> None:
        """Если транспорт закрыт, финальный response не отправляется."""
        transport = StdioServerTransport(
            complete_active_turn=AsyncMock(
                return_value=ACPMessage.response("1", {"stopReason": "end_turn"})
            ),
        )
        transport._closed = True

        with patch("codelab.server.transport.stdio.asyncio.sleep", new=AsyncMock()), \
             patch("codelab.server.transport.stdio.logger") as mock_logger, \
             patch.object(transport, "send") as mock_send:
            await transport._complete_deferred_prompt(session_id="s1")

        mock_send.assert_not_called()
        bound_logger = mock_logger.bind.return_value
        bound_logger.debug.assert_called_once()
        assert "deferred prompt skipped (transport closed)" in bound_logger.debug.call_args[0][0]

    async def test_skips_send_when_response_is_none(self) -> None:
        """Если complete_active_turn вернул None, response не отправляется."""
        transport = StdioServerTransport(
            complete_active_turn=AsyncMock(return_value=None),
        )

        with patch("codelab.server.transport.stdio.asyncio.sleep", new=AsyncMock()), \
             patch("codelab.server.transport.stdio.logger") as mock_logger, \
             patch.object(transport, "send") as mock_send:
            await transport._complete_deferred_prompt(session_id="s1")

        mock_send.assert_not_called()
        bound_logger = mock_logger.bind.return_value
        bound_logger.debug.assert_called_once()
        assert "deferred prompt skipped (no response)" in bound_logger.debug.call_args[0][0]

    async def test_load_pending_response_exception_on_cancel_logs_debug(self) -> None:
        """Исключение в load_pending_prompt_response при отмене логируется на debug."""
        transport = StdioServerTransport(
            complete_active_turn=AsyncMock(),
            load_pending_prompt_response=AsyncMock(side_effect=RuntimeError("load failed")),
        )

        with patch("codelab.server.transport.stdio.logger") as mock_logger, \
             patch.object(transport, "send") as mock_send:
            task = asyncio.create_task(
                transport._complete_deferred_prompt(session_id="s1")
            )
            await asyncio.sleep(0.01)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        mock_send.assert_not_called()
        bound_logger = mock_logger.bind.return_value
        bound_logger.debug.assert_called_once()
        assert "deferred prompt cancelled response error" in bound_logger.debug.call_args[0][0]

    async def test_unexpected_exception_logs_error(self) -> None:
        """Непредвиденное исключение в _complete_deferred_prompt логируется."""
        transport = StdioServerTransport()
        sleep_error = RuntimeError("unexpected")

        with patch("codelab.server.transport.stdio.asyncio.sleep", side_effect=sleep_error), \
             patch("codelab.server.transport.stdio.logger") as mock_logger, \
             patch.object(transport, "send") as mock_send:
            await transport._complete_deferred_prompt(session_id="s1")

        mock_send.assert_not_called()
        bound_logger = mock_logger.bind.return_value
        bound_logger.error.assert_called_once()
        assert "deferred prompt unexpected error" in bound_logger.error.call_args[0][0]


class TestStdioSignalHandlers:
    """Тесты для обработчиков сигналов."""

    def test_restore_signal_handlers_swallows_value_error(self) -> None:
        """_restore_signal_handlers игнорирует ValueError/OSError."""
        transport = StdioServerTransport()

        with patch("codelab.server.transport.stdio.signal.signal", side_effect=ValueError):
            transport._restore_signal_handlers()



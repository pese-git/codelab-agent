"""Тесты для StdioServerTransport."""

import asyncio
import signal
import sys
from unittest.mock import patch

import pytest

from codelab.server.messages import ACPMessage
from codelab.server.protocol.state import ProtocolOutcome
from codelab.server.transport.stdio import StdioServerTransport


class TestStdioServerTransportInit:
    """Тесты для инициализации StdioServerTransport."""

    def test_initial_state(self) -> None:
        """Начальное состояние корректное."""
        transport = StdioServerTransport()
        assert transport._stdin_reader is None
        assert transport._closed is False
        assert transport._on_message is None


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

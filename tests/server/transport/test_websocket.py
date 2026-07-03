"""Тесты для WebSocketTransport."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from dishka import AsyncContainer

from codelab.server.messages import ACPMessage
from codelab.server.protocol.state import ProtocolOutcome
from codelab.server.transport.websocket import (
    WebSocketTransport,
    _truncate_payload,
)


@pytest.fixture
def mock_connection() -> MagicMock:
    """Создать мок WebSocketConnection."""
    connection = MagicMock()
    connection.closed = False
    connection.send_str = AsyncMock()
    connection.send_json = AsyncMock()
    connection.close = AsyncMock()
    connection.exception = MagicMock(return_value=None)
    return connection


@pytest.fixture
def mock_container() -> MagicMock:
    """Создать мок DI контейнера."""
    container = MagicMock(spec=AsyncContainer)
    container.__call__ = MagicMock(return_value=AsyncMock())
    container.get = AsyncMock()
    return container


@pytest.fixture
def mock_config() -> MagicMock:
    """Создать мок конфигурации."""
    return MagicMock()


class TestTruncatePayload:
    """Тесты _truncate_payload."""

    def test_truncate_long_payload(self) -> None:
        """Обрезка длинного payload."""
        payload = "x" * 1000
        result = _truncate_payload(payload, max_length=100)
        assert len(result) == 100
        assert result == "x" * 100

    def test_no_truncate_short_payload(self) -> None:
        """Не обрезать короткий payload."""
        payload = "short"
        result = _truncate_payload(payload, max_length=100)
        assert result == payload

    def test_no_truncate_exact_length(self) -> None:
        """Не обрезать payload ровно max_length."""
        payload = "x" * 100
        result = _truncate_payload(payload, max_length=100)
        assert result == payload


class TestWebSocketTransportInit:
    """Тесты инициализации WebSocketTransport."""

    def test_init_stores_parameters(
        self,
        mock_connection: MagicMock,
        mock_container: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Инициализация сохраняет все параметры."""
        transport = WebSocketTransport(
            connection=mock_connection,
            app_container=mock_container,
            config=mock_config,
            connection_id="conn_123",
            remote_addr="127.0.0.1",
        )

        assert transport._connection is mock_connection
        assert transport._app_container is mock_container
        assert transport._config is mock_config
        assert transport._connection_id == "conn_123"
        assert transport._remote_addr == "127.0.0.1"
        assert transport._closed is False


class TestWebSocketTransportSend:
    """Тесты send()."""

    @pytest.mark.asyncio
    async def test_send_writes_to_websocket(
        self,
        mock_connection: MagicMock,
        mock_container: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """send() записывает JSON в WebSocket."""
        transport = WebSocketTransport(
            connection=mock_connection,
            app_container=mock_container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        message = ACPMessage(jsonrpc="2.0", id="1", method="test")
        await transport.send(message)

        mock_connection.send_str.assert_called_once()
        sent_data = mock_connection.send_str.call_args[0][0]
        assert '"jsonrpc":"2.0"' in sent_data

    @pytest.mark.asyncio
    async def test_send_does_nothing_when_ws_closed(
        self,
        mock_connection: MagicMock,
        mock_container: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """send() не пишет когда WebSocket закрыт."""
        mock_connection.closed = True
        transport = WebSocketTransport(
            connection=mock_connection,
            app_container=mock_container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        message = ACPMessage(jsonrpc="2.0", id="1", method="test")
        await transport.send(message)

        mock_connection.send_str.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_is_thread_safe(
        self,
        mock_connection: MagicMock,
        mock_container: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """send() защищён lock для concurrent вызовов."""
        transport = WebSocketTransport(
            connection=mock_connection,
            app_container=mock_container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        message = ACPMessage(jsonrpc="2.0", id="1", method="test")
        await asyncio.gather(
            transport.send(message),
            transport.send(message),
            transport.send(message),
        )

        assert mock_connection.send_str.call_count == 3


class TestWebSocketTransportClose:
    """Тесты close()."""

    @pytest.mark.asyncio
    async def test_close_sets_flag(
        self,
        mock_connection: MagicMock,
        mock_container: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """close() устанавливает _closed=True."""
        transport = WebSocketTransport(
            connection=mock_connection,
            app_container=mock_container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        await transport.close()

        assert transport._closed is True

    @pytest.mark.asyncio
    async def test_close_closes_websocket(
        self,
        mock_connection: MagicMock,
        mock_container: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """close() закрывает WebSocket."""
        transport = WebSocketTransport(
            connection=mock_connection,
            app_container=mock_container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        await transport.close()

        mock_connection.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_is_idempotent(
        self,
        mock_connection: MagicMock,
        mock_container: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """close() идемпотентен."""
        transport = WebSocketTransport(
            connection=mock_connection,
            app_container=mock_container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        await transport.close()
        await transport.close()

        assert transport._closed is True

    @pytest.mark.asyncio
    async def test_close_skips_if_ws_already_closed(
        self,
        mock_connection: MagicMock,
        mock_container: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """close() не закрывает WebSocket если уже закрыт."""
        mock_connection.closed = True
        transport = WebSocketTransport(
            connection=mock_connection,
            app_container=mock_container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        await transport.close()

        mock_connection.close.assert_not_called()


class TestWebSocketTransportSendOutcome:
    """Тесты _send_outcome()."""

    @pytest.mark.asyncio
    async def test_send_notifications_first(
        self,
        mock_connection: MagicMock,
        mock_container: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Notifications отправляются перед response."""
        transport = WebSocketTransport(
            connection=mock_connection,
            app_container=mock_container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        notification = ACPMessage(jsonrpc="2.0", method="notify", params={})
        response = ACPMessage(jsonrpc="2.0", id="1", result={"ok": True})

        outcome = ProtocolOutcome(
            response=response,
            notifications=[notification],
            followup_responses=[],
        )

        await transport._send_outcome(outcome, request_id="1")

        assert mock_connection.send_str.call_count == 2
        first_call = mock_connection.send_str.call_args_list[0][0][0]
        assert "notify" in first_call

    @pytest.mark.asyncio
    async def test_send_followup_responses(
        self,
        mock_connection: MagicMock,
        mock_container: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Followup responses отправляются после основного response."""
        transport = WebSocketTransport(
            connection=mock_connection,
            app_container=mock_container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        response = ACPMessage(jsonrpc="2.0", id="1", result={"ok": True})
        followup1 = ACPMessage(jsonrpc="2.0", id="2", result={"followup": 1})
        followup2 = ACPMessage(jsonrpc="2.0", id="3", result={"followup": 2})

        outcome = ProtocolOutcome(
            response=response,
            notifications=[],
            followup_responses=[followup1, followup2],
        )

        await transport._send_outcome(outcome, request_id="1")

        assert mock_connection.send_str.call_count == 3

    @pytest.mark.asyncio
    async def test_send_outcome_does_nothing_when_ws_closed(
        self,
        mock_connection: MagicMock,
        mock_container: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """_send_outcome() не пишет когда WebSocket закрыт."""
        mock_connection.closed = True
        transport = WebSocketTransport(
            connection=mock_connection,
            app_container=mock_container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        outcome = ProtocolOutcome(
            response=ACPMessage(jsonrpc="2.0", id="1", result={"ok": True}),
        )

        await transport._send_outcome(outcome, request_id="1")

        mock_connection.send_str.assert_not_called()


class TestWebSocketTransportSendRpcRequest:
    """Тесты _send_rpc_request()."""

    @pytest.mark.asyncio
    async def test_send_rpc_request_uses_send_json(
        self,
        mock_connection: MagicMock,
        mock_container: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """_send_rpc_request() использует send_json."""
        transport = WebSocketTransport(
            connection=mock_connection,
            app_container=mock_container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        request_dict = {"jsonrpc": "2.0", "id": "rpc_1", "method": "fs/read"}
        await transport._send_rpc_request(request_dict)

        mock_connection.send_json.assert_called_once_with(request_dict)

    @pytest.mark.asyncio
    async def test_send_rpc_request_does_nothing_when_ws_closed(
        self,
        mock_connection: MagicMock,
        mock_container: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """_send_rpc_request() не пишет когда WebSocket закрыт."""
        mock_connection.closed = True
        transport = WebSocketTransport(
            connection=mock_connection,
            app_container=mock_container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        request_dict = {"jsonrpc": "2.0", "id": "rpc_1", "method": "fs/read"}
        await transport._send_rpc_request(request_dict)

        mock_connection.send_json.assert_not_called()


class TestWebSocketTransportSendProtocolMessage:
    """Тесты _send_protocol_message()."""

    @pytest.mark.asyncio
    async def test_send_protocol_message_uses_send_str(
        self,
        mock_connection: MagicMock,
        mock_container: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """_send_protocol_message() использует send_str."""
        transport = WebSocketTransport(
            connection=mock_connection,
            app_container=mock_container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        message = ACPMessage(jsonrpc="2.0", method="notify", params={})
        await transport._send_protocol_message(message)

        mock_connection.send_str.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_protocol_message_does_nothing_when_ws_closed(
        self,
        mock_connection: MagicMock,
        mock_container: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """_send_protocol_message() не пишет когда WebSocket закрыт."""
        mock_connection.closed = True
        transport = WebSocketTransport(
            connection=mock_connection,
            app_container=mock_container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        message = ACPMessage(jsonrpc="2.0", method="notify", params={})
        await transport._send_protocol_message(message)

        mock_connection.send_str.assert_not_called()


class TestWebSocketTransportFinalizeOutcome:
    """Тесты _finalize_outcome_and_send()."""

    @pytest.mark.asyncio
    async def test_finalize_cancels_deferred_on_session_cancel(
        self,
        mock_connection: MagicMock,
        mock_container: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """session/cancel отменяет deferred prompt task."""
        transport = WebSocketTransport(
            connection=mock_connection,
            app_container=mock_container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        async def long_running() -> None:
            await asyncio.sleep(60)

        deferred = asyncio.create_task(long_running())
        deferred_tasks: dict[str, asyncio.Task[None]] = {"sess_1": deferred}

        mock_protocol = MagicMock()
        outcome = ProtocolOutcome(
            response=ACPMessage(jsonrpc="2.0", id="1", result={}),
        )

        await transport._finalize_outcome_and_send(
            method_name="session/cancel",
            session_id="sess_1",
            request_id="1",
            outcome=outcome,
            deferred_prompt_tasks=deferred_tasks,
            protocol=mock_protocol,
        )

        await asyncio.gather(deferred, return_exceptions=True)
        assert deferred.cancelled() or deferred.done()
        assert "sess_1" not in deferred_tasks


class TestWebSocketTransportProcessPromptInBackground:
    """Тесты _process_prompt_request_in_background()."""

    @pytest.mark.asyncio
    async def test_process_prompt_sends_outcome(
        self,
        mock_connection: MagicMock,
        mock_container: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """_process_prompt_request_in_background отправляет outcome."""
        transport = WebSocketTransport(
            connection=mock_connection,
            app_container=mock_container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

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
        mock_protocol = MagicMock()

        await transport._process_prompt_request_in_background(
            acp_request=prompt_msg,
            handler=handler,
            method_name="session/prompt",
            session_id="sess_1",
            request_id="p1",
            deferred_prompt_tasks={},
            protocol=mock_protocol,
        )

        handler.assert_awaited_once_with(prompt_msg)
        mock_connection.send_str.assert_called()

    @pytest.mark.asyncio
    async def test_process_prompt_sends_error_on_exception(
        self,
        mock_connection: MagicMock,
        mock_container: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """_process_prompt_request_in_background отправляет error при исключении."""
        transport = WebSocketTransport(
            connection=mock_connection,
            app_container=mock_container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        prompt_msg = ACPMessage(
            jsonrpc="2.0",
            id="p2",
            method="session/prompt",
            params={"sessionId": "sess_1"},
        )

        async def bad_handler(_msg: ACPMessage) -> ProtocolOutcome:
            raise RuntimeError("boom")

        mock_protocol = MagicMock()

        await transport._process_prompt_request_in_background(
            acp_request=prompt_msg,
            handler=bad_handler,
            method_name="session/prompt",
            session_id="sess_1",
            request_id="p2",
            deferred_prompt_tasks={},
            protocol=mock_protocol,
        )

        mock_connection.send_str.assert_called()
        sent_data = mock_connection.send_str.call_args[0][0]
        assert "error" in sent_data.lower()

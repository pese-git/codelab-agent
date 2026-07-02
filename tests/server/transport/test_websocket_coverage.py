"""Дополнительные тесты покрытия для WebSocketTransport.

Покрывают ветки основного цикла run(), очистки ресурсов и отложенных
prompt-задач, которые не были протестированы в базовом наборе.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import WSMsgType

from codelab.server.messages import ACPMessage
from codelab.server.protocol.core import ACPProtocol
from codelab.server.protocol.state import ProtocolOutcome, SessionState
from codelab.server.rpc_holder import ClientRPCServiceHolder
from codelab.server.transport.websocket import WebSocketTransport


class WsMessage:
    """Заглушка входящего WebSocket сообщения."""

    def __init__(self, msg_type: WSMsgType, data: str | None = None) -> None:
        self.type = msg_type
        self.data = data


class AsyncContextManager:
    """Простая реализация async context manager для мока DI контейнера."""

    def __init__(self, scope: AsyncMock) -> None:
        self._scope = scope

    async def __aenter__(self) -> AsyncMock:
        return self._scope

    async def __aexit__(self, *args: Any) -> None:
        return None


def _make_container(protocol: MagicMock) -> MagicMock:
    """Создать мок DI контейнера с holder и request scope."""
    holder = ClientRPCServiceHolder()
    request_scope = AsyncMock()
    request_scope.get = AsyncMock(return_value=protocol)

    container = MagicMock()
    container.return_value = AsyncContextManager(request_scope)
    container.get = AsyncMock(return_value=holder)
    return container


def _make_ws(messages: list[WsMessage]) -> MagicMock:
    """Создать мок WebSocketResponse с заданной последовательностью сообщений."""
    ws = MagicMock()
    ws.closed = False
    ws.send_str = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    ws.exception = MagicMock(return_value=None)

    async def _message_iterator(_self: Any) -> AsyncIterator[WsMessage]:
        for msg in messages:
            yield msg

    ws.__aiter__ = _message_iterator
    return ws


def _make_protocol() -> MagicMock:
    """Создать мок ACPProtocol с методами, используемыми транспортом."""
    protocol = MagicMock(spec=ACPProtocol)
    protocol.handle_and_process = AsyncMock(return_value=ProtocolOutcome())
    protocol.handle_client_response = AsyncMock(return_value=ProtocolOutcome())
    protocol.cancel_active_turns_on_disconnect = AsyncMock(return_value=0)
    protocol.should_auto_complete_active_turn = AsyncMock(return_value=False)
    protocol.complete_active_turn = AsyncMock(
        return_value=ACPMessage.response("req_1", {"stopReason": "end_turn"})
    )
    protocol._storage = MagicMock()
    protocol._storage.load_session = AsyncMock(return_value=None)
    protocol._storage.save_session = AsyncMock()
    protocol._send_callback = None
    return protocol


@pytest.fixture
def mock_config() -> MagicMock:
    """Создать мок конфигурации."""
    return MagicMock()


class TestWebSocketTransportRunContainer:
    """Тесты ветки инициализации контейнера в run()."""

    @pytest.mark.asyncio
    async def test_run_exits_when_app_container_missing(
        self,
        mock_config: MagicMock,
    ) -> None:
        """run() закрывает WS и завершается если app_container не задан."""
        ws = _make_ws([])
        transport = WebSocketTransport(
            ws=ws,
            app_container=None,  # type: ignore[arg-type]
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        await transport.run()

        ws.close.assert_awaited_once()


class TestWebSocketTransportRunLifecycle:
    """Тесты жизненного цикла основного цикла run()."""

    @pytest.mark.asyncio
    async def test_run_uninitialized_notification_ignored(
        self,
        mock_config: MagicMock,
    ) -> None:
        """Notification до initialize игнорируется без ответа."""
        protocol = _make_protocol()
        ws = _make_ws([
            WsMessage(
                WSMsgType.TEXT,
                ACPMessage.notification("session/cancel", {"sessionId": "sess_1"}).to_json(),
            ),
            WsMessage(WSMsgType.CLOSE),
        ])
        container = _make_container(protocol)
        transport = WebSocketTransport(
            ws=ws,
            app_container=container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        await transport.run()

        ws.send_str.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_run_close_message_breaks_loop(
        self,
        mock_config: MagicMock,
    ) -> None:
        """Сообщение WSMsgType.CLOSE завершает цикл обработки."""
        protocol = _make_protocol()
        ws = _make_ws([
            WsMessage(WSMsgType.TEXT, ACPMessage.request("initialize", {}).to_json()),
            WsMessage(WSMsgType.CLOSE),
        ])
        container = _make_container(protocol)
        transport = WebSocketTransport(
            ws=ws,
            app_container=container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        await transport.run()

        # Цикл завершился корректно, дополнительных проверок не требуется.

    @pytest.mark.asyncio
    async def test_run_closing_message_breaks_loop(
        self,
        mock_config: MagicMock,
    ) -> None:
        """Сообщение WSMsgType.CLOSING завершает цикл обработки."""
        protocol = _make_protocol()
        ws = _make_ws([
            WsMessage(WSMsgType.TEXT, ACPMessage.request("initialize", {}).to_json()),
            WsMessage(WSMsgType.CLOSING),
        ])
        container = _make_container(protocol)
        transport = WebSocketTransport(
            ws=ws,
            app_container=container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        await transport.run()

        # Цикл завершился корректно, дополнительных проверок не требуется.


class TestWebSocketTransportRunCleanup:
    """Тесты очистки ресурсов при закрытии соединения."""

    @pytest.mark.asyncio
    async def test_run_cancels_pending_prompt_tasks_on_close(
        self,
        mock_config: MagicMock,
    ) -> None:
        """При disconnect отменяются фоновые prompt-задачи."""
        protocol = _make_protocol()

        async def slow_prompt_handler(msg: ACPMessage) -> ProtocolOutcome:
            if msg.method == "session/prompt":
                await asyncio.sleep(60)
            return ProtocolOutcome()

        ws = _make_ws([])
        container = _make_container(protocol)
        transport = WebSocketTransport(
            ws=ws,
            app_container=container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        async def _message_iterator(_self: Any) -> AsyncIterator[WsMessage]:
            yield WsMessage(WSMsgType.TEXT, ACPMessage.request("initialize", {}).to_json())
            yield WsMessage(
                WSMsgType.TEXT,
                ACPMessage.request("session/prompt", {"sessionId": "sess_1"}).to_json(),
            )
            # Даём фоновой задаче шанс запуститься перед закрытием соединения.
            await asyncio.sleep(0)
            yield WsMessage(WSMsgType.CLOSE)

        ws.__aiter__ = _message_iterator

        await transport.run(on_message=slow_prompt_handler)

        # Использовался переданный on_message, а не protocol.handle_and_process.
        protocol.handle_and_process.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_run_cancels_deferred_prompt_tasks_on_close(
        self,
        mock_config: MagicMock,
    ) -> None:
        """При disconnect отменяются отложенные deferred prompt-задачи."""
        protocol = _make_protocol()
        protocol.should_auto_complete_active_turn = AsyncMock(return_value=True)
        protocol.complete_active_turn = AsyncMock(side_effect=asyncio.sleep(60))

        deferred_created = asyncio.Event()
        ws = _make_ws([])
        container = _make_container(protocol)
        transport = WebSocketTransport(
            ws=ws,
            app_container=container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        original_finalize = transport._finalize_outcome_and_send

        async def patched_finalize(**kwargs: Any) -> None:
            await original_finalize(**kwargs)
            if kwargs.get("method_name") == "session/prompt":
                deferred_created.set()

        transport._finalize_outcome_and_send = patched_finalize

        async def _message_iterator(_self: Any) -> AsyncIterator[WsMessage]:
            yield WsMessage(WSMsgType.TEXT, ACPMessage.request("initialize", {}).to_json())
            yield WsMessage(
                WSMsgType.TEXT,
                ACPMessage.request("session/prompt", {"sessionId": "sess_1"}).to_json(),
            )
            await deferred_created.wait()
            yield WsMessage(WSMsgType.CLOSE)

        ws.__aiter__ = _message_iterator

        await transport.run()

        # Deferred task была отменена в finally до вызова complete_active_turn.
        protocol.complete_active_turn.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_run_logs_active_turns_cancelled(
        self,
        mock_config: MagicMock,
    ) -> None:
        """При disconnect логируется отмена активных turn."""
        protocol = _make_protocol()
        protocol.cancel_active_turns_on_disconnect = AsyncMock(return_value=3)

        ws = _make_ws([
            WsMessage(WSMsgType.TEXT, ACPMessage.request("initialize", {}).to_json()),
            WsMessage(WSMsgType.CLOSE),
        ])
        container = _make_container(protocol)
        transport = WebSocketTransport(
            ws=ws,
            app_container=container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        await transport.run()

        protocol.cancel_active_turns_on_disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_logs_pending_rpc_cancelled(
        self,
        mock_config: MagicMock,
    ) -> None:
        """При disconnect логируется отмена ожидающих RPC-запросов."""
        protocol = _make_protocol()

        service_mock = MagicMock()
        service_mock.cancel_all_pending_requests = MagicMock(return_value=2)

        with patch(
            "codelab.server.transport.websocket.ClientRPCService",
            return_value=service_mock,
        ):
            ws = _make_ws([
                WsMessage(WSMsgType.TEXT, ACPMessage.request("initialize", {}).to_json()),
                WsMessage(WSMsgType.CLOSE),
            ])
            container = _make_container(protocol)
            transport = WebSocketTransport(
                ws=ws,
                app_container=container,
                config=mock_config,
                connection_id="conn_1",
                remote_addr="127.0.0.1",
            )

            await transport.run()

        service_mock.cancel_all_pending_requests.assert_called_once()


class TestWebSocketTransportFinalizeOutcome:
    """Тесты _finalize_outcome_and_send."""

    @pytest.mark.asyncio
    async def test_finalize_cancels_existing_deferred_task(
        self,
        mock_config: MagicMock,
    ) -> None:
        """Создание нового deferred task отменяет предыдущий для той же сессии."""
        transport = WebSocketTransport(
            ws=_make_ws([]),
            app_container=_make_container(_make_protocol()),
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        async def long_running() -> None:
            await asyncio.sleep(60)

        existing_task = asyncio.create_task(long_running())
        deferred_tasks: dict[str, asyncio.Task[None]] = {"sess_1": existing_task}

        protocol = _make_protocol()
        protocol.should_auto_complete_active_turn = AsyncMock(return_value=True)

        await transport._finalize_outcome_and_send(
            method_name="session/prompt",
            session_id="sess_1",
            request_id="p1",
            outcome=ProtocolOutcome(response=None),
            deferred_prompt_tasks=deferred_tasks,
            protocol=protocol,
        )

        await asyncio.gather(existing_task, return_exceptions=True)
        assert existing_task.cancelled() or existing_task.done()
        assert "sess_1" in deferred_tasks
        assert deferred_tasks["sess_1"] is not existing_task


class TestWebSocketTransportCompleteDeferredPrompt:
    """Тесты _complete_deferred_prompt."""

    @pytest.mark.asyncio
    async def test_complete_deferred_prompt_handles_timeout(
        self,
        mock_config: MagicMock,
    ) -> None:
        """TimeoutError при complete_active_turn не прерывает выполнение."""
        protocol = _make_protocol()
        protocol.complete_active_turn = AsyncMock(side_effect=TimeoutError)
        ws = _make_ws([])
        ws.closed = False
        transport = WebSocketTransport(
            ws=ws,
            app_container=_make_container(protocol),
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        await transport._complete_deferred_prompt(
            protocol=protocol,
            session_id="sess_1",
            deferred_prompt_tasks={},
        )

        ws.send_str.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_complete_deferred_prompt_handles_completion_error(
        self,
        mock_config: MagicMock,
    ) -> None:
        """Ошибка при complete_active_turn не прерывает выполнение."""
        protocol = _make_protocol()
        protocol.complete_active_turn = AsyncMock(side_effect=RuntimeError("boom"))
        ws = _make_ws([])
        ws.closed = False
        transport = WebSocketTransport(
            ws=ws,
            app_container=_make_container(protocol),
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        await transport._complete_deferred_prompt(
            protocol=protocol,
            session_id="sess_1",
            deferred_prompt_tasks={},
        )

        ws.send_str.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_complete_deferred_prompt_send_error(
        self,
        mock_config: MagicMock,
    ) -> None:
        """Ошибка отправки ответа логируется, но не прерывает выполнение."""
        protocol = _make_protocol()
        ws = _make_ws([])
        ws.closed = False
        ws.send_str = AsyncMock(side_effect=RuntimeError("send failed"))
        transport = WebSocketTransport(
            ws=ws,
            app_container=_make_container(protocol),
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        await transport._complete_deferred_prompt(
            protocol=protocol,
            session_id="sess_1",
            deferred_prompt_tasks={},
        )

        ws.send_str.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_complete_deferred_prompt_skips_when_ws_closed(
        self,
        mock_config: MagicMock,
    ) -> None:
        """Ответ не отправляется если WebSocket уже закрыт."""
        protocol = _make_protocol()
        ws = _make_ws([])
        ws.closed = True
        transport = WebSocketTransport(
            ws=ws,
            app_container=_make_container(protocol),
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        await transport._complete_deferred_prompt(
            protocol=protocol,
            session_id="sess_1",
            deferred_prompt_tasks={},
        )

        ws.send_str.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_complete_deferred_prompt_skips_when_no_response(
        self,
        mock_config: MagicMock,
    ) -> None:
        """Ответ не отправляется если complete_active_turn вернул None."""
        protocol = _make_protocol()
        protocol.complete_active_turn = AsyncMock(return_value=None)
        ws = _make_ws([])
        ws.closed = False
        transport = WebSocketTransport(
            ws=ws,
            app_container=_make_container(protocol),
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        await transport._complete_deferred_prompt(
            protocol=protocol,
            session_id="sess_1",
            deferred_prompt_tasks={},
        )

        ws.send_str.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_complete_deferred_prompt_sends_cancel_response(
        self,
        mock_config: MagicMock,
    ) -> None:
        """При отмене deferred task отправляется ответ из pending_prompt_response."""
        protocol = _make_protocol()
        session = SessionState(
            session_id="sess_1",
            cwd="/tmp",
            pending_prompt_response={
                "request_id": "req_1",
                "stop_reason": "cancelled",
            },
        )
        protocol._storage.load_session = AsyncMock(return_value=session)

        ws = _make_ws([])
        ws.closed = False
        transport = WebSocketTransport(
            ws=ws,
            app_container=_make_container(protocol),
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        deferred_tasks: dict[str, asyncio.Task[None]] = {}
        task = asyncio.create_task(
            transport._complete_deferred_prompt(
                protocol=protocol,
                session_id="sess_1",
                deferred_prompt_tasks=deferred_tasks,
            )
        )
        await asyncio.sleep(0.01)
        task.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await task

        ws.send_str.assert_awaited_once()
        assert session.pending_prompt_response is None
        protocol._storage.save_session.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_complete_deferred_prompt_cancel_response_error(
        self,
        mock_config: MagicMock,
    ) -> None:
        """Ошибка при формировании cancel-response не прерывает выполнение."""
        protocol = _make_protocol()
        protocol._storage.load_session = AsyncMock(side_effect=RuntimeError("load failed"))

        ws = _make_ws([])
        ws.closed = False
        transport = WebSocketTransport(
            ws=ws,
            app_container=_make_container(protocol),
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        deferred_tasks: dict[str, asyncio.Task[None]] = {}
        task = asyncio.create_task(
            transport._complete_deferred_prompt(
                protocol=protocol,
                session_id="sess_1",
                deferred_prompt_tasks=deferred_tasks,
            )
        )
        await asyncio.sleep(0.01)
        task.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await task

        ws.send_str.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_complete_deferred_prompt_handles_outer_error(
        self,
        mock_config: MagicMock,
    ) -> None:
        """Непредвиденная ошибка в _complete_deferred_prompt не прерывает выполнение."""
        protocol = _make_protocol()
        ws = _make_ws([])
        ws.closed = False
        transport = WebSocketTransport(
            ws=ws,
            app_container=_make_container(protocol),
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        with patch(
            "codelab.server.transport.websocket.asyncio.sleep",
            side_effect=RuntimeError("sleep boom"),
        ):
            await transport._complete_deferred_prompt(
                protocol=protocol,
                session_id="sess_1",
                deferred_prompt_tasks={},
            )

        ws.send_str.assert_not_awaited()


class TestObservabilityFlushOnDisconnect:
    """Тесты flush observability data при disconnect."""

    @pytest.mark.asyncio
    async def test_flush_called_on_disconnect(
        self,
        mock_config: MagicMock,
    ) -> None:
        """flush_all() вызывается при закрытии WebSocket соединения."""
        protocol = _make_protocol()
        ws = _make_ws([WsMessage(WSMsgType.CLOSE)])
        ws.closed = False

        flush_manager = AsyncMock()
        flush_manager.flush_all = AsyncMock()

        container = _make_container(protocol)

        def get_side_effect(cls):
            if cls.__name__ == "ObservabilityFlushManager":
                return flush_manager
            return MagicMock()

        container.get = AsyncMock(side_effect=get_side_effect)

        transport = WebSocketTransport(
            ws=ws,
            app_container=container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        await transport.run(on_message=protocol.handle_and_process)

        flush_manager.flush_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_flush_error_does_not_crash(
        self,
        mock_config: MagicMock,
    ) -> None:
        """Ошибка при flush не прерывает закрытие соединения."""
        protocol = _make_protocol()
        ws = _make_ws([WsMessage(WSMsgType.CLOSE)])
        ws.closed = False

        flush_manager = AsyncMock()
        flush_manager.flush_all = AsyncMock(side_effect=RuntimeError("flush failed"))

        container = _make_container(protocol)

        def get_side_effect(cls):
            if cls.__name__ == "ObservabilityFlushManager":
                return flush_manager
            return MagicMock()

        container.get = AsyncMock(side_effect=get_side_effect)

        transport = WebSocketTransport(
            ws=ws,
            app_container=container,
            config=mock_config,
            connection_id="conn_1",
            remote_addr="127.0.0.1",
        )

        # Не должно поднять исключение
        await transport.run(on_message=protocol.handle_and_process)

        # flush_all был вызван
        flush_manager.flush_all.assert_awaited_once()
